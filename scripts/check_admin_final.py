import paramiko

HOST = "69.169.108.197"
USER = "root"
PASSWORD = "M12122099m@@@@"


def run(ssh, cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "ignore").strip()
    err = stderr.read().decode("utf-8", "ignore").strip()
    rc = stdout.channel.recv_exit_status()
    with open("output.txt", "a", encoding="utf-8") as f:
        f.write(f"=== CMD: {cmd} ===\nRC: {rc}\nOUT:\n{out}\nERR:\n{err}\n\n")
    print(f"RC:{rc} - output saved to output.txt")
    if err:
        print(f"ERR length: {len(err)}")
    return rc


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("69.169.108.197", username="root", password="M12122099m@@@@", timeout=20)
    try:
        open("output.txt", "w", encoding="utf-8").close()

        run(ssh, "curl -s -o /dev/null -w 'health:%{http_code} time:%{time_total}\n' http://127.0.0.1:8080/health")
        run(ssh, "systemctl is-active boterx-dashboard.service boterx.service")

        print("=== 1. ADMIN LOGIN ===")
        run(ssh, "curl -s -c /tmp/admin_cookies.txt -w 'login:%{http_code} time:%{time_total}\n' 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=1&password=M12122099m@@@@'")

        run(ssh, "curl -s -b /tmp/admin_cookies.txt -w 'dashboard:%{http_code} time:%{time_total}\n' -o /dev/null 'http://127.0.0.1:8080/dashboard'")

        run(ssh, "curl -s -b /tmp/admin_cookies.txt 'http://127.0.0.1:8080/dashboard' > /tmp/dash.html")

        run(ssh, "curl -s -I 'http://127.0.0.1:8080/static/js/app.js?v=20260824b' | grep -i 'content-type\\|cache-control\\|last-modified'")
        run(ssh, "curl -s -I 'http://127.0.0.1:8080/static/js/base-app.js?v=20260824b' | grep -i 'content-type\\|cache-control\\|last-modified'")

        run(ssh, "curl -s -b /tmp/admin_cookies.txt 'http://127.0.0.1:8080/dashboard' > /tmp/dash.html")

        run(ssh, "grep -n 'toggleLang\\|toggleDarkMode\\|lang\\|darkMode' /opt/bot/dashboard/templates/base.html | head -30")

        run(ssh, "curl -s 'http://127.0.0.1:8080/static/js/app.js?v=20260824b' | grep -c 'tr\\|I18N\\|Alpine'")
        run(ssh, "curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260824b' | head -c 2000")

        run(ssh, "journalctl -u boterx-dashboard.service -n 50 --no-pager | grep -i 'error\\|exception\\|undefined\\|ReferenceError\\|t is not defined\\|notifications is not defined\\|activityTicker is not defined'")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()