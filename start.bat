@echo off
setlocal enabledelayedexpansion

echo Checking for Host IP...

:: Get IPv4 address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address" /c:"IP Address"') do (
    set IP=%%a
    set IP=!IP: =!
    goto :found
)

echo ❌ Khong the phat hien dia chi IP cua may.
exit /b 1

:found
echo ✅ Da phat hien IP may chu: %IP%

:: Update .env file
if exist .env (
    :: Use PowerShell to replace the line in .env
    powershell -Command "(gc .env) -replace 'APP_BASE_URL=.*', 'APP_BASE_URL=http://%IP%:8000' | Out-File -encoding ASCII .env"
    echo 📝 Da cap nhat APP_BASE_URL trong .env
) else (
    echo ⚠️ Khong tim thay file .env
)

echo 🚀 Dang khoi dong Docker (Windows Production)...
docker-compose -f docker-compose.yml up -d
pause
