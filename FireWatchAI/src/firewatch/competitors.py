"""Competitor registry, safe pickle audit and a shared ONNX detector runner.

Three pieces used by the edge benchmark and the competitor tests:

* :func:`load_registry` reads ``scout/doi_thu.yaml`` (one entry per public
  model: source revision, SHA-256, native class ids and their map onto the
  project convention 0 = fire, 1 = smoke, native imgsz / conf).
* :func:`audit_pickle` scans the pickle opcodes inside a PyTorch ``.pt``
  archive **without unpickling it**. It simulates the pickle stack just enough
  to know which globals are imported, which are called (``REDUCE``) and which
  are only instantiated with ``__new__`` (``NEWOBJ``), and accepts the file
  only when every global is on a fixed allow-list. A ``.pt`` from outside the
  team must pass this audit before ``torch.load`` / ``ultralytics.YOLO`` sees
  it, because those execute the pickle.
* :class:`OnnxYolo` runs an exported YOLO ONNX graph with one common
  pre/post-processing code path (letterbox, conf filter, class-aware NMS for
  raw heads, end-to-end heads as-is), and times each stage. Every model,
  including the team's, goes through the same code, so latency differences
  come from the graph, not from the wrapper.
"""

from __future__ import annotations

import hashlib
import pickletools
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import yaml

FIRE, SMOKE = 0, 1
"""Project class ids (``detector.classes: [fire, smoke]``)."""

# ───────────────────────────── registry ─────────────────────────────


@dataclass(slots=True)
class Competitor:
    """One public model as declared in ``scout/doi_thu.yaml``."""

    ma: str
    repo: str
    revision: str
    thu_muc: str
    weights: str
    sha256: str
    dinh_dang: str
    kien_truc: str
    co: str
    lop_goc: dict[int, str]
    map_lop: dict[int, int]
    imgsz_goc: int
    conf_goc: float
    trang_thai_bien: str
    trang_thai_pickle: str = ""
    chi_lua: bool = False
    giay_phep: str = ""
    ghi_chu: str = ""
    extra: dict = field(default_factory=dict)

    def weights_path(self, root: Path) -> Path:
        """Absolute path of the weights file under the repo ``root``."""
        return root / self.thu_muc / self.weights

    def map_class(self, cls_id: int) -> int | None:
        """Project class (0 fire / 1 smoke) of a native id, ``None`` = drop."""
        return self.map_lop.get(int(cls_id))


REQUIRED_KEYS = ("ma", "repo", "revision", "thu_muc", "weights", "sha256",
                 "dinh_dang", "kien_truc", "co", "lop_goc", "map_lop",
                 "imgsz_goc", "conf_goc", "trang_thai_bien")


def parse_competitor(entry: dict) -> Competitor:
    """Validate one YAML entry and build a :class:`Competitor`.

    Parameters
    ----------
    entry : dict
        Mapping read from ``doi_thu.yaml``.

    Returns
    -------
    Competitor

    Raises
    ------
    ValueError
        When a key is missing, the class map points outside {0, 1}, maps a
        native id that does not exist, or a fire-only model maps smoke.
    """
    missing = [k for k in REQUIRED_KEYS if k not in entry]
    if missing:
        raise ValueError(f"{entry.get('ma', '?')}: thiếu khoá {missing}")
    lop_goc = {int(k): str(v) for k, v in entry["lop_goc"].items()}
    map_lop = {int(k): int(v) for k, v in (entry["map_lop"] or {}).items()}
    bad = {k: v for k, v in map_lop.items() if v not in (FIRE, SMOKE)}
    if bad:
        raise ValueError(f"{entry['ma']}: map_lop ra ngoài 0/1: {bad}")
    unknown = sorted(set(map_lop) - set(lop_goc))
    if unknown:
        raise ValueError(f"{entry['ma']}: map_lop có id không có trong lop_goc "
                         f"{unknown}")
    if len(set(map_lop.values())) != len(map_lop):
        raise ValueError(f"{entry['ma']}: hai lớp gốc map vào cùng một lớp")
    chi_lua = bool(entry.get("chi_lua", False))
    if chi_lua and SMOKE in map_lop.values():
        raise ValueError(f"{entry['ma']}: chi_lua nhưng có map sang smoke")
    known = set(REQUIRED_KEYS) | {"trang_thai_pickle", "chi_lua", "giay_phep",
                                  "ghi_chu"}
    return Competitor(
        ma=str(entry["ma"]), repo=str(entry["repo"]),
        revision=str(entry["revision"]), thu_muc=str(entry["thu_muc"]),
        weights=str(entry["weights"]), sha256=str(entry["sha256"]),
        dinh_dang=str(entry["dinh_dang"]), kien_truc=str(entry["kien_truc"]),
        co=str(entry["co"]), lop_goc=lop_goc, map_lop=map_lop,
        imgsz_goc=int(entry["imgsz_goc"]), conf_goc=float(entry["conf_goc"]),
        trang_thai_bien=str(entry["trang_thai_bien"]),
        trang_thai_pickle=str(entry.get("trang_thai_pickle", "")),
        chi_lua=chi_lua, giay_phep=str(entry.get("giay_phep", "")),
        ghi_chu=str(entry.get("ghi_chu", "")),
        extra={k: v for k, v in entry.items() if k not in known})


