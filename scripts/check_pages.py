import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Check key admin pages
pages = [
    "/dashboard",
    "/users",
    "/transactions",
    "/agents",
    "/companies",
    "/payment-methods",
    "/apps",
    "/broadcast",
    "/channels",
    "/ai-api-keys",
    "/lottery",
    "/wheel",
    "/matching",
    "/trading",
    "/svrp",
    "/referrals",
    "/games-admin",
]

with open("pages_check.txt", "w", encoding="utf-8") as f:
    for page in pages:
        s, o, e = ssh.exec_command(f"curl -s -b /tmp/admin_cookies.txt -w '%{{http_code}}' -o /dev/null 'http://127.0.0.1:8080{page}'", timeout=30)
        out = o.read().decode('utf-8', 'ignore').strip()
        f.write(f"{page}: {out}\n")
        print(f"{page}: {out}")

print("Done")
ssh.close()