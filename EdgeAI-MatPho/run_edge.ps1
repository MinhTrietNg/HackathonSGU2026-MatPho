<#
.SYNOPSIS
    Script điều khiển Docker cho khối EdgeAI-MatPho (MediaMTX + Edge Backend + FireWatch AI + Mock Cam).
.DESCRIPTION
    Hỗ trợ khởi chạy nhanh, theo dõi logs, kiểm tra sức khỏe và chạy luồng camera giả lập.
.EXAMPLE
    .\run_edge.ps1 up          # Khởi chạy cụm Edge tiêu chuẩn (3 containers)
    .\run_edge.ps1 up-mock     # Khởi chạy kèm camera giả lập (--profile mock)
    .\run_edge.ps1 down        # Dừng toàn bộ cụm Edge
    .\run_edge.ps1 restart     # Khởi động lại
    .\run_edge.ps1 logs        # Xem logs trực tiếp
    .\run_edge.ps1 status      # Kiểm tra trạng thái và healthcheck
    .\run_edge.ps1 clean       # Dọn dẹp sạch containers & volumes
    .\run_edge.ps1             # Mở menu tương tác
#>

[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [ValidateSet("up", "up-mock", "mock", "start", "down", "stop", "restart", "logs", "status", "ps", "clean", "")]
    [string]$Command = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# --- Color helper functions ---
function Write-Header {
    param ([string]$Text)
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Yellow -BackgroundColor Black
    Write-Host "======================================================================" -ForegroundColor Cyan
}

function Write-Success {
    param ([string]$Text)
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-Warn {
    param ([string]$Text)
    Write-Host "[CẢNH BÁO] $Text" -ForegroundColor Yellow
}

function Write-Info {
    param ([string]$Text)
    Write-Host "[THÔNG TIN] $Text" -ForegroundColor Cyan
}

function Write-Fail {
    param ([string]$Text)
    Write-Host "[LỖI] $Text" -ForegroundColor Red
}

# --- Check Docker Prerequisites ---
function Assert-DockerRunning {
    Write-Info "Đang kiểm tra Docker daemon..."
    try {
        $null = docker info 2>&1
        Write-Success "Docker engine đang hoạt động."
    } catch {
        Write-Fail "Không thể kết nối đến Docker daemon!"
        Write-Host "  -> Vui lòng bật Docker Desktop trên máy tính rồi thử lại." -ForegroundColor Yellow
        exit 1
    }
}

# --- Ensure .env file exists ---
function Ensure-EnvFile {
    $envPath = Join-Path $ScriptDir ".env"
    $examplePath = Join-Path $ScriptDir ".env.example"

    if (-not (Test-Path $envPath)) {
        if (Test-Path $examplePath) {
            Copy-Item -Path $examplePath -Destination $envPath
            Write-Success "Đã tự động khởi tạo file .env từ .env.example."
        } else {
            Write-Warn "Không tìm thấy file .env.example để khởi tạo .env!"
        }
    } else {
        Write-Success "Đã nạp cấu hình từ .env."
    }
}

# --- Check Port Conflicts (e.g. backend mediamtx container) ---
function Check-PortConflicts {
    try {
        $runningContainers = docker ps --format "{{.Names}} {{.Ports}}" 2>$null
        if ($runningContainers -match "matpho_mediamtx" -or $runningContainers -match "8554->8554") {
            Write-Warn "Phát hiện port 8554/8888 đang được dùng bởi container khác (ví dụ: matpho_mediamtx của Backend)."
            Write-Host "  * Nếu muốn Edge dùng port mặc định, hãy tạm dừng container đó:" -ForegroundColor Gray
            Write-Host "    docker stop matpho_mediamtx" -ForegroundColor DarkYellow
            Write-Host "  * Hoặc đổi MEDIAMTX_RTSP_PORT/MEDIAMTX_HLS_PORT trong file .env của EdgeAI-MatPho." -ForegroundColor Gray
            Write-Host ""
        }
    } catch {
        # ignore check failure
    }
}

# --- Display Service Endpoints ---
function Show-Endpoints {
    param([bool]$WithMock = $false)
    Write-Header "THÔNG TIN CỔNG DỊCH VỤ KHỐI EDGE (EdgeAI-MatPho)"
    Write-Host "  * RTSP Media Server  : " -NoNewline; Write-Host "rtsp://localhost:8554/live/cam_01" -ForegroundColor Green
    Write-Host "  * HLS Mobile Stream  : " -NoNewline; Write-Host "http://localhost:8888/live/cam_01/index.m3u8" -ForegroundColor Green
    Write-Host "  * WebRTC WHEP Stream : " -NoNewline; Write-Host "http://localhost:8889/live/cam_01" -ForegroundColor Green
    Write-Host "  * Edge Controller API: " -NoNewline; Write-Host "http://localhost:8090/docs" -ForegroundColor Cyan
    Write-Host "  * Health Check API   : " -NoNewline; Write-Host "http://localhost:8090/api/v1/edge/health" -ForegroundColor Cyan
    Write-Host "  * MediaMTX Control   : " -NoNewline; Write-Host "http://localhost:9997/v3/config/paths/list" -ForegroundColor Gray
    if ($WithMock) {
        Write-Host "  * Camera Giả Lập     : " -NoNewline; Write-Host "rtsp://localhost:8554/mock/cam_test (ĐANG BƠM LUỒNG SỐ BẬT OSD)" -ForegroundColor Magenta
    }
    Write-Host "----------------------------------------------------------------------" -ForegroundColor Cyan
}

# --- Actions ---
function Start-Edge {
    param([bool]$IncludeMock = $false)
    Assert-DockerRunning
    Ensure-EnvFile
    Check-PortConflicts

    if ($IncludeMock) {
        Write-Header "KHỞI CHẠY KHỐI EDGE KÈM CAMERA GIẢ LẬP (--profile mock)"
        docker compose --profile mock up -d --build
    } else {
        Write-Header "KHỞI CHẠY KHỐI EDGE TIÊU CHUẨN (3 CONTAINERS)"
        docker compose up -d --build
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Toàn bộ containers khối Edge đã được khởi chạy thành công!"
        Start-Sleep -Seconds 2
        Show-Endpoints -WithMock $IncludeMock
    } else {
        Write-Fail "Khởi chạy thất bại! Vui lòng kiểm tra lỗi bên trên."
    }
}

function Stop-Edge {
    Assert-DockerRunning
    Write-Header "DỪNG TOÀN BỘ CỤM EDGE (EdgeAI-MatPho)"
    docker compose --profile mock down
    Write-Success "Đã dừng và giải phóng toàn bộ containers khối Edge."
}

function Restart-Edge {
    Assert-DockerRunning
    Write-Header "KHỞI ĐỘNG LẠI KHỐI EDGE"
    docker compose --profile mock down
    Ensure-EnvFile
    docker compose up -d --build
    Write-Success "Đã khởi động lại cụm Edge."
    Show-Endpoints
}

function Show-Logs {
    Assert-DockerRunning
    Write-Header "XEM LOGS TRỰC TIẾP KHỐI EDGE (Ctrl+C để thoát)"
    docker compose --profile mock logs -f --tail 100
}

function Show-Status {
    Assert-DockerRunning
    Write-Header "TRẠNG THÁI CONTAINERS KHỐI EDGE"
    docker compose --profile mock ps

    Write-Host ""
    Write-Info "Kiểm tra phản hồi Healthcheck từ Edge Backend (:8090)..."
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:8090/api/v1/edge/health" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
        Write-Success "Edge Backend Health: $($res | ConvertTo-Json -Compress)"
    } catch {
        Write-Warn "Chưa kết nối được http://localhost:8090/api/v1/edge/health (Container có thể đang khởi động)."
    }

    Write-Info "Kiểm tra phản hồi MediaMTX API (:9997)..."
    try {
        $res2 = Invoke-RestMethod -Uri "http://localhost:9997/v3/config/paths/list" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
        $pathCount = $res2.itemCount
        Write-Success "MediaMTX Paths Active: $pathCount path(s)."
    } catch {
        Write-Warn "Chưa kết nối được http://localhost:9997 (MediaMTX có thể chưa sẵn sàng)."
    }
}

function Clean-Edge {
    Assert-DockerRunning
    Write-Header "DỌN DẸP SẠCH CỤM EDGE (XÓA VOLUMES DỮ LIỆU SQLITE)"
    $confirm = Read-Host "Bạn có chắc chắn muốn xóa toàn bộ containers và volumes dữ liệu SQLite không? (y/N)"
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        docker compose --profile mock down -v --remove-orphans
        Write-Success "Đã xóa toàn bộ containers, mạng và volume matpho_edge_local_data."
    } else {
        Write-Info "Đã hủy thao tác dọn dẹp."
    }
}

