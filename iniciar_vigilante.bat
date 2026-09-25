@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Vigilando la carpeta "entrada". Copia ahi los folletos PDF. Ctrl+C para salir.
python -m extractor_ofertas vigilar
pause
