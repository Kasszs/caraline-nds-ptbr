@echo off
title Coraline DS - Gerenciador & Injetor de Texturas 2D
cd /d "%~dp0"
python CoralineTextureTool.py
if errorlevel 1 (
    echo.
    echo Ocorreu um erro ao iniciar o editor de texturas. Pressione qualquer tecla para sair.
    pause >nul
)
