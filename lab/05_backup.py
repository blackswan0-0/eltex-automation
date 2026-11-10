import getpass
from pathlib import Path
import time

INVENTORY = Path("inventory/inventory.example.txt")
USER = input("Type username: ")
TFTP = input("Type IP address TFTP: ")


def load_inventory(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    hosts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        hosts.append(line)
    return hosts


def connect(host, password):
    from netmiko import ConnectHandler

    conn = ConnectHandler(
        device_type="eltex",
        host=host,
        username=USER,
        password=password,
        conn_timeout=5,
        session_log=f"out/{host}/backup_script.log",
        session_log_record_writes=True,
    )
    return conn


def get_hostname(conn):
    return conn.find_prompt().strip("#>").strip()


if __name__ == "__main__":
    hosts = load_inventory(INVENTORY)
    password = getpass.getpass("Пароль от устройств: ")
    ok = 0
    fail = 0

    for host in hosts:
        log_dir = Path(f"out/{host}")
        log_dir.mkdir(parents=True, exist_ok=True)

        conn = None

        try:
            print(f"Try connect to {host}")
            conn = connect(host, password)

            hostname = get_hostname(conn)
            filename = f"{hostname}_{host}.cfg"

            output = conn.send_command(f"copy startup-config tftp://{TFTP}/{filename}")

            if "completed successfully" in output:
                ok += 1
                print(f"[+] {filename}: backup successful")
            else:
                fail += 1
                print(f"[-] {filename}: backup failed")
                print(output)

        except Exception as e:
            fail += 1
            print(f"[-] {host}: {e}")

        finally:
            if conn is not None:
                conn.disconnect()

    print("-" * 30)
    print(f"Успешно: {ok}")
    print(f"Ошибки: {fail}")
    print(f"Всего устройств: {len(hosts)}")
