@echo off
echo Starting Dracula File Manager Pro...
set PYTHONPATH=%PYTHONPATH%;%CD%
start "" venv\Scripts\pythonw.exe file_manager.py
exit