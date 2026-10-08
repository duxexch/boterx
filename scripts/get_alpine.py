import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

sftp = ssh.open_sftp()
sftp.get('/opt/bot/dashboard/static/vendor/alpine.min.js', 'dashboard/static/vendor/alpine.min.js')
sftp.close()
ssh.close()
print("Alpine downloaded")