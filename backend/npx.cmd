@echo off
setlocal enabledelayedexpansion

set "target=0"
for %%a in (%*) do (
    if "%%a"=="@ravi-bytes/india-flight-mcp-server" set "target=1"
)

if "!target!"=="1" (
    node "C:\Users\KIIT\Desktop\skymind\backend\scratch\india-flight-mcp\src\mcp\stdio_server.js"
) else (
    "C:\Program Files\nodejs\npx.cmd" %*
)
