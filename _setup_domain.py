#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

def run(cmd, t=20):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=t)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out + ('\n' + err if err else '')

# 1. Read current nginx config
print("=== Current nginx config ===")
print(run('cat /etc/nginx/sites-enabled/boterx-dashboard'))

# 2. Create vex.deals nginx config
print("\n=== Creating vex.deals config ===")
nginx_conf = """server {
    listen 80;
    server_name vex.deals www.vex.deals;
    
    # Redirect HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vex.deals www.vex.deals;
    
    # SSL certificates (will be created by certbot)
    ssl_certificate /etc/letsencrypt/live/vex.deals/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vex.deals/privkey.pem;
    
    # Proxy to Flask dashboard
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Static files
    location /static/ {
        alias /opt/bot/dashboard/static/;
        expires 30d;
    }
    
    # SSE support
    location /api/notifications/stream {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }
}
"""

# Write config
run(f"cat > /etc/nginx/sites-available/vex.deals << 'NGINX_EOF'\n{nginx_conf}\nNGINX_EOF")
run('ln -sf /etc/nginx/sites-available/vex.deals /etc/nginx/sites-enabled/vex.deals')
print("Config created")

# 3. First test nginx without SSL (will fail but that's ok)
test = run('nginx -t 2>&1')
print("nginx test (will fail on SSL):", test[:200])

# 4. Get SSL certificate with certbot
print("\n=== Getting SSL certificate ===")
# First remove the SSL config temporarily, get cert, then re-enable
run('rm /etc/nginx/sites-enabled/vex.deals')

# Create HTTP-only config for certbot
http_conf = """server {
    listen 80;
    server_name vex.deals www.vex.deals;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
"""
run(f"cat > /etc/nginx/sites-available/vex.deals << 'EOF'\n{http_conf}\nEOF")
run('ln -sf /etc/nginx/sites-available/vex.deals /etc/nginx/sites-enabled/vex.deals')
run('nginx -t 2>&1 && systemctl reload nginx')

# Get cert
cert_result = run('certbot certonly --nginx -d vex.deals -d www.vex.deals --non-interactive --agree-tos --email admin@vex.deals 2>&1', t=60)
print("Certbot result:", cert_result[:500])

# 5. Now write the full SSL config
run(f"cat > /etc/nginx/sites-available/vex.deals << 'NGINX_EOF'\n{nginx_conf}\nNGINX_EOF")
test2 = run('nginx -t 2>&1')
print("\nnginx test with SSL:", test2[:200])
run('systemctl reload nginx 2>&1')

# 6. Test HTTPS
time.sleep(2)
print("\n=== Testing HTTPS ===")
print(run('curl -s -o /dev/null -w "%{http_code}" https://vex.deals/login 2>&1'))
print(run('curl -s -o /dev/null -w "%{http_code}" https://vex.deals/webapp/games?uid=7146701713 2>&1'))

ssh.close()
