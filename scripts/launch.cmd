@echo off
rem Starts GT Pilot inside the ChatGPT desktop app on Windows. Same as scripts/launch.
setlocal
cd /d "%~dp0.."
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if not defined UV set "UV=%CD%\.uv\uv.exe"
if not exist "%UV%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:UV_INSTALL_DIR='%CD%\.uv'; $env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex" 1>&2
)
if not exist "%UV%" (
  echo GT Pilot could not download its runtime. Check the internet connection and restart ChatGPT. 1>&2
  exit /b 1
)
"%UV%" run --quiet --directory "%CD%" src\server.py
