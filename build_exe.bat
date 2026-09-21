@echo off
chcp 65001 >nul
echo ========================================================
echo   📦 Boot Avaliador - Build do Executavel (PyInstaller)
echo ========================================================
echo.

REM 1) Valida testes antes de empacotar
python test_modules.py
if errorlevel 1 (
    echo [ERRO] Testes falharam. Build cancelado.
    pause
    exit /b 1
)

REM 2) Garante o PyInstaller instalado
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    python -m pip install pyinstaller
)

REM 3) Gera o executavel
python -m PyInstaller --noconfirm --clean --onedir --windowed --name BootAvaliador ^
  --add-data "logo.png;." ^
  --add-data "logo.ico;." ^
  --icon "logo.ico" ^
  --hidden-import customtkinter ^
  --collect-data customtkinter ^
  --hidden-import telethon ^
  --hidden-import telethon.crypto.libssl ^
  --hidden-import PIL._tkinter_finder ^
  main.py

if errorlevel 1 (
    echo.
    echo [ERRO] Falha no build. Verifique as mensagens acima.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   [OK] Build concluido! Executavel em: dist\BootAvaliador\BootAvaliador.exe
echo ========================================================
pause
