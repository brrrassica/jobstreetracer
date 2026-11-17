@echo off
rem Run the JobStreetracer bridge minimized at login.
rem Put a shortcut to this file in: shell:startup
rem Edit the path below if the project lives elsewhere.
cd /d "%USERPROFILE%\projects\jobstreetracer"
if not exist ".venv\Scripts\jobstreetracer.exe" (
  echo JobStreetracer virtualenv not found.
  pause
  exit /b 1
)
start "JobStreetracer Bridge" /min ".venv\Scripts\jobstreetracer.exe" bridge --static web\dist
