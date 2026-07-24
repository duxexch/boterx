#!/bin/bash

echo "========================================"
echo "   Proomnes Smart VPS Bot Analyzer"
echo "========================================"

# ----------------------------------------------
# 1) CHECK PYTHON
# ----------------------------------------------
echo "[1] Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python NOT FOUND!"
    echo "Installing Python..."
    sudo apt update && sudo apt install python3 python3-pip -y
fi
echo "Python OK ✓"


# ----------------------------------------------
# 2) CREATE OR CHECK VENV
# ----------------------------------------------
echo "[2] Checking virtual environment..."

if [ ! -f "venv/bin/python" ]; then
    echo "Creating venv..."
    python3 -m venv venv
fi

if [ ! -f "venv/bin/python" ]; then
    echo "ERROR: venv failed!"
    exit 1
fi
echo "venv ready ✓"

source venv/bin/activate
echo "venv activated ✓"


# ----------------------------------------------
# 3) UPDATE PIP SAFELY
# ----------------------------------------------
echo "[3] Updating pip..."
python3 -m pip install --upgrade pip >/dev/null 2>&1
echo "pip updated ✓"


# ----------------------------------------------
# 4) AUTO-DETECT REQUIRED PACKAGES
# ----------------------------------------------
echo "[4] Analyzing bot files for needed libraries..."

PY_FILES=$(ls *.py)
REQ_PKGS=()

detect_pkg () {
    if grep -R "import $1" -i -- *.py >/dev/null 2>&1; then
        REQ_PKGS+=("$2")
        echo "Detected: $1 → requires ($2)"
    fi
}

detect_pkg aiogram aiogram
detect_pkg dotenv python-dotenv
detect_pkg PIL pillow
detect_pkg psutil psutil
detect_pkg requests requests
detect_pkg openpyxl openpyxl
detect_pkg babel babel
detect_pkg aiohttp aiohttp
detect_pkg aiofiles aiofiles
detect_pkg sqlalchemy sqlalchemy
detect_pkg aiosqlite aiosqlite
detect_pkg asyncpg asyncpg
detect_pkg cryptography cryptography
detect_pkg zipfile ""
detect_pkg urllib ""
detect_pkg json ""

echo "-----------------------------------------"
echo "Detected required packages:"
printf '%s\n' "${REQ_PKGS[@]}"
echo "-----------------------------------------"


# ----------------------------------------------
# 5) INSTALL MISSING PACKAGES
# ----------------------------------------------
echo "[5] Installing required packages..."

for pkg in "${REQ_PKGS[@]}"; do
    if [ "$pkg" != "" ]; then
        pip show $pkg >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "Installing: $pkg ..."
            pip install $pkg
        else
            echo "$pkg already installed ✓"
        fi
    fi
done

echo "All packages OK ✓"


# ----------------------------------------------
# 6) FIND ALL RUNNABLE BOT FILES
# ----------------------------------------------
echo "[6] Scanning for runnable bot files..."

declare -a BOT_FILES=()

for f in *.py; do
    if grep -R "aiogram" "$f" >/dev/null 2>&1 || \
       grep -R "telebot" "$f" >/dev/null 2>&1 || \
       grep -R "Application" "$f" >/dev/null 2>&1 || \
       grep -R "Dispatcher" "$f" >/dev/null 2>&1; then
      
        BOT_FILES+=("$f")
        echo "Detected bot file: $f"
    fi
done

echo "-------------------------------------"
if [ ${#BOT_FILES[@]} -eq 0 ]; then
    echo "❌ No bot files detected!"
    exit 1
fi

echo "Available bot files:"
i=1
for f in "${BOT_FILES[@]}"; do
    echo "$i) $f"
    ((i++))
done
echo "-------------------------------------"

echo -n "Choose file number to run: "
read choice

FILE_TO_RUN=${BOT_FILES[$choice-1]}

if [ "$FILE_TO_RUN" == "" ]; then
    echo "Invalid selection!"
    exit 1
fi

echo "========================================"
echo "Running bot: $FILE_TO_RUN"
echo "========================================"

python3 "$FILE_TO_RUN"
