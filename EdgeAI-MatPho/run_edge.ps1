<#
.SYNOPSIS
    Script dieu khien Docker cho khoi EdgeAI-MatPho (MediaMTX + Edge Backend + FireWatch AI + Mock Cam).
.DESCRIPTION
    Ho tro khoi chay nhanh, theo doi logs, kiem tra suc khoe va chay luong camera gia lap.
.EXAMPLE
    .\run_edge.ps1 up          # Khoi chay cum Edge tieu chuan (3 containers)
    .\run_edge.ps1 up-mock     # Khoi chay kem camera gia lap (--profile mock)
    .\run_edge.ps1 down        # Dung toan bo cum Edge
    .\run_edge.ps1 restart     # Khoi dong lai
    .\run_edge.ps1 logs        # Xem logs truc tiep
    .\run_edge.ps1 status      # Kiem tra trang thai va healthcheck
    .\run_edge.ps1 clean       # Don dep sach containers va volumes
    .\run_edge.ps1             # Mo menu tuong tac
#>

[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [ValidateSet("up", "up-mock", "mock", "up-gateway", "gateway", "start", "down", "stop", "restart", "logs", "status", "ps", "clean", "")]
    [string]$Command = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# --- Helper functions ---
function Write-Header {
    param ([string]$Text)
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Yellow
    Write-Host "======================================================================" -ForegroundColor Cyan
}

function Write-Success {
    param ([string]$Text)
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-Warn {
    param ([string]$Text)
    Write-Host "[CANH BAO] $Text" -ForegroundColor Yellow
}

function Write-Info {
    param ([string]$Text)
    Write-Host "[THONG TIN] $Text" -ForegroundColor Cyan
}

function Write-Fail {
    param ([string]$Text)
    Write-Host "[LOI] $Text" -ForegroundColor Red
}

# --- Check Docker Prerequisites ---
function Assert-DockerRunning {
    Write-Info "Dang kiem tra Docker daemon..."
    try {
        $null = docker info 2>&1
        Write-Success "Docker engine dang hoat dong."
    } catch {
        Write-Fail "Khong the ket noi den Docker daemon!"
        Write-Host "  -> Vui long bat Docker Desktop tren may tinh roi thu lai." -ForegroundColor Yellow
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
            Write-Success "Da tu dong khoi tao file .env tu .env.example."
        } else {
            Write-Warn "Khong tim thay file .env.example de khoi tao .env!"
        }
    } else {
        Write-Success "Da nap cau hinh tu file .env."
    }
}

# --- Check Port Conflicts (e.g. backend mediamtx container) ---
function Check-PortConflicts {
    try {
        $running = docker ps --format "{{.Names}} {{.Ports}}" 2>$null
        if ($running -match "matpho_mediamtx" -or $running -match "8554->8554") {
            Write-Warn "Phat hien port 8554/8888 dang duoc dung boi container khac (vi du: matpho_mediamtx cua Backend)."
            Write-Host "  * Neu muon Edge dung port mac dinh, hay tam dung container do:" -ForegroundColor Gray
            Write-Host "    docker stop matpho_mediamtx" -ForegroundColor DarkYellow
            Write-Host "  * Hoac doi MEDIAMTX_RTSP_PORT/MEDIAMTX_HLS_PORT trong file .env cua EdgeAI-MatPho." -ForegroundColor Gray
            Write-Host ""
        }
    } catch {
        # ignore
    }
}

# --- Display Service Endpoints ---
function Show-Endpoints {
    param([bool]$WithMock = $false)
    Write-Header "THONG TIN CONG DICH VU KHOI EDGE (EdgeAI-MatPho)"
    Write-Host "  * RTSP Media Server  : " -NoNewline; Write-Host "rtsp://localhost:8554/live/cam_01" -ForegroundColor Green
    Write-Host "  * HLS Mobile Stream  : " -NoNewline; Write-Host "http://localhost:8888/live/cam_01/index.m3u8" -ForegroundColor Green
    Write-Host "  * WebRTC WHEP Stream : " -NoNewline; Write-Host "http://localhost:8889/live/cam_01" -ForegroundColor Green
    Write-Host "  * Edge Controller API: " -NoNewline; Write-Host "http://localhost:8090/docs" -ForegroundColor Cyan
    Write-Host "  * Health Check API   : " -NoNewline; Write-Host "http://localhost:8090/api/v1/edge/health" -ForegroundColor Cyan
    Write-Host "  * MediaMTX Control   : " -NoNewline; Write-Host "http://localhost:9997/v3/config/paths/list" -ForegroundColor Gray
    if ($WithMock) {
        Write-Host "  * Camera Gia Lap OSD : " -NoNewline; Write-Host "rtsp://localhost:8554/mock/cam_test (DANG PHAT)" -ForegroundColor Magenta
    }
    Write-Host "----------------------------------------------------------------------" -ForegroundColor Cyan
}

# --- Actions ---
function Start-Edge {
    param(
        [bool]$IncludeMock = $false,
        [bool]$IncludeGateway = $false
    )
    Assert-DockerRunning
    Ensure-EnvFile
    Check-PortConflicts

    $profiles = @()
    if ($IncludeMock) { $profiles += "--profile", "mock" }
    if ($IncludeGateway) { $profiles += "--profile", "gateway" }

    if ($IncludeGateway) {
        Write-Header "KHOI CHAY KHOI EDGE KEM HTTPS GATEWAY (CLOUDFLARE TUNNEL)"
    } elseif ($IncludeMock) {
        Write-Header "KHOI CHAY KHOI EDGE KEM CAMERA GIA LAP (--profile mock)"
    } else {
        Write-Header "KHOI CHAY KHOI EDGE TIEU CHUAN (3 CONTAINERS)"
    }

    if ($profiles.Count -gt 0) {
        docker compose $profiles up -d --build
    } else {
        docker compose up -d --build
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Toan bo containers khoi Edge da duoc khoi chay thanh cong!"
        Start-Sleep -Seconds 2
        Show-Endpoints -WithMock $IncludeMock
    } else {
        Write-Fail "Khoi chay that bai! Vui long kiem tra loi ben tren."
    }
}

function Stop-Edge {
    Assert-DockerRunning
    Write-Header "DUNG TOAN BO CUM EDGE (EdgeAI-MatPho)"
    docker compose --profile mock down
    Write-Success "Da dung toan bo containers khoi Edge."
}

function Restart-Edge {
    Assert-DockerRunning
    Write-Header "KHOI DONG LAI KHOI EDGE"
    docker compose --profile mock down
    Ensure-EnvFile
    docker compose up -d --build
    Write-Success "Da khoi dong lai cum Edge."
    Show-Endpoints
}

function Show-Logs {
    Assert-DockerRunning
    Write-Header "XEM LOGS TRUC TIEP (Ctrl+C de thoat)"
    docker compose --profile mock logs -f --tail 100
}

function Show-Status {
    Assert-DockerRunning
    Write-Header "TRANG THAI CONTAINERS KHOI EDGE"
    docker compose --profile mock ps

    Write-Host ""
    Write-Info "Kiem tra phan hoi Healthcheck tu Edge Backend (:8090)..."
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:8090/api/v1/edge/health" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
        Write-Success "Edge Backend Health: $($res | ConvertTo-Json -Compress)"
    } catch {
        Write-Warn "Chua ket noi duoc http://localhost:8090/api/v1/edge/health (Container co the dang khoi dong)."
    }

    Write-Info "Kiem tra phan hoi MediaMTX API (:9997)..."
    try {
        $res2 = Invoke-RestMethod -Uri "http://localhost:9997/v3/config/paths/list" -Method Get -TimeoutSec 3 -ErrorAction SilentlyContinue
        $pathCount = $res2.itemCount
        Write-Success "MediaMTX Paths Active: $pathCount path(s)."
    } catch {
        Write-Warn "Chua ket noi duoc http://localhost:9997 (MediaMTX co the chua san sang)."
    }
}

