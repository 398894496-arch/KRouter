@echo off
rem KRouter hook launcher. cmd.exe finds this file through PATHEXT when
rem hooks/hooks.json asks for "session_hook"; POSIX runs the file without the
rem extension. python3 is never tried here: on Windows it is the Microsoft Store
rem app-execution alias, which exits 9009 and prints nothing.
setlocal
set "HERE=%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%HERE%session_hook.py" %*
    exit /b %errorlevel%
)
python "%HERE%session_hook.py" %*
if errorlevel 9009 echo KRouter: neither py nor python is on PATH ^(see docs/INSTALL.md^) 1>&2
exit /b %errorlevel%
