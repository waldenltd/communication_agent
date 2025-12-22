@echo off
:: Communication Agent Windows Service Installer
:: Run this script as Administrator

set NSSM=C:\communication_agent\nssm\nssm-2.24\win64\nssm.exe
set SERVICE_NAME=CommunicationAgent
set PYTHON=C:\Users\yearr\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe
set SCRIPT=C:\communication_agent\main.py
set APP_DIR=C:\communication_agent

echo ========================================
echo Communication Agent Service Installer
echo ========================================
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

:: Remove existing service if it exists
echo Checking for existing service...
%NSSM% status %SERVICE_NAME% >nul 2>&1
if %errorLevel% equ 0 (
    echo Stopping existing service...
    %NSSM% stop %SERVICE_NAME%
    echo Removing existing service...
    %NSSM% remove %SERVICE_NAME% confirm
)

:: Install the service
echo.
echo Installing %SERVICE_NAME% service...
%NSSM% install %SERVICE_NAME% "%PYTHON%" "%SCRIPT%"

:: Configure the service
echo Configuring service...
%NSSM% set %SERVICE_NAME% AppDirectory "%APP_DIR%"
%NSSM% set %SERVICE_NAME% DisplayName "Communication Agent"
%NSSM% set %SERVICE_NAME% Description "Processes email and SMS communication queue"
%NSSM% set %SERVICE_NAME% Start SERVICE_AUTO_START
%NSSM% set %SERVICE_NAME% AppStdout "%APP_DIR%\logs\service_stdout.log"
%NSSM% set %SERVICE_NAME% AppStderr "%APP_DIR%\logs\service_stderr.log"
%NSSM% set %SERVICE_NAME% AppRotateFiles 1
%NSSM% set %SERVICE_NAME% AppRotateBytes 10485760

:: Start the service
echo.
echo Starting service...
%NSSM% start %SERVICE_NAME%

:: Check status
echo.
echo ========================================
echo Service Status:
echo ========================================
%NSSM% status %SERVICE_NAME%

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo To manage the service:
echo   Start:   nssm start %SERVICE_NAME%
echo   Stop:    nssm stop %SERVICE_NAME%
echo   Status:  nssm status %SERVICE_NAME%
echo   Remove:  nssm remove %SERVICE_NAME%
echo.
pause
