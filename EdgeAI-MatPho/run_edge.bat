@echo off
REM ==============================================================================
REM Mắt Phố - Windows Batch Launcher for EdgeAI-MatPho Docker Stack
REM ==============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CLI_MODE=0"
if not "%1"=="" set "CLI_MODE=1"

if "%1"=="" goto menu
if /i "%1"=="up" goto up
if /i "%1"=="start" goto up
if /i "%1"=="up-mock" goto up_mock
if /i "%1"=="mock" goto up_mock
if /i "%1"=="down" goto down
if /i "%1"=="stop" goto down
if /i "%1"=="restart" goto restart
if /i "%1"=="logs" goto logs
if /i "%1"=="status" goto status
if /i "%1"=="ps" goto status
if /i "%1"=="clean" goto clean

:menu
cls
echo ======================================================================
echo   MENU QUAN LY DOCKER KHOI EDGEAI-MATPHO (WINDOWS)
echo ======================================================================
echo   1. Khoi chay cum Edge tieu chuan (3 containers)
echo   2. Khoi chay KEM Camera Gia Lap (Mock Counter OSD)
echo   3. Xem Logs truc tiep (docker compose logs -f)
echo   4. Kiem tra trang thai & Suc khoe
echo   5. Khoi dong lai cum Edge
echo   6. Dung toan bo cum Edge
echo   7. Don dep sach (Xoa Containers & Volumes)
echo   0. Thoat
echo ======================================================================
set /p choice="Nhap lua chon cua ban [0-7]: "

if "%choice%"=="1" goto up
if "%choice%"=="2" goto up_mock
if "%choice%"=="3" goto logs
if "%choice%"=="4" goto status
if "%choice%"=="5" goto restart
if "%choice%"=="6" goto down
if "%choice%"=="7" goto clean
if "%choice%"=="0" goto exit
goto menu

:check_env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Da tu dong khoi tao file .env tu .env.example.
    )
)
goto :eof

:up
echo.
echo [1/3] Kiem tra moi truong...
call :check_env
echo [2/3] Dang khoi chay Docker Containers...
docker compose up -d --build
if errorlevel 1 (
    echo [LOI] Khong the khoi chay Docker. Vui long kiem tra Docker Desktop!
    if "%CLI_MODE%"=="0" pause
    goto exit
)
echo [3/3] Thanh cong!
goto endpoints

:up_mock
echo.
echo [1/3] Kiem tra moi truong...
call :check_env
echo [2/3] Dang khoi chay Docker Containers kem Mock Camera...
docker compose --profile mock up -d --build
if errorlevel 1 (
    echo [LOI] Khong the khoi chay Docker. Vui long kiem tra Docker Desktop!
    if "%CLI_MODE%"=="0" pause
    goto exit
)
echo [3/3] Thanh cong!
goto endpoints_mock

:endpoints
echo.
echo ======================================================================
echo   THONG TIN CONG DICH VU KHOI EDGE (EdgeAI-MatPho)
echo ======================================================================
echo   * RTSP Media Server  : rtsp://localhost:8554/live/cam_01
echo   * HLS Mobile Stream  : http://localhost:8888/live/cam_01/index.m3u8
echo   * WebRTC Stream      : http://localhost:8889/live/cam_01
echo   * Edge Controller API: http://localhost:8090/docs
echo   * Health Check API   : http://localhost:8090/api/v1/edge/health
echo   * MediaMTX Control   : http://localhost:9997/v3/config/paths/list
echo ======================================================================
if "%CLI_MODE%"=="0" pause
goto exit

:endpoints_mock
echo.
echo ======================================================================
echo   THONG TIN CONG DICH VU KHOI EDGE (EdgeAI-MatPho)
echo ======================================================================
echo   * RTSP Media Server  : rtsp://localhost:8554/live/cam_01
echo   * HLS Mobile Stream  : http://localhost:8888/live/cam_01/index.m3u8
echo   * WebRTC Stream      : http://localhost:8889/live/cam_01
echo   * Edge Controller API: http://localhost:8090/docs
echo   * Health Check API   : http://localhost:8090/api/v1/edge/health
echo   * Camera Gia Lap OSD : rtsp://localhost:8554/mock/cam_test (DANG PHAT)
echo ======================================================================
if "%CLI_MODE%"=="0" pause
goto exit

:down
echo.
echo Dang dung toan bo cum Edge...
docker compose --profile mock down
echo [OK] Da dung containers.
if "%CLI_MODE%"=="0" pause
goto exit

:restart
echo.
echo Dang khoi dong lai cum Edge...
docker compose --profile mock down
call :check_env
docker compose up -d --build
goto endpoints

:logs
echo.
echo Dang mo logs (Nhan Ctrl+C de dung)...
docker compose --profile mock logs -f --tail 100
goto exit

:status
echo.
echo ======================================================================
echo   TRANG THAI CONTAINERS
echo ======================================================================
docker compose --profile mock ps
echo.
echo Kiem tra Healthcheck Edge Backend (:8090)...
curl -s http://localhost:8090/api/v1/edge/health 2>nul
echo.
if "%CLI_MODE%"=="0" pause
goto exit

:clean
echo.
set /p confirm="Ban co chac muon xoa toan bo container va volume SQLite? (y/N): "
if /i "%confirm%"=="y" (
    docker compose --profile mock down -v --remove-orphans
    echo [OK] Da xoa sach toan bo containers va volume.
) else (
    echo Da huy thao tac.
)
if "%CLI_MODE%"=="0" pause
goto exit

:exit
endlocal
