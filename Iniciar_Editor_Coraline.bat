@echo off
title Coraline DS - Editor & Tradutor de Textos
cd /d "%~dp0"
python CoralineTextEditor.py
if errorlevel 1 (
    echo.
    echo Ocorreu um erro ao iniciar o editor. Pressione qualquer tecla para sair.
    pause >nul
)
