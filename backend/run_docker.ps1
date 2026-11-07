# ==============================================================================
# MAT PHO - SCRIPT TU DONG KHOI CHAY BACKEND DOCKER (POWERSHELL)
# ==============================================================================

[CmdletBinding()]
param (
    [switch]$Build,        # Buoc build lai Docker Image truoc khi chay
    [switch]$Down,         # Tat va don dep cac container
    [switch]$Restart,      # Khoi dong lai cum container
    [switch]$Logs,         # Xem log thoi gian thuc cua backend
    [switch]$Status        # Kiem tra trang thai cac container
)

# Luon chay tai thu muc backend chua docker-compose.yml
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Xu ly cac co thao tac nhanh (Quick actions)
if ($Down) {
    Write-Host "[DOCKER] Dang tat cum dich vu Backend..." -ForegroundColor Yellow
    docker compose down --remove-orphans
    Write-Host "[DOCKER] Da dung toan bo dich vu." -ForegroundColor Green
    exit 0
}

if ($Logs) {
    docker compose logs -f backend
    exit 0
}

if ($Status) {
    docker compose ps
    exit 0
}

if ($Restart) {
    Write-Host "[DOCKER] Dang khoi dong lai cum dich vu Backend..." -ForegroundColor Yellow
    docker compose down
    docker compose up -d
    Write-Host "[DOCKER] Da khoi dong lai thanh cong!" -ForegroundColor Green
    exit 0
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   MAT PHO AI SURVEILLANCE PLATFORM - TU DONG CHAY BACKEND DOCKER    " -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Kiem tra Docker Daemon
# ------------------------------------------------------------------------------
Write-Host "[1/5] Kiem tra dich vu Docker Engine..." -ForegroundColor White
$dockerRunning = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
    }
} catch {
    $dockerRunning = $false
}

if (-not $dockerRunning) {
    Write-Host "   [LOI] Docker Desktop chua duoc bat hoac chua duoc cai dat!" -ForegroundColor Red
    Write-Host "   -> Vui long khoi dong Docker Desktop tren may va chay lai script nay." -ForegroundColor Yellow
    exit 1
}
Write-Host "   [OK] Docker Desktop dang hoat dong binh thuong!" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 2. Kiem tra va chuan bi file .env
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/5] Kiem tra cau hinh moi truong (.env)..." -ForegroundColor White
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "   [OK] Da tu dong tao file .env tu .env.example!" -ForegroundColor Green
    } else {
        Write-Host "   [CANH BAO] Khong tim thay .env.example de tao .env!" -ForegroundColor Yellow
    }
} else {
    Write-Host "   [OK] File .env da ton tai san sang." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 3. Kiem tra chia khoa Firebase Service Account
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/5] Kiem tra chia khoa Firebase Service Account..." -ForegroundColor White
$credPath = "credentials/firebase-service-account.json"
if (-not (Test-Path $credPath)) {
    Write-Host "   [CANH BAO] Chua tim thay file '$credPath'!" -ForegroundColor Yellow
    Write-Host "   -> Vui long dat file Service Account JSON vao thu muc credentials/ de ket noi Firebase." -ForegroundColor Yellow
} else {
    Write-Host "   [OK] Da tim thay chia khoa Firebase Service Account hop le." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 4. Khoi dong Docker Compose
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/5] Dang khoi dong cac container (Backend, Redis, MediaMTX)..." -ForegroundColor White

if ($Build) {
    Write-Host "   -> Dang build lai Docker image theo yeu cau (-Build)..." -ForegroundColor Cyan
    docker compose up -d --build --remove-orphans
} else {
    docker compose up -d --remove-orphans
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "   [LOI] Khoi dong Docker Compose that bai!" -ForegroundColor Red
    exit 1
}

# Cho Backend Healthcheck san sang
Write-Host "   Dang cho Backend khoi dong va kiem tra suc khoe (/health)..." -ForegroundColor Gray
$backendReady = $false
$maxRetries = 20

for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($resp -and ($resp.status -eq "ok" -or $resp.status -eq "healthy" -or $resp.status -eq "degraded")) {
            $backendReady = $true
            break
        }
    } catch {
        try {
            $rootResp = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($rootResp -and $rootResp.status -eq "ok") {
                $backendReady = $true
                break
            }
        } catch {}
    }
    Start-Sleep -Seconds 2
    Write-Host "." -NoNewline -ForegroundColor Gray
}
Write-Host ""

if ($backendReady) {
    Write-Host "   [OK] Backend da san sang phan hoi tai cong 8000!" -ForegroundColor Green
} else {
    Write-Host "   [CANH BAO] Backend dang mat nhieu thoi gian hon de khoi dong." -ForegroundColor Yellow
    Write-Host "   -> Ban co the xem log chi tiet bang lenh: .\run_docker.ps1 -Logs" -ForegroundColor Yellow
}

# ------------------------------------------------------------------------------
# 5. Kiem tra kich ban nap du lieu mau Firestore (Neu co script seed)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[5/5] Kiem tra kich ban nap du lieu mau (Seed Data)..." -ForegroundColor White
$seedScript = if (Test-Path "scripts/clean_and_seed_db.py") { "scripts/clean_and_seed_db.py" } elseif (Test-Path "scripts/init_firestore_db.py") { "scripts/init_firestore_db.py" } else { $null }
if ($seedScript) {
    try {
        Write-Host "   -> Dang chay nap du lieu mau ($seedScript)..." -ForegroundColor Cyan
        docker compose exec -T backend python $seedScript
        Write-Host "   [OK] Nap du lieu mau hoan tat!" -ForegroundColor Green
    } catch {
        Write-Host "   [CANH BAO] Khong the nap du lieu mau tu dong." -ForegroundColor Yellow
    }
} else {
    Write-Host "   [INFO] Chua co script seed du lieu (Bo qua buoc nap)." -ForegroundColor Gray
}

# ------------------------------------------------------------------------------
# Hoan tat & Hien thi thong tin dich vu
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  CHUC MUNG: HE THONG BACKEND DA DUOC KHOI CHAY THANH CONG!          " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Dia chi API:          http://localhost:8000/api/v1" -ForegroundColor White
Write-Host "Tai lieu Swagger:     http://localhost:8000/docs" -ForegroundColor White
Write-Host "Kiem tra suc khoe:    http://localhost:8000/api/v1/health" -ForegroundColor White
Write-Host "Cong Redis Cache:     localhost:6379" -ForegroundColor White
Write-Host "Media Server MediaMTX:" -ForegroundColor White
Write-Host "   - RTSP Ingest:        rtsp://localhost:8554" -ForegroundColor Gray
Write-Host "   - HLS Playback:       http://localhost:8888" -ForegroundColor Gray
Write-Host "   - WebRTC / WHEP:      http://localhost:8889" -ForegroundColor Gray
Write-Host "   - Control REST API:   http://localhost:9997" -ForegroundColor Gray
Write-Host ""
Write-Host "CAC LENH TIEN ICH HUU ICH:" -ForegroundColor Yellow
Write-Host "   - Xem log Backend:    .\run_docker.ps1 -Logs" -ForegroundColor Cyan
Write-Host "   - Kiem tra trang thai:.\run_docker.ps1 -Status" -ForegroundColor Cyan
Write-Host "   - Khoi dong lai:      .\run_docker.ps1 -Restart" -ForegroundColor Cyan
Write-Host "   - Tat he thong:       .\run_docker.ps1 -Down" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