def load_registry(path: Path, section: str = "doi_thu") -> list[Competitor]:
    """Read every entry of one list of ``scout/doi_thu.yaml``.

    Parameters
    ----------
    path : Path
        YAML file with top-level lists ``doi_thu`` (competitors) and
        ``moc_doi`` (the team's own reference models).
    section : str, optional
        Which list to read.

    Returns
    -------
    list of Competitor
        In file order; codes (``ma``) are unique.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out = [parse_competitor(e) for e in data.get(section) or []]
    codes = Counter(c.ma for c in out)
    dup = [k for k, n in codes.items() if n > 1]
    if dup:
        raise ValueError(f"mã đối thủ trùng: {dup}")
    return out


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# ─────────────────────────── pickle audit ───────────────────────────

_BUILTIN_MODULES = ("builtins", "__builtin__")
_SAFE_BUILTINS = frozenset({
    "set", "frozenset", "dict", "list", "tuple", "slice", "range", "complex",
    "float", "int", "bool", "str", "bytes", "bytearray"})
SAFE_CALLABLES: frozenset[tuple[str, str]] = frozenset({
    ("torch._utils", "_rebuild_tensor_v2"),
    ("torch._utils", "_rebuild_parameter"),
    ("torch._utils", "_rebuild_parameter_with_state"),
    ("torch._tensor", "_rebuild_from_type_v2"),
    ("torch", "Size"),
    ("torch", "device"),
    ("collections", "OrderedDict"),
    ("_codecs", "encode"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy._core.multiarray", "_reconstruct"),
    ("numpy.core.multiarray", "scalar"),
    ("numpy._core.multiarray", "scalar"),
    ("numpy", "dtype"),
    ("numpy", "ndarray"),
    ("ultralytics.utils", "IterableSimpleNamespace"),
    *((m, n) for m in _BUILTIN_MODULES for n in _SAFE_BUILTINS),
})
"""Globals that may be *called* by the pickle (``REDUCE``): tensor/storage
rebuilders, plain containers, NumPy reconstructors and the attribute bag
``IterableSimpleNamespace`` (a ``types.SimpleNamespace`` subclass). Nothing
here reads files, imports modules, runs code or touches the network."""

SAFE_TYPE_NAMES: frozenset[tuple[str, str]] = frozenset({
    ("torch.nn.parameter", "Parameter"),
})
_SAFE_TYPE_PREFIXES = ("torch.nn.modules.", "ultralytics.nn.")


def is_safe_type(module: str, name: str) -> bool:
    """Whether ``module.name`` may appear as a class built with ``__new__``.

    Allowed: storage classes of ``torch`` (``FloatStorage`` …), layer classes
    of ``torch.nn.modules.*`` and ``ultralytics.nn.*`` (class names start with
    an upper-case letter), plus :data:`SAFE_TYPE_NAMES`. These classes are
    only instantiated by ``NEWOBJ`` + ``BUILD`` (no constructor runs).
    """
    if (module, name) in SAFE_TYPE_NAMES:
        return True
    if module == "torch" and name.endswith("Storage") and name[:1].isupper():
        return True
    return module.startswith(_SAFE_TYPE_PREFIXES) and name[:1].isupper()


@dataclass(slots=True)
class PickleAudit:
    """Result of :func:`audit_pickle`."""

    path: str
    ok: bool
    globals: list[str]
    problems: list[str]
    calls: dict[str, int]

    def summary(self) -> str:
        """One line for logs and reports."""
        state = "QUA" if self.ok else "KHONG QUA"
        extra = f"; vấn đề: {self.problems[:5]}" if self.problems else ""
        return f"{state}: {len(self.globals)} global{extra}"


_MARK = object()
_STRING_OPS = frozenset({"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8",
                         "UNICODE", "STRING", "BINSTRING", "SHORT_BINSTRING"})
_FORBIDDEN_OPS = frozenset({"EXT1", "EXT2", "EXT4"})


class _StackError(Exception):
    pass


def _pop_for(op: pickletools.OpcodeInfo, stack: list) -> list:
    """Pop the operands of ``op`` (mark-aware) and return them, bottom first."""
    before = op.stack_before
    if pickletools.markobject in before:
        popped: list = []
        while stack and stack[-1] is not _MARK:
            popped.append(stack.pop())
        if not stack:
            raise _StackError(f"{op.name}: không thấy MARK")
        stack.pop()
        below = before.index(pickletools.markobject)
        head = []
        for _ in range(below):
            if not stack:
                raise _StackError(f"{op.name}: ngăn xếp rỗng")
            head.append(stack.pop())
        return head[::-1] + popped[::-1]
    out = []
    for _ in range(len(before)):
        if not stack:
            raise _StackError(f"{op.name}: ngăn xếp rỗng")
        out.append(stack.pop())
    return out[::-1]


def _scan_stream(data: bytes, allow_dill_types: frozenset[str],
                 globals_seen: set, problems: list, calls: Counter) -> None:
    """Walk one pickle stream; fill ``globals_seen``, ``problems``, ``calls``."""
    stack: list = []
    memo: dict = {}
    for op, arg, pos in pickletools.genops(data):
        name = op.name
        if name in _FORBIDDEN_OPS:
            problems.append(f"opcode {name} tại {pos}")
        if name in ("PUT", "BINPUT", "LONG_BINPUT"):
            if not stack:
                raise _StackError(f"{name} trên ngăn xếp rỗng")
            memo[arg] = stack[-1]
            continue
        if name == "MEMOIZE":
            if not stack:
                raise _StackError("MEMOIZE trên ngăn xếp rỗng")
            memo[len(memo)] = stack[-1]
            continue
        if name in ("GET", "BINGET", "LONG_BINGET"):
            stack.append(memo.get(arg))
            continue
        if name == "DUP":
            if not stack:
                raise _StackError("DUP trên ngăn xếp rỗng")
            stack.append(stack[-1])
            continue
        operands = _pop_for(op, stack)
        value = None
        if name in _STRING_OPS:
            value = arg if isinstance(arg, str) else None
        elif name in ("GLOBAL", "INST"):
            mod, _, nm = str(arg).partition(" ")
            globals_seen.add((mod, nm))
            value = ("G", mod, nm)
            if name == "INST":
                _check_call("INST", value, None, problems, calls,
                            allow_dill_types)
        elif name == "STACK_GLOBAL":
            mod, nm = operands
            if isinstance(mod, str) and isinstance(nm, str):
                globals_seen.add((mod, nm))
                value = ("G", mod, nm)
            else:
                problems.append(f"STACK_GLOBAL không xác định tại {pos}")
        elif name == "TUPLE1":
            value = ("T", tuple(operands))
        elif name == "REDUCE":
            _check_call("REDUCE", operands[0], operands[1], problems, calls,
                        allow_dill_types)
            value = _dill_type_value(operands[0], operands[1], allow_dill_types)
        elif name in ("NEWOBJ", "NEWOBJ_EX", "OBJ"):
            _check_new(name, operands[0], problems, calls)
        for item in op.stack_after:
            stack.append(_MARK if item is pickletools.markobject else value)


def _check_call(kind: str, callee, args, problems: list, calls: Counter,
                allow_dill_types: frozenset[str]) -> None:
    if not (isinstance(callee, tuple) and callee[:1] == ("G",)):
        problems.append(f"{kind} gọi đối tượng không phải global đã biết")
        return
    _, mod, nm = callee
    calls[f"{kind} {mod}.{nm}"] += 1
    if (mod, nm) in SAFE_CALLABLES:
        return
    if (mod, nm) == ("dill._dill", "_load_type"):
        ok = (isinstance(args, tuple) and args[:1] == ("T",)
              and len(args[1]) == 1 and args[1][0] in allow_dill_types)
        if ok:
            return
        problems.append(f"{kind} {mod}.{nm}{_fmt_args(args)} chưa được duyệt")
        return
    problems.append(f"{kind} gọi {mod}.{nm} (không nằm trong danh sách cho phép)")


def _dill_type_value(callee, args, allow_dill_types: frozenset[str]):
    """``dill._dill._load_type('set')`` evaluates to the builtin ``set``.

    Only for reviewed names that are plain builtin types, so later ``REDUCE``
    calls on the result are checked like a direct ``builtins.set`` call.
    """
    if callee != ("G", "dill._dill", "_load_type"):
        return None
    if not (isinstance(args, tuple) and args[:1] == ("T",) and len(args[1]) == 1):
        return None
    tname = args[1][0]
    if tname in allow_dill_types and tname in _SAFE_BUILTINS:
        return ("G", "builtins", tname)
    return None


def _fmt_args(args) -> str:
    if isinstance(args, tuple) and args[:1] == ("T",):
        return repr(args[1])
    return "(?)"


def _check_new(kind: str, cls, problems: list, calls: Counter) -> None:
    if not (isinstance(cls, tuple) and cls[:1] == ("G",)):
        problems.append(f"{kind} trên lớp không xác định")
        return
    _, mod, nm = cls
    calls[f"{kind} {mod}.{nm}"] += 1
    if not (is_safe_type(mod, nm) or (mod, nm) in SAFE_CALLABLES):
        problems.append(f"{kind} tạo {mod}.{nm} (không nằm trong danh sách cho phép)")


def _global_allowed(mod: str, nm: str, allow_dill_types: frozenset[str]) -> bool:
    if (mod, nm) in SAFE_CALLABLES or is_safe_type(mod, nm):
        return True
    return (mod, nm) == ("dill._dill", "_load_type") and bool(allow_dill_types)


def audit_pickle(path: Path,
                 allow_dill_types: frozenset[str] = frozenset()) -> PickleAudit:
    """Statically audit the pickles of a PyTorch zip checkpoint.

    Nothing is unpickled or imported. The file is accepted only when it is a
    zip archive (``torch.save`` format), contains no TorchScript code, every
    pickle stream parses, every imported global is allowed, every ``REDUCE``
    calls an allowed callable and every ``NEWOBJ`` builds an allowed class.

    Parameters
    ----------
    path : Path
        ``.pt`` file.
    allow_dill_types : frozenset of str, optional
        Type names that ``dill._dill._load_type`` may look up (for example
        ``{"set"}``). Empty by default: any ``dill`` global fails the audit.
        Only widen after an explicit review.

    Returns
    -------
    PickleAudit
        ``ok`` is ``True`` only if no problem was found.
    """
    path = Path(path)
    globals_seen: set[tuple[str, str]] = set()
    problems: list[str] = []
    calls: Counter = Counter()
    if not zipfile.is_zipfile(path):
        problems.append("không phải zip (định dạng torch cũ hoặc hỏng)")
        return PickleAudit(str(path), False, [], problems, {})
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if any("/code/" in n or n.startswith("code/") for n in names):
            problems.append("có mã TorchScript (thư mục code/)")
        pkls = [n for n in names if n.endswith(".pkl")]
        if not pkls:
            problems.append("không có pickle trong archive")
        for n in pkls:
            try:
                _scan_stream(zf.read(n), allow_dill_types, globals_seen,
                             problems, calls)
            except (_StackError, ValueError, zipfile.BadZipFile) as exc:
                problems.append(f"{n}: không phân tích được ({exc})")
    for mod, nm in sorted(globals_seen):
        if not _global_allowed(mod, nm, allow_dill_types):
            problems.append(f"global {mod}.{nm} không nằm trong danh sách cho phép")
    seen = sorted(f"{m}.{n}" for m, n in globals_seen)
    return PickleAudit(str(path), not problems, seen, problems, dict(calls))


# ──────────────────────────── ONNX runner ────────────────────────────


@dataclass(slots=True)
class Box:
    """One detection in original-image pixels, already mapped to 0/1."""

    cls: int
    conf: float
    xyxy: tuple[float, float, float, float]
    cls_goc: int


def letterbox(img: np.ndarray, size: int,
              pad_value: int = 114) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize keeping aspect ratio and pad to ``size × size``.

    Parameters
    ----------
    img : np.ndarray
        BGR image ``(H, W, 3)``.
    size : int
        Square output side.
    pad_value : int, optional
        Grey level of the padding (114 like Ultralytics).

    Returns
    -------
    out : np.ndarray
        ``(size, size, 3)`` uint8.
    ratio : float
        Scale applied to the original image.
    pad : tuple of int
        ``(left, top)`` padding in pixels.
    """
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    if (nw, nh) != (w, h):
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dw, dh = (size - nw) / 2, (size - nh) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    out = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT,
                             value=(pad_value, pad_value, pad_value))
    return out, r, (left, top)


