import getpass
import time
from pathlib import Path

INVENTORY = Path("inventory/inventory.example.txt")
USER = "automation"
NTP_SERVER = "192.0.2.20"
COMMANDS = [
    "clock timezone MSK +3",
    "clock source ntp",
    f"ntp server {NTP_SERVER}",
]


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
        session_log=f"out/{host}/ntp_script.log",
        session_log_record_writes=True,
    )
    return conn


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

            conn.send_config_set(COMMANDS)

            time.sleep(10)

            output = conn.send_command("show ntp associations")

            if "*~" in output and NTP_SERVER in output:
                ok += 1
                print(f"[{host}]: OK")
                output = conn.send_command_timing("wr")
                if "Overwrite file" in output:
                    output += conn.send_command_timing("Y")
            else:
                fail += 1
                print(f"[{host}] -> ERROR: no ntp server")

        except Exception as e:
            fail += 1
            print(f"{host} -> ERROR: {type(e).__name__}: {e}")

        finally:
            if conn is not None:
                conn.disconnect()

    print("-" * 30)
    print(f"Успешно: {ok}")
    print(f"Ошибки: {fail}")
    print(f"Всего устройств: {len(hosts)}")
