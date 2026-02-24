@echo off
echo Creating Virtual Environment...
python -m venv venv
echo Activating Virtual Environment...
call venv\Scripts\activate
echo Installing PySide6 and OpenCV...
pip install PySide6 opencv-python
echo.
echo Setup Complete! You can now run the app.
pause