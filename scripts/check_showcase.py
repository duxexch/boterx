import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Check showcase page
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/x/showcase?k=eyJzY29wZSI6ImRlY2siLCJleHAiOjAsIm5vbmNlIjoibVFxSFp1aWdLTjVIIiwicGVybWFuZW50Ijp0cnVlfQ.9575f071aa4c3fb15a9c6c5fce498148e2a53749aa1ea6d3bb05f205cf7faf51' | head -c 5000", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('showcase_check.txt', 'w', encoding='utf-8') as f:
    f.write(out)

print('Done')
ssh.close()