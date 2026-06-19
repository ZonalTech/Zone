@echo off
REM ===== Install the zonal CLI globally on this machine (Windows) =====
REM Installs once; afterwards `zonal` works from any directory, and you manage
REM as many ZT POS zones as you like with `zonal get` / `zonal setup` / `zonal start`.
setlocal
set HERE=%~dp0

echo Installing the zonal CLI...
where pipx >nul 2>nul
if %errorlevel%==0 (
    REM pipx keeps zonal isolated in its own venv and puts it on PATH.
    pipx install --force "%HERE%."
) else (
    echo pipx not found - falling back to "pip install --user".
    echo   ^(Recommended: py -m pip install --user pipx ^&^& py -m pipx ensurepath^)
    python -m pip install --user "%HERE%."
)

echo.
echo Done. Open a NEW terminal so PATH refreshes, then verify with:
echo     zonal --version
echo.
echo Then create your first zone:
echo     zonal get https://github.com/^<org^>/zt-pos.git
echo     cd zt-pos
echo     zonal setup --seed
echo     zonal start
endlocal