function Clean-Edge {
    Assert-DockerRunning
    Write-Header "DON DEP SACH CUM EDGE (XOA VOLUMES DU LIEU SQLITE)"
    $confirm = Read-Host "Ban co chac muon xoa toan bo containers va volumes SQLite? (y/N)"
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        docker compose --profile mock down -v --remove-orphans
        Write-Success "Da xoa toan bo containers, network va volumes matpho_edge_local_data."
    } else {
        Write-Info "Da huy thao tac don dep."
    }
}

# --- Interactive Menu ---
function Show-Menu {
    while ($true) {
        Write-Header "MENU QUAN LY DOCKER KHOI EDGEAI-MATPHO"
        Write-Host "  1. Khoi chay cum Edge tieu chuan       (docker compose up -d --build)" -ForegroundColor Green
        Write-Host "  2. Khoi chay KEM Camera Gia Lap        (docker compose --profile mock up -d)" -ForegroundColor Magenta
        Write-Host "  3. Xem Logs thoi gian thuc             (docker compose logs -f)" -ForegroundColor Cyan
        Write-Host "  4. Kiem tra trang thai va Suc khoe     (docker compose ps va healthcheck)" -ForegroundColor Yellow
        Write-Host "  5. Khoi dong lai cum Edge              (docker compose restart)" -ForegroundColor White
        Write-Host "  6. Dung cum Edge                       (docker compose down)" -ForegroundColor DarkYellow
        Write-Host "  7. Don dep sach (Xoa Containers & Vol) (docker compose down -v)" -ForegroundColor Red
        Write-Host "  0. Thoat" -ForegroundColor Gray
        Write-Host "----------------------------------------------------------------------" -ForegroundColor Cyan
        
        $choice = Read-Host "Nhap lua chon cua ban [0-7]"
        switch ($choice) {
            "1" { Start-Edge -IncludeMock $false; break }
            "2" { Start-Edge -IncludeMock $true; break }
            "3" { Show-Logs; break }
            "4" { Show-Status; break }
            "5" { Restart-Edge; break }
            "6" { Stop-Edge; break }
            "7" { Clean-Edge; break }
            "0" { Write-Info "Tam biet!"; exit 0 }
            default { Write-Warn "Lua chon khong hop le. Vui long thu lai!" }
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
