#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko, sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

stdin, stdout, stderr = ssh.exec_command('journalctl -u boterx --no-pager -n 80 2>&1')
logs = stdout.read().decode('utf-8', errors='replace')

# Print lines with errors
for line in logs.split('\n'):
    if any(kw in line for kw in ['Traceback', 'Error:', 'Exception:', 'NameError', 'SyntaxError', 'ImportError', 'File "', 'line ']):
        sys.stdout.buffer.write((line + '\n').encode('utf-8'))

ssh.close()
