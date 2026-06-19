@echo off
REM ===== Install the zonal CLI globally on this machine (Windows) =====
REM Installs once; afterwards `zonal` works from any directory, and you manage
REM as many ZT POS zones as you like with `zonal get` / `zonal setup` / `zonal start`.
setlocal
set "HERE=%~dp0"

REM zonal must land in the REAL Python, never a project's .venv. Drop any active
REM virtualenv for this script and use the `py` launcher so VIRTUAL_ENV / a
REM venv-first PATH can't hijack the install. zonal has no dependencies of its
REM own, so a plain "pip install --user" is all it needs.
set "VIRTUAL_ENV="
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo Installing the zonal CLI with %PY% ...
%PY% -m pip install --user "%HERE%."
if errorlevel 1 (
    echo.
    echo Install failed. Make sure you're NOT inside a virtualenv ^(run "deactivate"
    echo or open a new terminal^), then re-run install.bat.
    endlocal & exit /b 1
)

echo.
echo If 'zonal' is not found, add your user Scripts folder to PATH:
for /f "delims=" %%B in ('%PY% -m site --user-base') do echo     %%B\Scripts
echo.
echo Open a NEW terminal so PATH refreshes, then verify with:
echo     zonal --version
echo.
echo Then create your first zone:
echo     zonal get https://github.com/^<org^>/zt-pos.git
echo     cd zt-pos
echo     zonal setup --seed
echo     zonal start
endlocal
