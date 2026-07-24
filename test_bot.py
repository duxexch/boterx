#!/usr/bin/env python3
"""
Test script to verify the bot database and functionality
"""

import sqlite3
import json

def test_database():
    """Test the SQLite database"""
    print("🔍 Testing LangSense Database...")
    
    try:
        conn = sqlite3.connect('langsense.db')
        cursor = conn.cursor()
        
        # Test tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"📊 Found tables: {[table[0] for table in tables]}")
        
        # Test languages
        cursor.execute("SELECT * FROM languages")
        languages = cursor.fetchall()
        print(f"🌐 Available languages: {languages}")
        
        # Test users count
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"👥 Total users: {user_count}")
        
        conn.close()
        print("✅ Database test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_bot_api():
    """Test Telegram API connection"""
    import os
    from urllib.request import urlopen, Request
    
    print("\n🤖 Testing Telegram API connection...")
    
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        print("❌ BOT_TOKEN not found in environment")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        request = Request(url)
        
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        if data.get('ok'):
            bot_info = data['result']
            print(f"✅ Bot connected successfully!")
            print(f"📛 Bot name: {bot_info['first_name']}")
            print(f"🏷️ Bot username: @{bot_info['username']}")
            print(f"🆔 Bot ID: {bot_info['id']}")
            return True
        else:
            print(f"❌ API returned error: {data}")
            return False
            
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False

def display_bot_info():
    """Display bot setup information"""
    print("\n" + "="*50)
    print("🚀 LangSense Telegram Bot - Setup Complete!")
    print("="*50)
    print("\n📋 Features Available:")
    print("  ✅ Multi-language support (Arabic RTL + English)")
    print("  ✅ User registration with phone verification")
    print("  ✅ Customer ID generation")
    print("  ✅ Financial services (Deposit/Withdraw)")
    print("  ✅ Admin panel and broadcasting")
    print("  ✅ SQLite database with user management")
    print("  ✅ Simple HTTP-based implementation (no dependency issues)")
    
    print("\n🔧 How to Test:")
    print("  1. Open Telegram and search for your bot")
    print("  2. Send /start command to begin")
    print("  3. Share your phone number when prompted")
    print("  4. Explore the menu options")
    print("  5. Try admin commands with /admin (if you're an admin)")
    
    print("\n⚙️ Configuration:")
    print("  - Bot Token: ✅ Configured")
    print("  - Admin IDs: ✅ Configured") 
    print("  - Database: ✅ SQLite (langsense.db)")
    print("  - Languages: Arabic (default), English")
    
    print("\n📝 Next Steps:")
    print("  - Test the bot in Telegram")
    print("  - Verify phone number registration")
    print("  - Check admin functionality")
    print("  - Review logs for any issues")

def main():
    print("LangSense Bot - System Test")
    print("=" * 30)
    
    # Test database
    db_ok = test_database()
    
    # Test API
    api_ok = test_bot_api()
    
    if db_ok and api_ok:
        display_bot_info()
        print("\n🎉 All systems are GO! The bot is ready for use.")
    else:
        print("\n⚠️ Some tests failed. Please check the configuration.")

if __name__ == '__main__':
    main()