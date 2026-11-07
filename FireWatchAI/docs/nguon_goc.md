# Nguồn gốc mã FireWatch trong repo này

## Nhập từ đâu, khi nào

| Mục | Giá trị |
|---|---|
| Repo nguồn | `MinhTrietNg/Model-Mat-Pho-` |
| Commit nguồn | `afa5a70788ebd872b0523cc722f4c372e4f7f6c4` (2026-11-06 15:25 +0700) |
| Ngày nhập | 2026-11-07 |
| Commit nhập | `42b9f631602d21128ba0342b82e03c850aa279da` ("Nhập mã nguồn FireWatch làm bản gốc của repo") |
| Vị trí hiện tại | thư mục `FireWatchAI/` (dời từ gốc repo sang `ai/` ở commit đổi bố cục, sau đó đổi tên `ai/` thành `FireWatchAI/`) |

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
sha256sum FireWatchAI/src/firewatch/{voting,detector,sources}.py
```
