@echo off
REM ============================================================================
REM  Batch Attribute Editor - copy the launch command to the clipboard
REM
REM  Double-click this file, then paste into Maya's Script Editor (Python tab)
REM  and press Enter. This script does NOT start Maya - you keep using the Maya
REM  session you already have open.
REM
REM  The copied command carries this folder's absolute path, so the project can
REM  live anywhere - USB stick, network share, any drive letter, renamed folder -
REM  and the pasted command keeps working without editing.
REM ============================================================================

setlocal

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "LAUNCH_CMD=import sys; sys.path.insert(0, r'%PROJECT_ROOT%'); import main; main.reload_and_launch()"
set "CHECK_CMD=import sys; sys.path.insert(0, r'%PROJECT_ROOT%'); import tools.selfcheck; tools.selfcheck.run(create_test_nodes=True)"

<nul set /p "=%LAUNCH_CMD%" | clip

echo Batch Attribute Editor
echo.
echo Project folder:
echo   %PROJECT_ROOT%
echo.
echo ---------------------------------------------------------------- clipboard
echo Copied - paste into Maya's Script Editor (Python tab) and press Enter:
echo.
echo   %LAUNCH_CMD%
echo.
echo This reloads the project's modules before opening the window, so Maya never
echo keeps running a stale copy. Without it, editing a file here has no effect
echo until Maya is restarted: "import main" would return the already-loaded module.
echo.
echo ------------------------------------------------------------- other commands
echo Self-check (builds temporary nodes, then deletes them again):
echo.
echo   %CHECK_CMD%
echo.
echo Test suite (run with mayapy.exe, not inside Maya):
echo.
echo   "%%ProgramFiles%%\Autodesk\Maya2024\bin\mayapy.exe" "%PROJECT_ROOT%\tests\run_tests.py"
echo.
pause

endlocal
