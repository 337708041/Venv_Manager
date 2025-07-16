@echo off 
if "%1"=="hide" goto CmdBegin
start mshta vbscript:createobject("wscript.shell").run("""%~0"" hide",0)(window.close)&&exit
:CmdBegin
cd /d "%~dp0"
venv\Scripts\python.exe main.py