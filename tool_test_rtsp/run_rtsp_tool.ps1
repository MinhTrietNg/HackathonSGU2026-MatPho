# Mắt Phố - RTSP Virtual Camera Fleet Studio (PowerShell Launcher)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "          MẮT PHỐ - RTSP VIRTUAL CAMERA FLEET STUDIO                  " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$PythonCandidates = @(
    "D:\Project\Team_Project\NOD89\MatPho-Draft\backend\.venv\Scripts\python.exe",
    "$ProjectRoot\.venv\Scripts\python.exe",
    "python.exe"
)

$PythonExe = $null
foreach ($cand in $PythonCandidates) {
    if (Test-Path $cand) {
        $PythonExe = $cand
        break
    }
}

if (-not $PythonExe) {
    $PythonExe = "python"
}

Write-Host "[INFO] Sử dụng Python: $PythonExe" -ForegroundColor Yellow
Write-Host "[INFO] Đang khởi chạy Giao diện RTSP Studio..." -ForegroundColor Yellow
Write-Host ""

$env:PYTHONPATH = "."
& $PythonExe -m tool_test_rtsp.src.gui_app

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Đã xảy ra lỗi khi khởi chạy Studio (Exit code: $LASTEXITCODE)" -ForegroundColor Red
    pause
}
