@echo off
setlocal enabledelayedexpansion
title MAT PHO - HE THONG: BACKEND (TUNNEL) + EDGE (AI MODEL) + RTSP + APP
color 0B

:menu
cls
echo ================================================================================
echo   MAT PHO - HE THONG: BACKEND (TUNNEL) + EDGE (KEM MODEL AI) + RTSP + APP
echo ================================================================================
echo.
echo   [1] KHOI DONG TRON GOI : Tu dong chay tuan tu ca 5 buoc (1-Click Startup)
echo.
echo   ------------------------------------------------------------------------------
echo   [2] BUOC 1: Chi bat Cloud Backend (:8000)
echo   [3] BUOC 2: Mo Duong Ham Cloudflare Tunnel cho Backend va Nap vao Edge
echo   [4] BUOC 3: Chi bat Cum Edge EAG KEM MODEL AI (3 Containers)
echo   [5] BUOC 4: Chi bat Tool Test RTSP Camera va Tu Dong Dong Bo Luong
echo   [6] BUOC 5: Sinh Lenh va Khoi Chay App Flutter Ket Noi Backend
echo   ------------------------------------------------------------------------------
echo   [S] KIEM TRA TOAN CHUOI: Xem thong luong tu Camera -^> Edge -^> Model AI -^> Cloud
echo   [X] DUNG TOAN BO CAC KHOI VA DONG DUONG HAM
echo   [0] Thoat menu
echo ================================================================================
set "choice="
set /p choice="Nhap lua chon cua ban [1-6, S, X, 0]: "
if "%choice%"=="" goto menu

if "%choice%"=="1" goto run_all
if "%choice%"=="2" goto step1
if "%choice%"=="3" goto step2
if "%choice%"=="4" goto step3
if "%choice%"=="5" goto step4
if "%choice%"=="6" goto step5
if /i "%choice%"=="s" goto status
if /i "%choice%"=="x" goto stop_all
if "%choice%"=="0" goto exit
goto menu

:run_all
cls
echo ================================================================================
echo    BAT DAU KHOI DONG TRON GOI: BACKEND -^> TUNNEL -^> EDGE (AI) -^> RTSP CAMERA
echo ================================================================================
echo.
call "%~dp0scripts\01_start_backend.bat" auto
echo.
call "%~dp0scripts\02_start_tunnel.bat" auto
echo.
call "%~dp0scripts\03_start_edge.bat" auto
echo.
call "%~dp0scripts\04_start_rtsp_test.bat" auto
echo.
echo [*] Khoi dong tron goi thanh cong! Dang kiem tra trang thai tong the...
ping 127.0.0.1 -n 3 >nul
call "%~dp0scripts\06_check_status.bat"
echo.
echo [*] Tiep theo: Sinh lenh va khoi chay App Mobile...
call "%~dp0scripts\05_run_app.bat" auto
goto menu

:step1
call "%~dp0scripts\01_start_backend.bat"
goto menu

:step2
call "%~dp0scripts\02_start_tunnel.bat"
goto menu

:step3
call "%~dp0scripts\03_start_edge.bat"
goto menu

:step4
call "%~dp0scripts\04_start_rtsp_test.bat"
goto menu

:step5
call "%~dp0scripts\05_run_app.bat"
goto menu

:status
call "%~dp0scripts\06_check_status.bat"
goto menu

:stop_all
call "%~dp0scripts\07_stop_all.bat"
goto menu

:exit
echo Tam biet!
exit /b 0
