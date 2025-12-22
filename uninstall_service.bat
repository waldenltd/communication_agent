@echo off
:: Communication Agent Windows Service Uninstaller
:: Run this script as Administrator

set NSSM=C:\communication_agent\nssm\nssm-2.24\win64\nssm.exe
set SERVICE_NAME=CommunicationAgent

echo ========================================
echo Communication Agent Service Uninstaller
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

:: Stop and remove service
echo Stopping service...
%NSSM% stop %SERVICE_NAME%

echo Removing service...
%NSSM% remove %SERVICE_NAME% confirm

echo.
echo Service removed successfully!
pause
