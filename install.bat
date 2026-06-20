@echo off
REM ===== Install the zone CLI (Windows) =====
REM Installs the CLI and registers `zone` on PATH so plain `zone` commands work
REM immediately - no reload, no `py -m`.
setlocal
set "HERE=%~dp0"

REM Editors auto-activate a project's .venv in the terminal, which hijacks pip.
REM Drop any active virtualenv and use the `py` launcher to hit the real Python.
set "VIRTUAL_ENV="
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo Installing the zone CLI with %PY% ...
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
)

REM Register `zone` by running the freshly installed executable once. That drops
REM a launcher into a folder already on PATH, so `zone` resolves right away.
echo Registering 'zone' on your PATH ...
for /f "delims=" %%S in ('%PY% -c "import sysconfig;print(sysconfig.get_path('scripts'))"') do set "SCR=%%S"
if exist "%SCR%\zone.exe" ("%SCR%\zone.exe" --version)

echo.
echo Done. Plain `zone` commands now work - no reload needed:
echo     zone --version
echo     zone init mystore
echo     cd mystore
echo     zone start mystore
endlocal
