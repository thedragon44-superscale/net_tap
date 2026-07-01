#!/bin/bash

# Ensure the script runs in the directory where it's located
cd "$(dirname "$0")"

echo "=================================================="
echo "[*] Initializing Dragon HMS & Wiretap Workspace"
echo "[*] Path: $(pwd)"
echo "=================================================="

# 1. Handle the Virtual Environment
if [ ! -d "venv" ]; then
    echo "[*] No venv found. Creating a fresh virtual environment..."
    python3 -m venv venv
else
    echo "[*] Existing venv found."
    echo "    (Note: If you just moved to a new PC and imports fail, delete the 'venv' folder and re-run this script.)"
fi

# 2. Activate the Environment
echo "[*] Activating venv..."
source venv/bin/activate

# 3. Handle Dependencies
echo "[*] Upgrading pip..."
pip install --upgrade pip -q

echo "[*] Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "[!] WARNING: requirements.txt not found in $(pwd)! Skipping dependency install."
fi

echo "=================================================="
echo "[SUCCESS] Workspace is ready and activated!"
echo "[INFO] You are now in your isolated environment."
echo "=================================================="

# 4. Launch a subshell so the venv remains active in your current terminal window
exec bash --rcfile venv/bin/activate
