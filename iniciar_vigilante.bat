@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Modo borrador SIN IA (reglas). Para la extraccion completa usa Claude/ChatGPT Desktop (ver README).
python -m extractor_ofertas vigilar
pause
