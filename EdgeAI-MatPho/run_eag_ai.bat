@echo off
setlocal enabledelayedexpansion
title KHOI DONG CUM EAG VA MO HINH AI (FIREWATCH AI)
color 0E

echo ======================================================================
echo    KHOI DONG CUM EAG [EDGE GATEWAY] VA MO HINH AI [FIREWATCH AI]
echo ======================================================================
echo.

set "ROOT_DIR=%~dp0"
if exist "%ROOT_DIR%\EdgeAI-MatPho\docker-compose.yml" (
    set "EDGE_DIR=%ROOT_DIR%\EdgeAI-MatPho"
) else if exist "%ROOT_DIR%\docker-compose.yml" (
    set "EDGE_DIR=%ROOT_DIR%"
) else (
    echo [LOI] Khong tim thay thu muc EdgeAI-MatPho!
    pause
    exit /b 1
)

cd /d "%EDGE_DIR%"

echo [*] Kiem tra Docker Daemon...
docker info >nul 2>&1
if errorlevel 1 (
    echo [LOI] Docker Desktop chua bat! Vui long bat Docker Desktop truoc.
    pause
    exit /b 1
)

REM Demo: "run_eag_ai.bat chay <ten>" phat clip demo\<ten>_chay.mp4 MOT LAN vao luong camera
REM demo; het clip MediaMTX tu quay ve canh thuong nen luong khong mat. Can chay cum Edge
REM voi MEDIAMTX_CONFIG=./mediamtx/mediamtx.demo.yml trong .env, xem demo\README.md.
if /i "%~1"=="chay" (
    if "%~2"=="" (
        echo [LOI] Thieu ten. Vi du: run_eag_ai.bat chay cam_gara
        echo       Ten hop le: cam_gara, cam_xe_dien, cam_nha_xe, cam_bai_xe, fire_demo, cam_01
        exit /b 1
    )
    if not exist "%CD%\demo\%~2_chay.mp4" (
        echo [LOI] Khong co file demo\%~2_chay.mp4, xem demo\README.md
        exit /b 1
    )
    set "DEMO_PATH=mock/%~2"
    if /i "%~2"=="cam_01" set "DEMO_PATH=source/cam_01"
    docker rm -f matpho_demo_chay_%~2 >nul 2>&1
    docker run -d --rm --name matpho_demo_chay_%~2 --network matpho_edge_net -v "%CD%\demo:/demo:ro" --entrypoint ffmpeg edgeai-matpho-edge-backend -hide_banner -loglevel warning -re -i /demo/%~2_chay.mp4 -c copy -f rtsp -rtsp_transport tcp rtsp://mediamtx:8554/!DEMO_PATH! >nul
    if errorlevel 1 (
        echo [LOI] Khong phat duoc clip chay.
        exit /b 1
    )
    echo [OK] Dang phat clip chay vao !DEMO_PATH!, het clip se tu ve canh thuong.
    exit /b 0
)

REM IP LAN cua may nay de Cloud tra cho dien thoai dia chi HLS mo duoc (khong can tunnel).
REM Bo qua neu EDGE_LAN_IP / EDGE_PUBLIC_HLS_URL da dat trong moi truong hoac .env.
if "%EDGE_LAN_IP%"=="" if "%EDGE_PUBLIC_HLS_URL%"=="" (
    findstr /R "^EDGE_LAN_IP=. ^EDGE_PUBLIC_HLS_URL=." .env >nul 2>&1
    if errorlevel 1 (
        for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /C:"IPv4"') do (
            if "!EDGE_LAN_IP!"=="" set "EDGE_LAN_IP=%%A"
        )
        set "EDGE_LAN_IP=!EDGE_LAN_IP: =!"
        if not "!EDGE_LAN_IP!"=="" (
            echo [OK] IP LAN cho luong HLS: !EDGE_LAN_IP! [ghi de bang EDGE_LAN_IP hoac EDGE_PUBLIC_HLS_URL]
        ) else (
            echo [CANH BAO] Khong do duoc IP LAN; dat EDGE_LAN_IP trong .env neu xem camera trong LAN.
        )
    )
)

REM Kiem tra xem co tham so mock hay khong
set "PROFILE_ARG="
if /i "%1"=="mock" set "PROFILE_ARG=--profile mock"
if /i "%1"=="--mock" set "PROFILE_ARG=--profile mock"

echo [*] Dang khoi chay containers Cum EAG va Mo hinh AI...
echo     1. MediaMTX      : Edge Stream Gateway [RTSP :8554, HLS :8888, WebRTC :8889]
echo     2. Edge Backend  : Controller API va Stream Worker [:8090]
echo     3. FireWatch AI  : Mo hinh AI phat hien chay va khoi
if not "!PROFILE_ARG!"=="" (
    echo     4. Mock Camera   : Camera OSD dem giay gia lap
    docker compose !PROFILE_ARG! up -d
) else (
    docker compose up -d
)