# --- Interactive Menu ---
function Show-Menu {
    while ($true) {
        Write-Header "MENU QUẢN LÝ DOCKER KHỐI EDGEAI-MATPHO"
        Write-Host "  1. Khởi chạy cụm Edge tiêu chuẩn       (docker compose up -d --build)" -ForegroundColor Green
        Write-Host "  2. Khởi chạy KÈM Camera Giả Lập        (docker compose --profile mock up -d)" -ForegroundColor Magenta
        Write-Host "  3. Xem Logs thời gian thực             (docker compose logs -f)" -ForegroundColor Cyan
        Write-Host "  4. Kiểm tra trạng thái & Sức khỏe      (docker compose ps & healthcheck)" -ForegroundColor Yellow
        Write-Host "  5. Khởi động lại cụm Edge              (docker compose restart)" -ForegroundColor White
        Write-Host "  6. Dừng cụm Edge                       (docker compose down)" -ForegroundColor DarkYellow
        Write-Host "  7. Dọn dẹp sạch (Xóa Containers & Vol) (docker compose down -v)" -ForegroundColor Red
        Write-Host "  0. Thoát" -ForegroundColor Gray
        Write-Host "----------------------------------------------------------------------" -ForegroundColor Cyan
        
        $choice = Read-Host "Lựa chọn của bạn [0-7]"
        switch ($choice) {
            "1" { Start-Edge -IncludeMock $false; break }
            "2" { Start-Edge -IncludeMock $true; break }
            "3" { Show-Logs; break }
            "4" { Show-Status; break }
            "5" { Restart-Edge; break }
            "6" { Stop-Edge; break }
            "7" { Clean-Edge; break }
            "0" { Write-Info "Tạm biệt!"; exit 0 }
            default { Write-Warn "Lựa chọn không hợp lệ. Vui lòng thử lại!" }
        }
    }
}

# --- Command Router ---
switch ($Command.ToLower()) {
    "up"       { Start-Edge -IncludeMock $false }
    "start"    { Start-Edge -IncludeMock $false }
    "up-mock"  { Start-Edge -IncludeMock $true }
    "mock"     { Start-Edge -IncludeMock $true }
    "down"     { Stop-Edge }
    "stop"     { Stop-Edge }
    "restart"  { Restart-Edge }
    "logs"     { Show-Logs }
    "status"   { Show-Status }
    "ps"       { Show-Status }
    "clean"    { Clean-Edge }
    default    { Show-Menu }
}
