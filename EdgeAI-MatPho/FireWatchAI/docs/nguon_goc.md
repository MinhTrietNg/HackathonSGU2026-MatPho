# Nguồn gốc mã FireWatch trong repo này

## Nhập từ đâu, khi nào

| Mục | Giá trị |
|---|---|
| Repo nguồn | `MinhTrietNg/Model-Mat-Pho-` |
| Commit nguồn | `afa5a70788ebd872b0523cc722f4c372e4f7f6c4` (2026-11-06 15:25 +0700) |
| Ngày nhập | 2026-11-07 |
| Commit nhập | `42b9f631602d21128ba0342b82e03c850aa279da` ("Nhập mã nguồn FireWatch làm bản gốc của repo") |
| Vị trí hiện tại | thư mục `EdgeAI-MatPho/FireWatchAI/` (dời từ gốc repo sang `ai/` ở commit đổi bố cục, đổi tên `ai/` thành `FireWatchAI/`, rồi chuyển vào `EdgeAI-MatPho/` ngày 2026-11-08) |

Phần được nhập, so theo hash object của git giữa `afa5a70` và `42b9f63` (hash object
trùng nghĩa là nội dung trùng từng byte):

| Đường dẫn | Kết quả |
|---|---|
| `src/firewatch/` | trùng toàn bộ cây |
| `config.yaml`, `pyproject.toml`, `uv.lock`, `.env.example`, `.gitignore` | trùng |
| `tests/` | nhập 23 trên 46 file, cả 23 file trùng bản nguồn |

Không nhập: `curation/`, `data/`, `docs/`, `models/`, `notebooks/`, `reports/`,
`scout/`, `scripts/`, `README.md`, và 23 file test sau: `test_agreement_report.py`,
`test_apply_review.py`, `test_benchmark_edge.py`, `test_camsim.py`,
`test_competitors.py`, `test_data_layout.py`, `test_eval_dfire.py`,
`test_eval_suite.py`, `test_eval_verifier.py`, `test_frame_test_tools.py`,
`test_gray_variant.py`, `test_label_events.py`, `test_label_events_packet.py`,
`test_leakcheck.py`, `test_metrics_eval_events.py`,
`test_metrics_protocol_lock.py`, `test_pack_dataset.py`, `test_relist_dataset.py`,
`test_stats.py`, `test_t1_dev.py`, `test_train_notebook.py`,
`test_train_script.py`, `test_video_segments.py`.

## Phần nhập thêm sau đó (2026-11-07, bảo trì)

Cùng commit nguồn `afa5a70`. Không file nào được chép nguyên: tài liệu được viết lại theo
mã hiện tại, script được chép rồi sửa docstring.

| Nguồn @ `afa5a70` | Đích trong `FireWatchAI/` | Sửa gì |
|---|---|---|
| `README.md` mục 3, 3b, 4 | `docs/ban_giao_backend.md` | đối chiếu lại với `alerts.py`, `server.py`; bỏ số đo độ trễ Gemini và đường dẫn `reports/` của repo cũ; thêm mục verifier sau cờ |
| `README.md` mục 1, 2, 3, 5, 6 và phần nguồn live ở mục 8 | `docs/van_hanh.md` | trọng số theo FireWatch-v2.0; bỏ bảng nghiệm thu đo bằng model cũ và đường dẫn clip mẫu; đánh giá trỏ sang R3 của FireWatch-Model |
| `README.md` mục 7 | `docs/kien_truc.md` | viết theo bố cục `FireWatchAI/` hiện tại; thêm mục thay đổi so với sơ đồ 05/11 |
| `README.md` mục 8 | `docs/decisions/2026-11-06-quyet-dinh-thiet-ke-goc.md` | ba chỗ sửa ghi ở cuối file đó |
| `scripts/annotate_video.py` | `tools/annotate_video.py` | chỉ sửa docstring (đường dẫn script và tên weights) |

Không nhập lần này: các script, tài liệu, dữ liệu và báo cáo thuộc phần benchmark. Bốn
file trong số đó chưa có chỗ ở FireWatch-Model, ghi ở `docs/ton_dong.md`.

## Đối chiếu SHA-256 ba module lõi

SHA-256 tính trên nội dung file đã commit (xuống dòng LF), lấy bằng
`git show <commit>:<đường dẫn> | sha256sum`.

- Cột 1: `Model-Mat-Pho-` @ `afa5a70`, đường dẫn `src/firewatch/<file>`.
- Cột 2: repo này @ `7d29bca`, đường dẫn `src/firewatch/<file>` (trước khi dời; sau
  khi dời sang `FireWatchAI/src/firewatch/<file>` nội dung không đổi).
- Cột 3: `MinhTrietNg/FireWatch-Model` @ `f61f8f2468ef98ed23fbcf4822a7d79bf8a9942b`,
  đường dẫn `src/firewatch/<file>`.

| File | `afa5a70` | Repo này | `FireWatch-Model` |
|---|---|---|---|
| `voting.py` | `6b240a94226423f69b3d95957f260224fac1c256772399784af7bc6df9ac4d13` | `6b240a94226423f69b3d95957f260224fac1c256772399784af7bc6df9ac4d13` | `6b240a94226423f69b3d95957f260224fac1c256772399784af7bc6df9ac4d13` |
| `detector.py` | `0f672680cff5f4c0cdea1bbc634ef84235e66d24d1ca10cf4d86faf6f7be4b78` | `0f672680cff5f4c0cdea1bbc634ef84235e66d24d1ca10cf4d86faf6f7be4b78` | `0f672680cff5f4c0cdea1bbc634ef84235e66d24d1ca10cf4d86faf6f7be4b78` |
| `sources.py` | `80403f957065336d62e0e94a5814ca250338bfbb11c0cdb31fce670ec83b2732` | `80403f957065336d62e0e94a5814ca250338bfbb11c0cdb31fce670ec83b2732` | `80403f957065336d62e0e94a5814ca250338bfbb11c0cdb31fce670ec83b2732` |

Ba cột trùng nhau ở cả ba file.

## Kiểm lại

Trước khi có `.gitattributes`, `core.autocrlf=true` làm bản checkout trên Windows
có CRLF, nên hash file trên đĩa lệch với bảng trên dù nội dung commit trùng. Từ
commit thêm `.gitattributes` (`* text=auto eol=lf`), bản checkout giữ LF và có thể
kiểm trực tiếp:

```bash
sha256sum EdgeAI-MatPho/FireWatchAI/src/firewatch/{voting,detector,sources}.py
```
