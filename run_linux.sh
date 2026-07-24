#!/bin/bash

echo "========================================"
echo "LangSense Telegram Bot - Linux Setup"
echo "========================================"
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}$1 ✓${NC}"
}

print_error() {
    echo -e "${RED}ERROR: $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    echo "Please install Python 3.8+ using your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/RHEL: sudo yum install python3 python3-pip"
    echo "  Fedora: sudo dnf install python3 python3-pip"
    exit 1
fi

print_success "Python 3 is installed"

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    print_error "Python 3.8 or higher is required. You have Python $PYTHON_VERSION"
    exit 1
fi

print_success "Python version $PYTHON_VERSION is compatible"
echo

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        print_error "Failed to create virtual environment"
        exit 1
    fi
    print_success "Virtual environment created"
else
    print_success "Virtual environment already exists"
fi

echo

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    print_error "Failed to activate virtual environment"
    exit 1
fi

print_success "Virtual environment activated"
echo

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip
print_success "Pip upgraded"
echo

# Install required packages
echo "Installing required packages..."
pip install aiogram sqlalchemy aiosqlite asyncpg python-dotenv aiohttp pydantic psutil requests aiofiles pillow cryptography apscheduler babel
if [ $? -ne 0 ]; then
    print_error "Failed to install packages"
    exit 1
fi

print_success "Packages installed successfully"
echo

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_warning ".env file not found!"
    echo
    echo "Please create a .env file with the following content:"
    echo "BOT_TOKEN=your_bot_token_here"
    echo "ADMIN_USER_IDS=your_telegram_user_id_here"
    echo "DATABASE_URL=sqlite+aiosqlite:///./langsense.db"
    echo
    echo "You can copy .env.example to .env and modify the values:"
    echo "cp .env.example .env"
    echo
    read -p "Press Enter to continue..."
else
    print_success ".env file found"
fi

echo

# Create directories if they don't exist
for dir in translations handlers services utils; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        print_success "Created $dir directory"
    fi
done

echo
echo "========================================"
print_success "Setup completed successfully! 🎉"
echo "========================================"
echo

# Make script executable
chmod +x "$0"

# Start the bot
echo "Starting LangSense Bot..."
echo "Press Ctrl+C to stop the bot"
echo

# Function to handle script termination
cleanup() {
    echo
    echo "Bot stopped."
    deactivate
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start the bot
python main.py

# Cleanup on normal exit
cleanup
