# دليل النشر — Boterx على VPS

> آخر تحديث: 30 يوليو 2026

---

## 🖥️ السيرفر

| العنصر | القيمة |
|--------|--------|
| **IP** | `69.169.108.197` |
| **نظام التشغيل** | Ubuntu 24.04 |
| **Python** | 3.12.3 |
| **venv** | `/opt/bot/venv` |
| **كود البوت** | `/opt/bot/bot` |

---

## ⚙️ systemd

الخدمة: `boterx.service`

```bash
# حالة الخدمة
systemctl status boterx.service

# إعادة تشغيل
systemctl restart boterx.service

# السجلات
journalctl -u boterx.service -f
```

---

## 🔄 التحديث التلقائي

cron job يفحص GitHub كل دقيقة:
- يسحب آخر commit من `main`
- يعيد تشغيل الخدمة تلقائياً
- السكربت: `/opt/bot/auto_update.sh`

---

## 🔑 متغيرات البيئة

ملف `.env` في `/opt/bot/bot/.env`:

```
BOT_TOKEN=8909512324:AAGWTHWvtHuFXc9TEQ-TNMmbqCsG8fq5Ap0
ADMIN_USER_IDS=7146701713
MULTI_BOT=yes
```

---

## 🚀 النشر الأول

```bash
# 1. تثبيت Python + Git
apt update && apt install -y python3 python3-venv git

# 2. نسخ الكود
cd /opt
git clone https://github.com/duxexch/boterx.git bot/bot

# 3. إنشاء venv
cd /opt/bot
python3 -m venv venv
source venv/bin/activate
pip install python-dotenv openpyxl

# 4. إنشاء .env
cp bot/.env.example bot/.env
nano bot/.env  # ضع التوكن

# 5. systemd service
cat > /etc/systemd/system/boterx.service << 'EOF'
[Unit]
Description=Boterx Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/bot/bot
ExecStart=/opt/bot/venv/bin/python comprehensive_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable boterx
systemctl start boterx

# 6. التحديث التلقائي
cat > /opt/bot/auto_update.sh << 'EOF'
#!/bin/bash
cd /opt/bot/bot
git fetch origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  git pull origin main
  systemctl restart boterx.service
fi
EOF
chmod +x /opt/bot/auto_update.sh

# cron كل دقيقة
(crontab -l 2>/dev/null; echo "* * * * * /opt/bot/auto_update.sh") | crontab -
```

---

## ⚠️ مشاكل شائعة

### البوت لا يعمل بعد تحديث
```bash
# تحقق من السجل
journalctl -u boterx.service -n 50 --no-pager

# تحقق من syntax
cd /opt/bot/bot
/opt/bot/venv/bin/python -c "import py_compile; py_compile.compile('comprehensive_bot.py', doraise=True); py_compile.compile('svrp.py', doraise=True)"
```

### SSH لا يستجيب
البوت قد استهلك كل الذاكرة. أعد تشغيل السيرفر من لوحة تحكم VPS.

### ملفات CSV فارغة
الترحيل التلقائي ينشئ الملفات عند أول تشغيل. تحقق من الصلاحيات:
```bash
ls -la /opt/bot/bot/*.csv
```