def to_tensor(img: np.ndarray) -> np.ndarray:
    """BGR uint8 ``(H, W, 3)`` -> RGB float32 ``(1, 3, H, W)`` in [0, 1]."""
    x = img[:, :, ::-1].transpose(2, 0, 1)
    return np.ascontiguousarray(x, dtype=np.float32)[None] / 255.0


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> np.ndarray:
    """Greedy non-maximum suppression; returns kept indices by score."""
    if len(boxes) == 0:
        return np.zeros(0, dtype=np.int64)
    x1, y1, x2, y2 = boxes.T
    areas = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    order = np.argsort(-scores, kind="stable")
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        union = areas[i] + areas[rest] - inter
        ov = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
        order = rest[ov <= iou]
    return np.asarray(keep, dtype=np.int64)


def head_kind(shape: tuple[int, ...]) -> str:
    """Tell an end-to-end head ``(1, N, 6)`` from a raw one ``(1, 4+nc, A)``."""
    if len(shape) != 3:
        raise ValueError(f"đầu ra ONNX không hỗ trợ: {shape}")
    if shape[2] == 6 and shape[1] != 6:
        return "e2e"
    if shape[1] < shape[2]:
        return "raw"
    raise ValueError(f"đầu ra ONNX không hỗ trợ: {shape}")


