@echo off
rem KRouter MCP launcher, the same way session_hook.cmd does it.
rem .claude-plugin/plugin.json asks for "mcp_server"; cmd.exe finds this file
rem through PATHEXT, POSIX runs the file without the extension.
setlocal
set "HERE=%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%HERE%mcp_server.py" %*
    exit /b %errorlevel%
)
python "%HERE%mcp_server.py" %*
if errorlevel 9009 echo KRouter: neither py nor python is on PATH ^(see docs/INSTALL.md^) 1>&2
exit /b %errorlevel%
