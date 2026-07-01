@echo off
echo ==================================================
echo [*] Initializing Dragon HMS ^& Wiretap Workspace
echo [*] Path: %CD%
echo ==================================================

:: 1. Handle the Virtual Environment
IF NOT EXIST venv (
    echo [*] No venv found. Creating a fresh virtual environment...
    python -m venv venv
) ELSE (
    echo [*] Existing venv found.
    echo     (Note: If you just moved to a new PC, delete the 'venv' folder and re-run this script.^)
)

:: 2. Activate the Environment
echo [*] Activating venv...
call venv\Scripts\activate.bat

:: 3. Handle Dependencies
echo [*] Upgrading pip...
python -m pip install --upgrade pip -q

echo [*] Installing dependencies...
IF EXIST requirements.txt (
    pip install -r requirements.txt
) ELSE (
    echo [!] WARNING: requirements.txt not found in this directory! Skipping dependency install.
)

echo ==================================================
echo [SUCCESS] Workspace is ready and activated!
echo [INFO] You are now in your isolated environment.
echo ==================================================

:: 4. Keep the command prompt open and active in the venv
cmd /k
