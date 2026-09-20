@echo off
chcp 65001 >nul
echo ========================================================
echo   🚀 Boot Avaliador - Git OK (Commit ^& Push Automatico)
echo ========================================================
echo.

git add .
set /p commit_msg="Mensagem do Commit (Enter para automatico): "

if "%commit_msg%"=="" (
    set commit_msg=feat(bootavaliador): atualizacao das rotinas de avaliacao, monitoramento e limpeza
)

echo.
echo Executando commit: "%commit_msg%"...
git commit -m "%commit_msg%"

echo.
echo Enviando alteracoes para o GitHub (push)...
git push origin main

echo.
echo ========================================================
echo   ✅ Operacao concluida!
echo ========================================================
pause