if errorlevel 1 (
    echo [LOI] Khong the khoi dong Docker Compose!
    pause
    exit /b 1
)

echo.
echo [*] Dang kiem tra trang thai ket noi cac dich vu...

REM 1. Kiem tra Edge Backend [:8090]
set /a attempts=0
:wait_edge
set /a attempts+=1
if !attempts! geq 20 (
    echo.
    echo [CANH BAO] Edge Backend mat qua nhieu thoi gian de san sang.
    goto check_ai
)

curl -s -f http://localhost:8090/health >nul 2>&1
if errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    <nul set /p=.
    goto wait_edge
)

:check_ai
echo.
echo [*] Kiem tra ket noi Mo hinh AI FireWatch AI vao Cum EAG...
ping 127.0.0.1 -n 3 >nul

REM Kiem tra xem FireWatch AI co goi duoc vao Edge Backend khong
set "AI_STATUS=DANG KHOI DONG"
REM Log cua Python di ra stderr nen phai gop 2^>^&1, neu bo 2^>nul thi khong doc duoc gi.
docker logs matpho_edge_firewatch_ai --tail 40 2>&1 | findstr /I "edge-backend:8090" >nul
if not errorlevel 1 (
    set "AI_STATUS=KET NOI THANH CONG [SYNC CAMERA OK]"
)
REM Khong co luong camera thi /health tra 503 va container bao unhealthy.
docker logs matpho_edge_firewatch_ai --tail 20 2>&1 | findstr /C:"DESCRIBE failed" >nul
if not errorlevel 1 (
    set "AI_STATUS=CHUA CO LUONG CAMERA [chay: run_eag_ai.bat mock]"
)
REM Healthcheck cua Docker la nguon dang tin nhat: healthy thi AI dang doc duoc camera.
set "AI_HEALTH="
for /f "delims=" %%H in ('docker inspect -f "{{.State.Health.Status}}" matpho_edge_firewatch_ai 2^>nul') do set "AI_HEALTH=%%H"
if /i "!AI_HEALTH!"=="healthy" set "AI_STATUS=HOAT DONG [healthy]"
if /i "!AI_HEALTH!"=="unhealthy" set "AI_STATUS=KHONG KHOE [unhealthy, thuong do chua co luong camera]"

echo.
echo ======================================================================
echo [THANH CONG] CUM EAG VA MO HINH AI DA KET NOI HOAT DONG!
echo ======================================================================
echo   * MediaMTX Ingest [RTSP]   : rtsp://localhost:8554
echo   * MediaMTX Playback [HLS]  : http://localhost:8888
echo   * Edge Controller API      : http://localhost:8090/docs
echo   * Edge Healthcheck         : http://localhost:8090/health
echo   * Mo Hinh FireWatch AI     : matpho_edge_firewatch_ai
echo   * Trang Thai AI -^> EAG     : !AI_STATUS!
echo ======================================================================
echo.

echo [*] Danh sach container Edge dang chay:
docker ps --filter "name=matpho_edge" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.

echo [*] 5 dong log moi nhat cua Mo hinh AI:
docker logs matpho_edge_firewatch_ai --tail 5 2>&1
echo.

if "%~1"=="auto" goto end

:menu_loop
echo ======================================================================
echo TUY CHON THEO DOI:
echo   [1] Xem Log truc tiep Mo hinh AI theo thoi gian thuc [Live Logs]
echo   [2] Xem Log truc tiep Edge Backend
echo   [3] Xem Log truc tiep MediaMTX Gateway
echo   [4] Kiem tra danh sach camera dang scan AI
echo   [0] Thoat menu [Giu cac container chay ngam]
echo ======================================================================
set "sub_choice="
set /p sub_choice="Nhap lua chon cua ban [1-4, 0]: "
if "!sub_choice!"=="" goto menu_loop

if "%sub_choice%"=="1" (
    echo [*] Dang mo log live FireWatch AI. Nhan 'Ctrl + C' de quay lai menu...
    docker logs -f matpho_edge_firewatch_ai
    goto menu_loop
)
if "%sub_choice%"=="2" (
    echo [*] Dang mo log live Edge Backend. Nhan 'Ctrl + C' de quay lai menu...
    docker logs -f matpho_edge_backend
    goto menu_loop
)
if "%sub_choice%"=="3" (
    echo [*] Dang mo log live MediaMTX. Nhan 'Ctrl + C' de quay lai menu...
    docker logs -f matpho_edge_mediamtx
    goto menu_loop
)
if "%sub_choice%"=="4" (
    echo [*] Danh sach camera tu Edge Backend [:8090]:
    curl -s http://localhost:8090/api/v1/edge/cameras
    echo.
    echo.
    goto menu_loop
)
if "%sub_choice%"=="0" goto end

goto menu_loop

:end
if "%~1"=="" pause
exit /b 0
