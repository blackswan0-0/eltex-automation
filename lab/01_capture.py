import getpass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HOST = os.environ["ELTEX_HOST"]
USER = os.environ["ELTEX_USER"]
COMMANDS = [
    "show session",
    "show interfaces status",
    "show vlan",
    "show running-config",
]


def connect():
    from netmiko import ConnectHandler

    password = getpass.getpass("Пароль устройства: ")

    conn = ConnectHandler(
        device_type="eltex",
        host=HOST,
        username=USER,
        password=password,
        session_log="out/session.log",
        session_log_record_writes=True,
    )
    print("Приглашение устройства: ", conn.find_prompt())
    return conn


def capture(conn, cmd, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    output = conn.send_command(cmd)
    filename = cmd.replace(" ", "_") + ".txt"
    filepath = outdir / filename
    filepath.write_text(output)
    print(f"Сохранено: {filepath} ({filepath.stat().st_size} байт)")


if __name__ == "__main__":
    conn = connect()
    outdir = Path("out") / HOST
    for cmd in COMMANDS:
        capture(conn, cmd, outdir)
    conn.disconnect()
    print("Готово")
