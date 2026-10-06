@echo off
echo ==========================================
echo  Plateforme RFM SRB Vatovavy
echo  Pre-requis : service Windows MongoDB demarre
echo ==========================================
echo.
start "Backend RFM SRB" "%~dp0demarrer-backend.bat"
start "Frontend RFM SRB" "%~dp0demarrer-frontend.bat"
echo.
echo Backend  : http://127.0.0.1:8000/docs
echo Frontend : http://localhost:3000
timeout /t 3 >nul