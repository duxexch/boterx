# Development Guide — LangSense / DUX Bot

> Coding conventions, patterns, state machine reference, and contribution rules.

---

## 1. Coding Conventions

### 1.1 Language & Encoding
- **Python 3.8+** required
- All CSV files use `utf-8-sig` encoding (BOM for Excel compatibility)
- All string literals with Arabic text must be in double quotes or triple-quoted strings

### 1.2 Bot API Pattern (comprehensive_bot.py)
```python
# All Telegram API calls go through api_call():
def api_call(self, method, data=None):
    url = f"{self.api_url}/{method}"
    json_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=json_data)
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode('utf-8'))

# Sending messages:
self.send_message(chat_id, text, keyboard)
# keyboard is a dict with 'keyboard' or 'inline_keyboard' key
```

### 1.3 CSV Read Pattern
```python
# READ:
with open('file.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # row is a dict with column names as keys

# WRITE (append):
with open('file.csv', 'a', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow([val1, val2, ...])

# WRITE (full rewrite):
with open('file.csv', 'w', newline='', encoding='utf-8-sig') as f:
    fieldnames = ['col1', 'col2', ...]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_list)
```

### 1.4 State Machine Pattern
```python
# Set state:
self.user_states[user_id] = 'state_name_param1_param2'

# Check state:
state = self.user_states.get(user_id, '')
if state.startswith('state_name_'):
    parts = state.split('_')
    param1 = parts[2]  # after 'state_name'
    param2 = parts[-1]  # last element (for single trailing param)

# Clear state:
if user_id in self.user_states:
    del self.user_states[user_id]
```

### 1.5 Keyboard Pattern
```python
# Reply keyboard:
keyboard = {
    'keyboard': [
        [{'text': 'Button 1'}, {'text': 'Button 2'}],  # row
        [{'text': 'Button 3'}]  # another row
    ],
    'resize_keyboard': True,
    'one_time_keyboard': False
}

# Inline keyboard:
keyboard = {
    'inline_keyboard': [
        [{'text': '✅ Confirm', 'callback_data': 'confirm_123'}]
    ]
}
```

### 1.6 Admin Command Format
```
Text commands:     command param1 param2 ...
Example:           موافقة DEP20260723143000
                   رفض WTH20260723143000 سبب_الرفض
                   حظر C824717 مخالفة
                   بحث أحمد
                   اضافة_شركة STC_Pay both محفظة_رقمية

Button commands:   "📋 الطلبات المعلقة" → handle_admin_actions() routes
```

### 1.7 Translation Pattern (comprehensive_bot.py)
```python
# Inline translations dict:
self.translations = {
    'key_name': {
        'ar': "نص عربي {placeholder}",
        'en': "English text {placeholder}"
    }
}

# Usage:
text = self.tr('key_name', lang, placeholder=value)
```

### 1.8 Notification Pattern
```python
# Notify all admins:
for admin_id in self.admin_ids:
    try:
        self.send_message(admin_id, message, action_keyboard)
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
```

---

## 2. When Adding New Features

### Adding a new user flow:
1. Add state names to `user_states` in the handler
2. Add state check in `process_message()` before the main menu routing
3. Add cleanup in `super_reset_user_system()`
4. Add translations for all user-facing strings
5. Add admin notifications if needed
6. Test with both AR and EN languages

### Adding a new admin command:
1. Add button to `admin_keyboard()` (respect permissions)
2. Add handler in `handle_admin_actions()` if/elif chain
3. Implement the handler method
4. Add to `show_quick_copy_commands()` if text-based
5. Log with `log_admin_action()`
6. Test with admin and non-admin users

### Adding a new CSV data file:
1. Add initialization in `init_files()`
2. Add to `verify_and_fix_system_files()` required_files list
3. Add read/write helpers following the CSV pattern above
4. Add to backup in `create_backup_zip()` files_to_backup list
5. Add to Excel report in `create_professional_excel_report()`

