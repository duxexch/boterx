import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# Fix: 1 worker with 100 threads (all in one process so daemon works)
service_new = """[Unit]
Description=Boterx Web Dashboard
After=network.target

[Service]
LimitNOFILE=65535
LimitNPROC=65535
Type=simple
User=root
WorkingDirectory=/opt/bot
ExecStart=/opt/bot/venv/bin/python3 -m gunicorn --workers 1 --threads 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50 -b 0.0.0.0:8080 dashboard.app:app
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
Environment=DASHBOARD_SECRET_KEY=7fc1f340e7d9f7efce5bec85ae536b75629e73a3b0dc2a321a552d4c39ecdf64
Environment=DASHBOARD_PASSWORD=Vex-LN36X_SG3bv-UNooqkME
Environment=APP_ENV=production
Environment=ADMIN_USER_IDS=7146701713

[Install]
WantedBy=multi-user.target
"""

stdin, stdout, stderr = ssh.exec_command(f"cat > /etc/systemd/system/boterx-dashboard.service << 'ENDOFSERVICE'\n{service_new}ENDOFSERVICE")
stdout.read()

cmds = [
    'systemctl daemon-reload',
    'systemctl restart boterx-dashboard',
    'sleep 4',
    'systemctl is-active boterx-dashboard',
]
for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    print(f'{cmd}: {out.strip()}')

ssh.close()
