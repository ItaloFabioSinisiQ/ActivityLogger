@echo off
setlocal enabledelayedexpansion

echo Verificando dependencias de Python...
for %%m in (psutil pyperclip) do (
    python -c "import %%m" 2>nul
    if !errorlevel! neq 0 (
        echo [INSTALANDO] %%m...
        pip install %%m --quiet
    )
)

echo Ejecutando monitor_actividad.py...
python "TU RUTA"

if !errorlevel! equ 0 (
    echo Script ejecutado correctamente.
) else (
    echo ERROR: El script falló (Código: !errorlevel!).
)

pause
endlocal