### Adding a new currency:
1. Add to `self.currencies` dict in `__init__()`
2. Format: `'CODE': {'name': 'Arabic name', 'symbol': 'symbol', 'flag': 'emoji'}`
3. Test with `show_currency_selection()` and `handle_currency_selection()`

---

## 3. Critical Patterns to Preserve

### 3.1 Button Label Override System
The bot supports admin-editable button text. When sending keyboards:
- `transform_keyboard()` applies overrides before sending
- `normalize_button_text()` reverses overrides when receiving

**Rule:** Always use `self.apply_button_label()` and `self.normalize_button_text()` — never hardcode button text matching without going through these.

### 3.2 Admin Permission Filtering
`admin_keyboard()` filters buttons based on `admin_permissions.json`. The `current_admin_id` must be set before calling `admin_keyboard()`.

**Rule:** Always set `self.current_admin_id = user_id` in `handle_admin_panel()` before generating the keyboard.

### 3.3 Currency Awareness
All amount displays should use `format_amount_with_currency()`:
```python
formatted = self.format_amount_with_currency(amount, user_currency)
```
Never hardcode "ريال" — always use the user's selected currency symbol.

### 3.4 Broadcast Without Keyboard
Broadcast messages must NOT include keyboards to avoid overwriting user's current state:
```python
self.send_message(telegram_id, broadcast_msg, None)  # None = no keyboard
```

### 3.5 Error Recovery
Every user-facing error should offer reset options:
```python
error_keyboard = {
    'keyboard': [
        [{'text': '🔄 إعادة تعيين النظام'}, {'text': '🆘 إصلاح شامل'}],
        [{'text': '💰 طلب إيداع'}, {'text': '💸 طلب سحب'}]
    ],
    'resize_keyboard': True
}
```

---

## 4. Testing Checklist

Before deploying changes:

- [ ] Bot starts without errors (`python comprehensive_bot.py`)
- [ ] `/start` works for new user (registration flow)
- [ ] `/start` works for returning user (main menu)
- [ ] Deposit flow: company → method → wallet → amount → confirmation
- [ ] Withdrawal flow: company → method → wallet → amount → address → code → confirm
- [ ] Admin panel opens (`/admin`)
- [ ] Admin can approve/reject transactions
- [ ] Company add/edit/delete works
- [ ] Payment method add/edit/delete works
- [ ] Broadcast sends to all users
- [ ] Currency change works
- [ ] Language switch (AR ↔ EN) works
- [ ] Ban/unban works
- [ ] Complaint submission + admin reply works
- [ ] Excel report generates
- [ ] Manual backup creates ZIP and sends
- [ ] Button label editing works
- [ ] Reset system (`🔄 إعادة تعيين النظام`) clears state

---

## 5. File Modification Rules

### Files safe to modify:
- `comprehensive_bot.py` — the main bot, add features here
- `excel_formatter.py` — report formatting
- `translations/ar.json`, `translations/en.json` — Aiogram version strings
- `handlers/*.py` — Aiogram version (if being developed)
- Run scripts (`run_windows.bat`, `run_linux.sh`)

### Files to NOT modify without backup:
- `*.csv` data files — contain live data
- `admin_permissions.json` — contains permission config
- `button_labels.csv` — admin customizations
- `backup_server_files/` — reference snapshot

### Files to consider removing (legacy):
- `advanced_bot.py`, `simple_bot.py`, `simple_improved_bot.py`
- `simple_payment_bot.py`, `fixed_bot.py`, `excel_bot.py`
- These are superseded by `comprehensive_bot.py`

---

## 6. Logging

Current logging configuration:
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
```

Log file: `bot.log` (configured in config.py but comprehensive_bot.py logs to console only)

**Rule:** Use `logger.info()` for normal operations, `logger.error()` for failures, `logger.warning()` for recoverable issues. Never log sensitive data (tokens, phone numbers).
