# LangSense Telegram Bot

A comprehensive Telegram bot for financial services with multi-language support, admin panel, broadcasting, and transaction management built with Python and Aiogram v3.

## Features

### 🌐 Multi-Language Support
- Arabic (RTL) and English interfaces
- Dynamic language switching
- Localized content and keyboards
- Country-specific settings

### 👥 User Management
- Phone number verification
- Automatic customer code generation
- User profiles and preferences
- Activity tracking

### 💰 Financial Services
- Deposit requests with receipt uploads
- Withdrawal processing
- Complaint handling system
- Transaction workflow management

### 🛠️ Admin Panel
- User management and statistics
- Language and country administration
- Broadcasting system with targeting
- Request inbox and approval workflow

### 📢 Broadcasting & Announcements
- Mass messaging with rate limiting
- Target filtering by language/country
- Scheduled announcements
- Delivery tracking and retry logic

### 🔒 Security & Authentication
- Admin-only access controls
- Secure database operations
- Input validation and sanitization
- Error handling and logging

## Technology Stack

- **Framework**: Aiogram v3 (Telegram Bot API)
- **Database**: SQLAlchemy with async support
- **Storage**: SQLite (dev) / PostgreSQL (prod)
- **Internationalization**: JSON-based translations
- **Task Scheduling**: APScheduler
- **Image Processing**: Pillow
- **Environment**: python-dotenv

## Quick Start

### Prerequisites
- Python 3.8 or higher
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Your Telegram User ID

### Windows Setup
1. Download/clone this repository
2. Double-click `run_windows.bat`
3. Follow the setup instructions
4. Create `.env` file with your bot token and admin ID
5. The bot will start automatically

### Linux/macOS Setup
```bash
# Make the script executable
chmod +x run_linux.sh

# Run the setup script
./run_linux.sh
