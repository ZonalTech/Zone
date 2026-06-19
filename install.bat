@echo off
REM ===== Install the zone CLI globally on this machine (Windows) =====
REM Installs once into your real Python so `zone` works from ANY directory.
REM No path switching afterwards.
setlocal
set "HERE=%~dp0"

REM Editors like VS Code auto-activate a project's .venv in the terminal, which
REM hijacks pip. Drop any active virtualenv and use the `py` launcher so we
REM install into the real, global Python. zone has no dependencies of its own.
set "VIRTUAL_ENV="
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo Installing the zone CLI globally with %PY% ...
%PY% -m pip install "%HERE%."
if errorlevel 1 (
    echo.
    echo Global install failed ^(permissions?^) - falling back to a per-user install...
    %PY% -m pip install --user "%HERE%."
    if errorlevel 1 (
        echo.
        echo Install failed. Make sure you are NOT inside a virtualenv and retry.
        endlocal & exit /b 1
    )
    echo If 'zone' is not found, add this folder to PATH:
    for /f "delims=" %%B in ('%PY% -m site --user-base') do echo     %%B\Scripts
)

echo.
echo Done. Open a NEW terminal, then from ANY folder run:
echo     zone --version
echo.
echo Create your first zone and run an app:
echo     zone init mystore
echo     cd mystore
echo     zone get https://github.com/ZonalTech/^<your-app^>.git
echo     zone setup zt-pos --seed
echo     zone start zt-pos
endlocal
