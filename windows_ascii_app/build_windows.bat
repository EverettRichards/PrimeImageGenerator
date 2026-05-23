@echo off
setlocal
cd /d %~dp0
rem Build into a nested build folder to avoid permission/locking issues on the top-level dist folder
set DIST_DIR=%~dp0build\dist
set WORK_DIR=%~dp0build\work
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
rem Ensure PyInstaller can find the local package at the repository root
set "REPO_ROOT=%~dp0.."

rem Add the repository root to the module search path for PyInstaller
rem and explicitly include the shared_ascii_app package as data and hidden imports

rem Prefer using the project's virtual environment python to run PyInstaller if available
set "VENV_PY=%REPO_ROOT%\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    echo Using virtualenv python at %VENV_PY%
    "%VENV_PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name VADIM_ASCII_Generator --distpath "%DIST_DIR%" --workpath "%WORK_DIR%" --paths "%REPO_ROOT%" --add-data "%REPO_ROOT%\shared_ascii_app;shared_ascii_app" --hidden-import shared_ascii_app --hidden-import shared_ascii_app.engine --hidden-import shared_ascii_app.gui main.py
) else (
    echo Virtualenv python not found at %VENV_PY%, attempting to use pyinstaller from PATH
    pyinstaller --noconfirm --clean --onefile --windowed --name VADIM_ASCII_Generator --distpath "%DIST_DIR%" --workpath "%WORK_DIR%" --paths "%REPO_ROOT%" --add-data "%REPO_ROOT%\shared_ascii_app;shared_ascii_app" --hidden-import shared_ascii_app --hidden-import shared_ascii_app.engine --hidden-import shared_ascii_app.gui main.py
)