def decode_output(out: np.ndarray, conf: float, iou: float,
                  max_det: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Boxes ``xyxy`` (letterbox pixels), scores and native class ids.

    Raw heads (YOLOv8/YOLO11: ``(1, 4+nc, A)`` with ``cx, cy, w, h`` then
    class scores) are filtered at ``conf`` and passed through class-aware NMS.
    End-to-end heads (YOLO26: ``(1, N, 6)`` = ``x1, y1, x2, y2, conf, cls``)
    are only filtered at ``conf``. At most ``max_det`` boxes are returned.
    """
    if head_kind(out.shape) == "e2e":
        rows = out[0]
        rows = rows[rows[:, 4] >= conf]
        rows = rows[np.argsort(-rows[:, 4], kind="stable")][:max_det]
        return rows[:, :4], rows[:, 4], rows[:, 5].astype(np.int64)
    pred = out[0].T
    scores_all = pred[:, 4:]
    cls = scores_all.argmax(axis=1)
    score = scores_all[np.arange(len(cls)), cls]
    sel = score >= conf
    pred, cls, score = pred[sel], cls[sel], score[sel]
    cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    offset = cls[:, None].astype(np.float32) * 7680.0
    keep = nms(xyxy + offset, score, iou)[:max_det]
    return xyxy[keep], score[keep], cls[keep].astype(np.int64)


class OnnxYolo:
    """Shared runner for exported YOLO ONNX graphs (CPU, batch 1).

    Parameters
    ----------
    path : Path
        ONNX file.
    class_map : dict of int to int, optional
        Native class id -> project id (0 fire, 1 smoke); ids not in the map
        are dropped. ``None`` keeps native ids unchanged.
    imgsz : int, optional
        Input side for graphs with a dynamic spatial size; fixed-size graphs
        always use their own size.
    threads : int, optional
        ``intra_op_num_threads`` (the edge definition fixes 4).
    conf, iou : float, optional
        Confidence floor and NMS IoU (pipeline defaults 0.25 / 0.5).
    max_det : int, optional
        Boxes kept per image (pipeline default 50).
    """

    def __init__(self, path: Path, class_map: dict[int, int] | None = None,
                 imgsz: int | None = None, threads: int = 4, conf: float = 0.25,
                 iou: float = 0.5, max_det: int = 50):
        import onnxruntime as ort  # import chậm, chỉ khi cần

        so = ort.SessionOptions()
        so.intra_op_num_threads = int(threads)
        so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.path = Path(path)
        self.session = ort.InferenceSession(str(path), so,
                                            providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        side = inp.shape[2] if len(inp.shape) == 4 else None
        self.fixed_size = isinstance(side, int)
        self.imgsz = int(side) if self.fixed_size else int(imgsz or 640)
        meta = self.session.get_modelmeta().custom_metadata_map or {}
        self.metadata = dict(meta)
        self.class_map = class_map
        self.threads = int(threads)
        self.conf, self.iou, self.max_det = float(conf), float(iou), int(max_det)

    def infer(self, img: np.ndarray) -> tuple[list[Box], dict[str, float]]:
        """Detect on one BGR image; also return per-stage times in ms."""
        t0 = time.perf_counter()
        lb, r, (left, top) = letterbox(img, self.imgsz)
        x = to_tensor(lb)
        t1 = time.perf_counter()
        out = self.session.run(None, {self.input_name: x})[0]
        t2 = time.perf_counter()
        boxes = self.postprocess(out, r, left, top, img.shape[:2])
        t3 = time.perf_counter()
        ms = {"tien_xu_ly": (t1 - t0) * 1e3, "suy_luan": (t2 - t1) * 1e3,
              "hau_xu_ly": (t3 - t2) * 1e3}
        return boxes, ms

    def postprocess(self, out: np.ndarray, r: float, left: int, top: int,
                    hw: tuple[int, int]) -> list[Box]:
        """Decode, undo the letterbox and map classes."""
        xyxy, score, cls = decode_output(out, self.conf, self.iou, self.max_det)
        h, w = hw
        res: list[Box] = []
        for b, s, c in zip(xyxy, score, cls):
            mapped = (int(c) if self.class_map is None
                      else self.class_map.get(int(c)))
            if mapped is None:
                continue
            x1 = float(np.clip((b[0] - left) / r, 0, w))
            y1 = float(np.clip((b[1] - top) / r, 0, h))
            x2 = float(np.clip((b[2] - left) / r, 0, w))
            y2 = float(np.clip((b[3] - top) / r, 0, h))
            res.append(Box(mapped, float(s), (x1, y1, x2, y2), int(c)))
        return res

    def detect_jpeg(self, data: bytes) -> tuple[list[Box], dict[str, float]]:
        """End-to-end on encoded bytes: decode + :meth:`infer`, timed."""
        t0 = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        t1 = time.perf_counter()
        if img is None:
            raise ValueError("không giải mã được ảnh")
        boxes, ms = self.infer(img)
        ms["giai_ma"] = (t1 - t0) * 1e3
        ms["tong"] = (time.perf_counter() - t0) * 1e3
        return boxes, ms
