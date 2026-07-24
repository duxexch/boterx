#!/bin/bash

echo "========================================"
echo "   Proomnes Bot VPS Launcher (Linux)"
echo "========================================"

# -----------------------------------------
# 1) CHECK PYTHON
# -----------------------------------------
echo "[1] Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python3 NOT installed!"
    echo "Install using:"
    echo "sudo apt install python3 python3-pip -y"
    exit 1
fi
echo "Python OK ✓"


# -----------------------------------------
# 2) CHECK OR CREATE VENV
# -----------------------------------------
echo "[2] Checking virtual environment..."

if [ ! -f "venv/bin/python" ]; then
    echo "Creating venv..."
    python3 -m venv venv
fi

if [ ! -f "venv/bin/python" ]; then
    echo "ERROR: venv creation failed!"
    exit 1
fi
echo "venv ready ✓"


# -----------------------------------------
# 3) ACTIVATE venv
# -----------------------------------------
echo "[3] Activating venv..."
source venv/bin/activate
echo "venv activated ✓"


# -----------------------------------------
# 4) UPDATE PIP (inside venv only)
# -----------------------------------------
echo "[4] Updating pip..."
python3 -m pip install --upgrade pip
echo "pip updated ✓"


# -----------------------------------------
# 5) INSTALL REQUIRED PACKAGES
# -----------------------------------------
echo "[5] Installing required packages if needed..."

REQUIRED_PACKAGES=(
aiogram
python-dotenv
pillow
psutil
requests
openpyxl
babel
aiohttp
aiofiles
)

for pkg in "${REQUIRED_PACKAGES[@]}"; do
    pip show $pkg >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Installing missing package: $pkg"
        pip install $pkg
    else
        echo "Package OK: $pkg ✓"
    fi
done

echo "All packages OK ✓"


# -----------------------------------------
# 6) CREATE REQUIRED FILES
# -----------------------------------------
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    echo "BOT_TOKEN=" >> .env
fi

if [ ! -f "button_labels.json" ]; then
    echo "Creating button_labels.json..."
    echo "{}" > button_labels.json
fi

echo "Essential files ready ✓"


# -----------------------------------------
# 7) ASK USER WHICH BOT FILE TO RUN
# -----------------------------------------
echo "========================================"
echo " Choose Bot File to Run"
echo "========================================"
echo "1) main.py"
echo "2) comprehensive_bot.py"
echo "3) advanced_bot.py"
echo "4) fixed_bot.py"
echo "5) simple_bot.py"
echo -n "Enter number: "
read choice

case $choice in
    1) script="main.py" ;;
    2) script="comprehensive_bot.py" ;;
    3) script="advanced_bot.py" ;;
    4) script="fixed_bot.py" ;;
    5) script="simple_bot.py" ;;
    *) echo "Invalid choice!"; exit 1 ;;
esac

echo "Running $script ..."
python3 "$script"

echo "Bot stopped."
