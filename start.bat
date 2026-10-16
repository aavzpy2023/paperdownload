@echo off
rem Double-click launcher for Windows: runs start.ps1 without changing any system policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
