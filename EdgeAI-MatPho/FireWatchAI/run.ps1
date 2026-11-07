# Chạy FireWatch trên Windows sau khi kiểm SHA-256 trọng số theo models/README.md.
# Sai hoặc thiếu file .pt thì dừng, không chạy. Mọi tham số chuyển nguyên cho
# "python -m firewatch", ví dụ:
#   .\run.ps1 serve --source rtsp://camera/stream
#   .\run.ps1 --set vlm.provider=mock run --source clip.mp4
# Đặt $env:FIREWATCH_SOURCE thì "serve" không kèm --source sẽ chạy trên nguồn đó.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = "1"

# Trình thông dịch: $env:FIREWATCH_PYTHON nếu đặt, rồi .venv của thư mục này, rồi python.
$py = $env:FIREWATCH_PYTHON
if (-not $py) {
    $py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
}

& $py tools\kiem_trong_so.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$thamSo = @($args)
if (($thamSo -contains "serve") -and -not ($thamSo -contains "--source") -and
        $env:FIREWATCH_SOURCE) {
    $thamSo += @("--source", $env:FIREWATCH_SOURCE)
}

& $py -m firewatch @thamSo
exit $LASTEXITCODE
