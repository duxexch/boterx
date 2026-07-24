# replit.md

## Overview

LangSense is a streamlined Telegram bot for financial services with Arabic support. The bot provides a simplified financial ecosystem focusing on deposit/withdrawal processing with company selection, wallet number input, and exchange address management. Features include user registration, admin approval system, and comprehensive transaction tracking.

## User Preferences

Preferred communication style: Simple, everyday language.
UI Design: Button-based navigation preferred over text commands.
Notifications: Only at completion of operations, not during process.
Admin Commands: Simplified format without complex syntax requirements.

## System Architecture

### Core Framework
- **Bot Framework**: Simplified HTTP-based Telegram Bot API implementation using Python standard library
- **Language**: Python 3 with urllib and json for lightweight operation
- **State Management**: Simple dictionary-based state management for user sessions
- **Implementation**: Streamlined single-file solution without external dependencies
- **Backup System**: Automated data backup every 6 hours with ZIP compression and admin delivery

### Database Layer
- **Database**: CSV files for simplicity and transparency
- **Files**: users.csv, transactions.csv, companies.csv, exchange_addresses.csv, system_settings.csv
- **Schema**: Simplified tables focusing on essential data only with currency support
- **Currency Storage**: User currency preferences stored in users.csv, transaction currencies in transactions.csv
- **Data Integrity**: Automatic customer code generation, basic validation, currency consistency

### User Interface
- **Navigation**: Button-based keyboards for all interactions
- **Language**: Arabic primary with simple interface
- **Flow**: Linear process flows for deposits and withdrawals
- **Withdrawal Confirmation**: Button-based final confirmation with "✅ تأكيد الطلب", "❌ إلغاء", and "🏠 القائمة الرئيسية"
- **Advanced Reset System**: "🔄 إعادة تعيين النظام" and "🆘 إصلاح شامل" buttons for comprehensive error resolution
- **Super Reset Function**: Complete system cleanup including user states, temporary data, and file integrity verification
- **Error Recovery**: Enhanced error messages with multiple reset options and alternative action buttons
- **System Diagnostics**: Automatic verification and repair of core system files
- **Simplicity**: No complex commands or syntax requirements

### Authentication & Authorization
- **Admin System**: Environment variable-based admin user ID configuration
- **User Registration**: Name and phone number only
- **Session Management**: Simple state tracking for multi-step processes

### Financial Services Workflow
- **Enhanced Deposit Process**: Company Selection → **Payment Method Selection** → Wallet Number → Amount → Completion
- **Enhanced Withdrawal Process**: Company Selection → **Payment Method Selection** → Wallet Number → Amount → **Withdrawal Address Entry** → **Confirmation Code Entry** → Final Confirmation
- **Multi-Currency Support**: Users can select from 18 currencies including all Arab countries, USD, EUR, and Turkish Lira
- **Currency Integration**: All transactions, amounts, and financial displays use user's selected currency
- **Default Currency**: Saudi Riyal (SAR) with ability to change via "تغيير العملة" button
- **Payment Method Integration**: Users select specific payment methods for each company (bank accounts, e-wallets, etc.)
- **Status Tracking**: Simple pending/approved/rejected states
- **Admin Approval**: Direct text-based commands (موافقة/رفض)
- **Withdrawal Address**: Users must specify withdrawal address for each request
- **Confirmation Code**: Required verification code from customer before processing

### Company & Payment Method Management
- **Enhanced Company Management**: Interactive step-by-step wizards for adding, editing, and deleting companies
- **Comprehensive Payment Method System**: 
  - Multiple payment methods per company (bank accounts, e-wallets, investment accounts)
  - Customizable payment data fields for each method
  - Admin CRUD operations (add, edit, delete) for payment methods
  - User selection of payment methods during transactions
- **User-Friendly Interface**: Button-based navigation with confirmation dialogs and real-time preview
- **Advanced Features**: 
  - Add Company Wizard: Name → Service Type (buttons) → Details → Confirmation with edit options
  - Payment Method Management: Add/Edit/Delete methods with custom data fields
  - Edit Company Wizard: Select company → Edit any field → Live preview → Safe save
  - Delete Company: Safety confirmation with company details display
  - Management Dashboard: Enhanced view with company count, status indicators, and quick actions
- **Exchange Address**: Single active address that can be updated easily
- **Flexibility**: Dynamic company list for both deposits and withdrawals with method selection

### Notifications
- **Timing**: Only at completion of operations (approval/rejection) + instant notifications for new requests
- **Content**: Essential information only
- **Direction**: Bidirectional (admin ↔ user) at completion + instant admin alerts for new transactions
- **Admin Alerts**: Immediate notifications when users submit deposit/withdrawal requests
- **Customer Alerts**: Instant notifications upon approval/rejection with full transaction details
- **Broadcast Messages**: Sent without keyboard markup to prevent interference with existing user interfaces
- **Direct Admin Messages**: Individual customer messages sent without keyboard to preserve current user state

### Admin Interface
- **Commands**: Simplified text-based commands with enhanced copy functionality
- **Format**: Natural language without complex syntax
- **Enhanced Copy System**: 
  - Quick copy commands for each transaction (approve/reject)
  - Quick copy responses for complaints with templates
  - Comprehensive quick copy commands section with all admin operations
  - Pre-formatted commands for easy copying and modification
- **Direct User Messaging**: Send targeted messages to specific customers using their customer ID
- **Enhanced Payment Method Management**: Full CRUD operations with interactive selection interfaces
- **Easy Copy Payment Data**: Customer-friendly display of payment account information with copy functionality
- **Payment Method Commands**: 
  - `اضافة_وسيلة_دفع ID_الشركة اسم_الوسيلة نوع_الوسيلة البيانات`
  - `حذف_وسيلة_دفع ID_الوسيلة`
  - `تعديل_وسيلة_دفع ID_الوسيلة البيانات_الجديدة`
- **Professional Excel Reports**: 
  - Button: "📊 تقرير Excel احترافي" for comprehensive data export
  - CSV format with professional formatting and Arabic support
  - Comprehensive statistics with percentages and detailed breakdowns
  - Organized sections: Users, Transactions, Complaints, Companies, Payment Methods
  - Real-time data analysis with currency breakdowns and performance metrics
- **Examples**: "موافقة DEP123", "رفض WTH456 سبب", "اضف_شركة اسم نوع تفاصيل"
- **Navigation**: Button-based admin panel with payment method management

### Error Handling & Logging
- **Logging**: Basic console logging for monitoring
- **Validation**: Simple input validation with clear error messages
- **Fallbacks**: Graceful handling of invalid inputs
- **Data Protection**: Automated backup system every 6 hours with encrypted ZIP files sent to admin accounts
- **Manual Backup**: Admin command for instant backup generation and delivery
- **Backup Contents**: All CSV files, system settings, and comprehensive statistical reports

## External Dependencies

### Core Dependencies
- **Aiogram v3**: Modern Telegram Bot API framework with async support
- **SQLAlchemy**: Async ORM for database operations and relationship management
- **APScheduler**: Task scheduling for announcements and periodic operations
- **Pillow**: Image processing for media validation and manipulation

### Database Options
- **SQLite**: Default development database with aiosqlite driver
- **PostgreSQL**: Production database with asyncpg driver for scalability

### Runtime Dependencies
- **Python-dotenv**: Environment variable management and configuration loading
- **AsyncIO**: Core async runtime for handling concurrent operations

### Optional Integrations
- **File Storage**: Local file system for media uploads (configurable for cloud storage)
- **External APIs**: Extensible architecture for payment provider integrations
- **Monitoring Services**: Ready for integration with external logging and monitoring platforms