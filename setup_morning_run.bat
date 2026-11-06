@echo off
REM Morning auto-run setup — Data Cleaner Studio (Batch 5, v1.3).
REM Double-click this file on your own PC. It registers a Windows
REM scheduled task that runs morning_run.py every morning at 8:00am.
REM Nothing is scheduled until you run this file yourself, and you can
REM remove the task any time with:
REM   schtasks /delete /tn "Data Cleaner Studio Morning Run" /f
REM This file needs morning_run.py in the same folder.

set "HERE=%~dp0"
set "PY=%HERE%Data-Cleaner-Studio\python\python.exe"
if not exist "%PY%" set "PY=python"
schtasks /create /tn "Data Cleaner Studio Morning Run" /tr "\"%PY%\" \"%HERE%morning_run.py\"" /sc daily /st 08:00 /f
if %ERRORLEVEL%==0 (
  echo Done — the morning run is set for 8:00am every day.
  echo Put messy files in the morning_in folder and find the cleaned
  echo files in morning_out each morning.
) else (
  echo Could not create the scheduled task. Try right-clicking this
  echo file and choosing "Run as administrator".
)
pause
