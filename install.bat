@echo off
REM ===== Install the zonal CLI globally on this machine (Windows) =====
REM Installs once into your real Python so `zonal` works from ANY directory,
REM exactly like `bench`. No path switching afterwards.
setlocal
set "HERE=%~dp0"

REM Editors like VS Code auto-activate a project's .venv in the terminal, which
REM hijacks pip. Drop any active virtualenv and use the `py` launcher so we
REM install into the real, global Python. zonal has no dependencies of its own.
set "VIRTUAL_ENV="
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo Installing the zonal CLI globally with %PY% ...
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
    echo If 'zonal' is not found, add this folder to PATH:
    for /f "delims=" %%B in ('%PY% -m site --user-base') do echo     %%B\Scripts
)

echo.
echo Done. Open a NEW terminal, then from ANY folder run:
echo     zonal --version
echo.
echo Create your first zone and run an app:
echo     zonal init mystore
echo     cd mystore
echo     zonal get https://github.com/^<org^>/zt-pos.git
echo     cd apps\zt-pos
echo     zonal setup --seed
echo     zonal start
endlocal
