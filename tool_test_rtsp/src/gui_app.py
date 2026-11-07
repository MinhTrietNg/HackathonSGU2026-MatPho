"""
RTSP Studio: Desktop GUI Application for generating & managing multiple virtual RTSP camera streams.
Built with Tkinter, TTK, Pillow and PyAV.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Dict, Optional

import cv2
from PIL import Image, ImageTk

from tool_test_rtsp.src.sample_generator import ensure_default_sample_videos
from tool_test_rtsp.src.stream_fleet_manager import StreamFleetManager
from tool_test_rtsp.src.virtual_cam_worker import VirtualCamWorker

logger = logging.getLogger("rtsp_studio.gui")


class CameraCard(ttk.LabelFrame):
    """Visual card representing a single RTSP virtual camera stream."""

    def __init__(
        self,
        parent: tk.Widget,
        worker: VirtualCamWorker,
        on_remove: callable,
        on_sync_edge: callable,
        on_swap_video: callable,
    ) -> None:
        super().__init__(parent, text=f" {worker.cam_id.upper()} - {worker.cam_name} ", padding=8)
        self.worker = worker
        self.on_remove = on_remove
        self.on_sync_edge = on_sync_edge
        self.on_swap_video = on_swap_video
        self.is_user_dragging = False

        # Thumbnail cache
        self._photo_img: Optional[ImageTk.PhotoImage] = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)

        # 1. Left Thumbnail Preview
        self.thumb_canvas = tk.Canvas(self, width=160, height=90, bg="#1e1e1e", highlightthickness=1, highlightbackground="#444")
        self.thumb_canvas.grid(row=0, column=0, rowspan=3, padx=(0, 10), pady=2, sticky="nw")
        self.thumb_canvas.create_text(80, 45, text="No Signal", fill="#888888", font=("Segoe UI", 9))

        # 2. Middle Info & Controls
        info_frame = ttk.Frame(self)
        info_frame.grid(row=0, column=1, sticky="ew")
        info_frame.columnconfigure(1, weight=1)

        # Status badge & Timecode
        header_frame = ttk.Frame(info_frame)
        header_frame.pack(fill="x", pady=(0, 2))

        self.lbl_status = tk.Label(header_frame, text="STOPPED", bg="#555555", fg="white", font=("Segoe UI", 8, "bold"), padx=6, pady=1)
        self.lbl_status.pack(side="left", padx=(0, 8))

        self.lbl_timecode = ttk.Label(header_frame, text="00:00 / 00:00 (1.0x)", font=("Consolas", 9, "bold"))
        self.lbl_timecode.pack(side="left")

        # Video source path
        src_frame = ttk.Frame(info_frame)
        src_frame.pack(fill="x", pady=2)
        ttk.Label(src_frame, text="File:", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 4))
        self.lbl_filepath = ttk.Label(src_frame, text=Path(self.worker.video_path).name, font=("Segoe UI", 8))
        self.lbl_filepath.pack(side="left", fill="x", expand=True)

        btn_swap = ttk.Button(src_frame, text="Đổi File", width=8, command=lambda: self.on_swap_video(self.worker.cam_id))
        btn_swap.pack(side="right", padx=(4, 0))

        # Target RTSP URL & Copy Button
        rtsp_frame = ttk.Frame(info_frame)
        rtsp_frame.pack(fill="x", pady=2)
        ttk.Label(rtsp_frame, text="RTSP:", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 4))
        self.lbl_rtsp = ttk.Label(rtsp_frame, text=self.worker.target_rtsp_url, foreground="#0066cc", font=("Consolas", 8))
        self.lbl_rtsp.pack(side="left", fill="x", expand=True)

        btn_copy = ttk.Button(rtsp_frame, text="Copy URL", width=8, command=self._copy_rtsp_url)
        btn_copy.pack(side="right", padx=(4, 0))

        # 3. Interactive Seek Slider
        seek_frame = ttk.Frame(self)
        seek_frame.grid(row=1, column=1, sticky="ew", pady=(4, 2))
        seek_frame.columnconfigure(0, weight=1)

        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_slider = ttk.Scale(
            seek_frame,
            from_=0.0,
            to=100.0,
            orient="horizontal",
            variable=self.seek_var,
        )
        self.seek_slider.grid(row=0, column=0, sticky="ew")
        self.seek_slider.bind("<ButtonPress-1>", self._on_slider_press)
        self.seek_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # 4. Action Buttons (Bottom row: Play/Pause, Speeds, Rewind, Sync Edge, Delete)
        action_frame = ttk.Frame(self)
        action_frame.grid(row=2, column=1, sticky="ew", pady=(4, 0))

        self.btn_play_pause = ttk.Button(action_frame, text="▶ Start", width=8, command=self._toggle_play_pause)
        self.btn_play_pause.pack(side="left", padx=(0, 4))

        btn_rewind = ttk.Button(action_frame, text="|<< 00:00", width=8, command=self._rewind)
        btn_rewind.pack(side="left", padx=(0, 8))

        # Speed buttons
        ttk.Label(action_frame, text="Tốc độ:", font=("Segoe UI", 8)).pack(side="left", padx=(0, 2))
        for spd in (0.25, 0.5, 1.0, 2.0, 4.0):
            lbl = f"{spd}x" if spd != 1.0 else "1x"
            btn_spd = ttk.Button(action_frame, text=lbl, width=4, command=lambda s=spd: self._set_speed(s))
            btn_spd.pack(side="left", padx=1)

        # Sync to Edge button
        btn_sync = ttk.Button(action_frame, text="Sync Edge", width=9, command=lambda: self.on_sync_edge(self.worker.cam_id))
        btn_sync.pack(side="right", padx=(4, 0))

        # Remove button
        btn_del = ttk.Button(action_frame, text="✖ Xóa", width=6, command=lambda: self.on_remove(self.worker.cam_id))
        btn_del.pack(side="right", padx=(4, 0))

    def _copy_rtsp_url(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.worker.target_rtsp_url)
        messagebox.showinfo("Đã sao chép", f"Đã copy URL RTSP vào clipboard:\n{self.worker.target_rtsp_url}")

    def _toggle_play_pause(self) -> None:
        if not self.worker.is_running:
            self.worker.start()
        elif self.worker.is_paused:
            self.worker.resume()
        else:
            self.worker.pause()

    def _rewind(self) -> None:
        self.worker.seek_to_second(0.0)

    def _set_speed(self, speed: float) -> None:
        self.worker.set_speed(speed)

    def _on_slider_press(self, event) -> None:
        self.is_user_dragging = True

    def _on_slider_release(self, event) -> None:
        ratio = self.seek_var.get() / 100.0
        self.worker.seek_to_ratio(ratio)
        self.is_user_dragging = False

    def update_ui(self) -> None:
        """Called periodically by the main studio loop to refresh status and thumbnail."""
        state = self.worker.get_state()

        # Update status badge
        if not state["is_running"]:
            self.lbl_status.config(text="STOPPED", bg="#666666", fg="white")
            self.btn_play_pause.config(text="▶ Start")
        elif state["is_paused"]:
            self.lbl_status.config(text="PAUSED", bg="#d97706", fg="white")
            self.btn_play_pause.config(text="▶ Resume")
        else:
            self.lbl_status.config(text="STREAMING", bg="#16a34a", fg="white")
            self.btn_play_pause.config(text="⏸ Pause")

        # Update timecode
        cur = state["current_sec"]
        dur = state["duration_sec"]
        spd = state["speed"]
        cur_str = f"{int(cur//60):02d}:{int(cur%60):02d}"
        dur_str = f"{int(dur//60):02d}:{int(dur%60):02d}"
        self.lbl_timecode.config(text=f"{cur_str} / {dur_str} ({spd:.2f}x)")

        # Update slider if user is not actively dragging it
        if not self.is_user_dragging and dur > 0:
            pct = min(100.0, max(0.0, (cur / dur) * 100.0))
            self.seek_var.set(pct)

        # Update thumbnail preview
        thumb = self.worker.get_preview_thumbnail(max_w=160, max_h=90)
        if thumb is not None:
            # Convert BGR (OpenCV) to RGB (PIL)
            rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            self._photo_img = ImageTk.PhotoImage(pil_img)
            self.thumb_canvas.delete("all")
            self.thumb_canvas.create_image(80, 45, image=self._photo_img, anchor="center")


class RTSPStudioApp:
    """Main Application Window for RTSP Camera Stream Studio."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mắt Phố - RTSP Virtual Camera Studio (Multi-Stream Fleet)")
        self.root.geometry("980x720")
        self.root.minsize(800, 500)

        self.fleet = StreamFleetManager(mediamtx_host="127.0.0.1", mediamtx_port=8554)
        self.cards: Dict[str, CameraCard] = {}
        self._is_closing = False

        self._init_theme()
        self._build_top_bar()
        self._build_scrollable_card_area()
        self._build_status_bar()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start periodic GUI refresh loop
        self.root.after(150, self._periodic_refresh)

    def _init_theme(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

    def _build_top_bar(self) -> None:
        top_frame = ttk.LabelFrame(self.root, text=" Quản lý Fleet & Điều khiển Tổng ", padding=8)
        top_frame.pack(fill="x", padx=10, pady=(8, 4))

        # Row 1: Add cams, batch folder, generate samples
        r1 = ttk.Frame(top_frame)
        r1.pack(fill="x", pady=2)

        btn_add_cam = ttk.Button(r1, text="➕ Thêm Video Cam", command=self._action_add_single_video)
        btn_add_cam.pack(side="left", padx=(0, 6))

        btn_add_folder = ttk.Button(r1, text="📁 Thêm Cả Thư Mục", command=self._action_add_from_folder)
        btn_add_folder.pack(side="left", padx=(0, 6))

        btn_samples = ttk.Button(r1, text="🎬 Tạo 2 Video Mẫu (Bình thường & Cháy)", command=self._action_generate_samples)
        btn_samples.pack(side="left", padx=(0, 6))

        # Presets on the right
        btn_load_preset = ttk.Button(r1, text="📂 Mở Preset", command=self._action_load_preset)
        btn_load_preset.pack(side="right", padx=(4, 0))

        btn_save_preset = ttk.Button(r1, text="💾 Lưu Preset", command=self._action_save_preset)
        btn_save_preset.pack(side="right", padx=(4, 0))

        # Row 2: Batch controls (Start All, Pause All, Resume All, Stop All, Sync All)
        r2 = ttk.Frame(top_frame)
        r2.pack(fill="x", pady=(6, 2))

        ttk.Button(r2, text="▶ Start All", width=10, command=self._action_start_all).pack(side="left", padx=(0, 4))
        ttk.Button(r2, text="⏸ Pause All", width=10, command=self._action_pause_all).pack(side="left", padx=(0, 4))
        ttk.Button(r2, text="▶ Resume All", width=12, command=self._action_resume_all).pack(side="left", padx=(0, 4))
        ttk.Button(r2, text="⏹ Stop All", width=10, command=self._action_stop_all).pack(side="left", padx=(0, 10))

        # Bulk speed controls
        ttk.Label(r2, text="Tất cả tốc độ:").pack(side="left", padx=(4, 2))
        for spd in (0.5, 1.0, 2.0, 4.0):
            lbl = f"{spd}x" if spd != 1.0 else "1x"
            ttk.Button(r2, text=lbl, width=4, command=lambda s=spd: self._action_set_speed_all(s)).pack(side="left", padx=1)

        # Sync all to Edge button
        btn_sync_all = ttk.Button(r2, text="🌐 Sync All -> Edge (:8090)", command=self._action_sync_all_edge)
        btn_sync_all.pack(side="right")

    def _build_scrollable_card_area(self) -> None:
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=10, pady=4)

        self.canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=None, yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Responsive card width on resize
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )

    def _build_status_bar(self) -> None:
        self.status_bar = ttk.Frame(self.root, padding=4)
        self.status_bar.pack(fill="x", side="bottom")

        self.lbl_status_msg = ttk.Label(
            self.status_bar,
            text="Sẵn sàng. Chưa có luồng nào đang phát. Hãy thêm video hoặc bấm 'Tạo Video Mẫu'.",
            font=("Segoe UI", 9),
        )
        self.lbl_status_msg.pack(side="left", fill="x", expand=True)

        self.lbl_count_msg = ttk.Label(
            self.status_bar,
            text="0 Cameras | Target: rtsp://127.0.0.1:8554",
            font=("Segoe UI", 9, "bold"),
        )
        self.lbl_count_msg.pack(side="right")

    # --- Actions ---

    def _action_add_single_video(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Chọn Video Nguồn",
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov"), ("All Files", "*.*")],
        )
        if not file_path:
            return

        worker = self.fleet.add_camera(video_path=file_path, auto_start=True)
        self._rebuild_card_ui()
        self.lbl_status_msg.config(text=f"Đã thêm camera {worker.cam_id} ({Path(file_path).name})")

    def _action_add_from_folder(self) -> None:
        dir_path = filedialog.askdirectory(title="Chọn Thư Mục Chứa Video")
        if not dir_path:
            return

        created = self.fleet.add_from_directory(dir_path, auto_start=True)
        self._rebuild_card_ui()
        self.lbl_status_msg.config(text=f"Đã thêm {len(created)} camera từ thư mục: {dir_path}")

    def _action_generate_samples(self) -> None:
        sample_dir = Path(__file__).resolve().parent.parent / "samples"
        res = ensure_default_sample_videos(sample_dir)
        # Add normal and fire sample cameras
        self.fleet.add_camera(
            video_path=res["normal"],
            cam_id="cam_sample_normal",
            cam_name="Giao Thông Bình Thường (Sample)",
            auto_start=True,
        )
        self.fleet.add_camera(
            video_path=res["fire"],
            cam_id="cam_sample_fire",
            cam_name="Mô Phỏng Cháy Tầng 2 (Sample)",
            auto_start=True,
        )
        self._rebuild_card_ui()
        self.lbl_status_msg.config(text=f"Đã sinh và kích hoạt 2 camera mẫu tại {sample_dir}")

    def _action_start_all(self) -> None:
        self.fleet.start_all()
        self.lbl_status_msg.config(text="Đã gửi lệnh Start All cho toàn bộ camera.")

    def _action_pause_all(self) -> None:
        self.fleet.pause_all()
        self.lbl_status_msg.config(text="Đã tạm dừng (Pause) toàn bộ camera.")

    def _action_resume_all(self) -> None:
        self.fleet.resume_all()
        self.lbl_status_msg.config(text="Đã tiếp tục (Resume) toàn bộ camera.")

    def _action_stop_all(self) -> None:
        self.fleet.stop_all()
        self.lbl_status_msg.config(text="Đã dừng (Stop) toàn bộ camera.")

    def _action_set_speed_all(self, speed: float) -> None:
        self.fleet.set_speed_all(speed)
        self.lbl_status_msg.config(text=f"Đã đổi tốc độ phát của tất cả camera thành {speed}x.")

    def _action_save_preset(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="Lưu Cấu Hình Fleet (Preset)",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
        )
        if not file_path:
            return
        self.fleet.save_preset(file_path)
        messagebox.showinfo("Lưu Preset Thành Công", f"Đã lưu preset thành công vào:\n{file_path}")

    def _action_load_preset(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Mở Cấu Hình Fleet (Preset)",
            filetypes=[("JSON Files", "*.json")],
        )
        if not file_path:
            return
        loaded = self.fleet.load_preset(file_path, auto_start=True)
        self._rebuild_card_ui()
        messagebox.showinfo("Đã nạp Preset", f"Đã nạp thành công {len(loaded)} camera từ preset.")

    def _action_sync_all_edge(self) -> None:
        def _sync_worker():
            res = self.fleet.sync_all_to_edge()
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Kết Quả Sync Edge",
                    f"Đã đồng bộ {res['synced']}/{res['total']} camera sang Edge Backend (:8090)!",
                ),
            )

        threading.Thread(target=_sync_worker, daemon=True).start()

    def _handle_remove_camera(self, cam_id: str) -> None:
        if messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn xóa camera {cam_id}?"):
            self.fleet.remove_camera(cam_id)
            self._rebuild_card_ui()

    def _handle_sync_edge_single(self, cam_id: str) -> None:
        def _sync_single():
            res = self.fleet.sync_camera_to_edge(cam_id)
            if res.get("success"):
                self.root.after(
                    0,
                    lambda: messagebox.showinfo("Sync Thành Công", f"Camera {cam_id} đã đăng ký thành công trên Edge Backend!"),
                )
            else:
                self.root.after(
                    0,
                    lambda: messagebox.showwarning("Sync Thất Bại", f"Không thể sync camera {cam_id}:\n{res.get('error')}"),
                )

        threading.Thread(target=_sync_single, daemon=True).start()

    def _handle_swap_video(self, cam_id: str) -> None:
        file_path = filedialog.askopenfilename(
            title=f"Chọn Video Mới Cho {cam_id}",
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov"), ("All Files", "*.*")],
        )
        if not file_path:
            return

        worker = self.fleet.get_camera(cam_id)
        if worker:
            worker.change_video(file_path)
            card = self.cards.get(cam_id)
            if card:
                card.lbl_filepath.config(text=Path(file_path).name)
            self.lbl_status_msg.config(text=f"Đã đổi video nguồn của {cam_id} thành {Path(file_path).name}")

    def _rebuild_card_ui(self) -> None:
        """Synchronize the visible cards with the current fleet cameras."""
        current_cams = {w.cam_id: w for w in self.fleet.list_cameras()}

        # Destroy cards that no longer exist
        for cid in list(self.cards.keys()):
            if cid not in current_cams:
                self.cards[cid].destroy()
                del self.cards[cid]

        # Add new cards
        for cid, worker in current_cams.items():
            if cid not in self.cards:
                card = CameraCard(
                    parent=self.scrollable_frame,
                    worker=worker,
                    on_remove=self._handle_remove_camera,
                    on_sync_edge=self._handle_sync_edge_single,
                    on_swap_video=self._handle_swap_video,
                )
                card.pack(fill="x", expand=True, padx=4, pady=4)
                self.cards[cid] = card

        self.lbl_count_msg.config(text=f"{len(current_cams)} Cameras | Target: rtsp://127.0.0.1:8554")

    def _periodic_refresh(self) -> None:
        """Periodic loop to update previews, timecodes and seek sliders."""
        if self._is_closing:
            return

        try:
            for card in list(self.cards.values()):
                card.update_ui()
        except Exception as exc:
            logger.debug("Refresh loop error: %s", exc)

        self.root.after(150, self._periodic_refresh)

    def _on_close(self) -> None:
        self._is_closing = True
        self.fleet.stop_all()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = RTSPStudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
