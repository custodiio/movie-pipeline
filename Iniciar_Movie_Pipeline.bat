@echo off
title Servidor Movie-Pipeline Bot Admin
color 0A
echo ============================================================
echo   INICIANDO BOT ADMIN DO MOVIE-PIPELINE (LOCAL)
echo ============================================================
echo.
cd /d "D:\Applications\Movie-Pipeline"
echo Diretorio atual: %CD%
echo.
python run_bot.py
echo.
echo ============================================================
echo   SERVIDOR ENCERRADO!
echo ============================================================
pause
