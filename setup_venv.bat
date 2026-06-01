@echo off
echo Setting up virtual environment for tracker_person_2...

:: Create venv
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create venv. Make sure Python 3.11 is installed.
    pause
    exit /b 1
)

:: Activate and install
call venv\Scripts\activate
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete! To activate the environment:
echo   venv\Scripts\activate
pause
