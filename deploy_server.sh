#!/bin/bash
# ===== Boterx Full Server Deployment =====
# انسخ هذا السكريبت كاملاً والصقه في SSH بعد تسجيل الدخول

echo "🚀 Boterx Full Deployment Starting..."

# 1. تحديد مسار البوت
BOT_DIR=$(find / -name 'comprehensive_bot.py' -maxdepth 5 2>/dev/null | head -1 | xargs dirname)

if [ -z "$BOT_DIR" ]; then
    echo "❌ لم يتم العثور على البوت. سيتم استنساخه من GitHub."
    cd /root
    git clone https://github.com/duxexch/boterx.git bot
    BOT_DIR="/root/bot"
fi

echo "📁 مسار البوت: $BOT_DIR"
cd "$BOT_DIR"

# 2. تحديث الكود
echo "📥 تحديث الكود من GitHub..."
git fetch origin
git reset --hard origin/main
git pull origin main

# 3. تثبيت المتطلبات
echo "📦 تثبيت المتطلبات..."
pip3 install flask flask-bcrypt python-dotenv openpyxl 2>&1 | tail -3

# 4. إضافة متغيرات لوحة التحكم في .env
echo "⚙️ تحديث .env..."
if ! grep -q "DASHBOARD_PORT" .env 2>/dev/null; then
    cat >> .env << 'EOF'

# ===== Dashboard Settings =====
DASHBOARD_PORT=8080
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PASSWORD=boterx_admin_2026
EOF
    echo "✅ تمت إضافة إعدادات اللوحة"
else
    echo "✅ الإعدادات موجودة"
fi

# 5. إيقاف البوت القديم وإعادة تشغيله
echo "🔄 إعادة تشغيل البوت..."
systemctl stop boterx 2>/dev/null
systemctl daemon-reload
systemctl start boterx
systemctl status boterx --no-pager | head -5

# 6. تشغيل لوحة التحكم كـ service
echo "🖥️ إنشاء service للوحة التحكم..."
cat > /etc/systemd/system/boterx-dashboard.service << 'EOF'
[Unit]
Description=Boterx Web Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=__BOT_DIR__
ExecStart=/usr/bin/python3 __BOT_DIR__/run_dashboard.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# استبدال المسار
sed -i "s|__BOT_DIR__|$BOT_DIR|g" /etc/systemd/system/boterx-dashboard.service

systemctl daemon-reload
systemctl enable boterx-dashboard
systemctl start boterx-dashboard
systemctl status boterx-dashboard --no-pager | head -5

# 7. فتح المنفذ
echo "🔓 فتح المنفذ 8080..."
ufw allow 8080/tcp 2>/dev/null
iptables -I INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null

# 8. التحقق
sleep 3
echo ""
echo "========================================"
echo "✅ تم النشر بنجاح!"
echo "========================================"
echo "🤖 البوت: systemctl status boterx"
echo "🖥️ اللوحة: systemctl status boterx-dashboard"
echo "🌐 افتح: http://69.169.108.197:8080"
echo "🔐 كلمة المرور: boterx_admin_2026"
echo "========================================"
