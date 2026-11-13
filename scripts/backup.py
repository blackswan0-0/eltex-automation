import argparse
import getpass
import logging
import sys
from datetime import date
from pathlib import Path

from netmiko import (
    ConnectHandler,
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)
from netmiko.base_connection import BaseConnection

INVENTORY = Path("inventory/devices.txt")
KEY = Path.home() / ".ssh" / "eltex_backup"
OUT_DIR = Path("out")
BACKUP_DIR = Path("backups")
SOURCES = ("startup-config", "running-config")  # что бэкапим
MAX_AUTH_FAILS_IN_ROW = 3
MIN_CONFIG_LEN = 200

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Бэкап скрипт сетевого оборудования Eltex MES. Ansible-like, список хостов берется из inventory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-p", "--port", type=int, default=22, help="Порт подключения.")
    parser.add_argument(
        "-i",
        "--inventory",
        type=Path,
        metavar="FILE",
        default=INVENTORY,
        help="Указать путь к файлу inventory.",
    )
    parser.add_argument(
        "-u",
        "--user",
        default=None,
        help="Указать пользователя. Иначе скрипт спросит в начале выполнения.",
    )
    parser.add_argument(
        "-k",
        "--ask-pass",
        action="store_true",
        help="Спросить пароль (по умолчанию ключи).",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        metavar="FILE",
        default=KEY,
        help="Приватный SSH-ключ. Используется, если не задан -k.",
    )
    parser.add_argument(
        "-l",
        "--limit",
        metavar="HOST[,HOST...]",
        default=None,
        help="Ограничить список хостов из inventory.",
    )
    parser.add_argument(
        "--list-hosts",
        action="store_true",
        help="Показать итоговый список хостов (с учетом --limit) и выйти без подключений.",
    )
    return parser.parse_args()


def setup_logger() -> None:
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    OUT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(OUT_DIR / "backup.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_inventory(path: Path) -> list[str]:
    hosts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hosts.append(line)
    return list(dict.fromkeys(hosts))  # дедуп с сохранением порядка


def apply_limit(hosts: list[str], limit: str) -> list[str]:
    parts = [s.strip() for s in limit.split(",") if s.strip()]
    wanted = set(parts)
    missing = wanted - set(hosts)
    if missing:
        raise ValueError(f"not in inventory: {', '.join(sorted(missing))}")
    return [h for h in hosts if h in wanted]


def get_hostname(conn: BaseConnection) -> str:
    name = conn.find_prompt().rstrip("#>").strip()
    return name or "unknown"


def normalize(config: str) -> str:
    """Для сравнения конфигов: игнорируем пустые строки, комментарии '!' и хвостовые пробелы."""
    return "\n".join(
        line.rstrip()
        for line in config.splitlines()
        if line.strip() and not line.strip().startswith("!")
    )


def fetch_config(conn: BaseConnection, source: str) -> str:
    """Забрать конфиг и убедиться, что это конфиг, а не ошибка/пустота"""
    config = conn.send_command(f"show {source}", read_timeout=20)
    if len(config) < MIN_CONFIG_LEN or "interface" not in config:
        raise RuntimeError(f"suspicious 'show {source}' output: {config[:200]!r}")
    return config.rstrip() + "\n"


def backup_one(
    host: str,
    username: str,
    day_dir: Path,
    connect_kwargs: dict,
) -> list[Path]:
    """Бэкап одного коммутатора. Возвращает список сохранённых файлов или бросает исключение."""
    log_dir = OUT_DIR / host
    log_dir.mkdir(parents=True, exist_ok=True)

    common = {
        "device_type": "eltex",
        "host": host,
        "username": username,
        "conn_timeout": 5,
        "auth_timeout": 15,
        "session_log": str(log_dir / "session.log"),
    }
    with ConnectHandler(**{**common, **connect_kwargs}) as conn:
        hostname = get_hostname(conn)

        # сначала забираем и проверяем ВСЁ, только потом пишем на диск,
        # чтобы не осталось половины бэкапа при ошибке на середине
        configs = {source: fetch_config(conn, source) for source in SOURCES}

        saved = []
        for source, config in configs.items():
            path = day_dir / f"{hostname}_{host}_{source}.cfg"
            path.write_text(config, encoding="utf-8")
            saved.append(path)

        if normalize(configs["startup-config"]) != normalize(configs["running-config"]):
            logger.warning(
                "%s: running-config differs from startup-config (unsaved changes?)",
                host,
            )

    return saved


def main() -> int:
    args = parse_args()
    setup_logger()

    try:
        hosts = load_inventory(args.inventory)
        if args.limit:
            try:
                hosts = apply_limit(hosts, args.limit)
            except ValueError as e:
                logger.error("Limit error: %s", e)
                return 1

        if args.list_hosts:
            for h in hosts:
                print(h)
            return 0

    except FileNotFoundError:
        logger.error("Inventory file not found: %s", args.inventory)
        return 1
    if not hosts:
        logger.error("Inventory is empty")
        return 1

    username = args.user or input("Username: ").strip()

    if args.ask_pass:
        password = getpass.getpass("Password: ")
        connect_kwargs = {"password": password}
    else:
        connect_kwargs = {
            "use_keys": True,
            "key_file": str(args.key_file),
        }
    connect_kwargs["port"] = args.port

    ok = fail = auth_fails = skipped = 0

    day_dir = BACKUP_DIR / date.today().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    try:
        for host in hosts:
            try:
                logger.info("Connecting to %s", host)
                saved = backup_one(host, username, day_dir, connect_kwargs)
            except NetmikoAuthenticationException:
                fail += 1
                auth_fails += 1
                logger.error("%s: authentication failed", host)
                if auth_fails >= MAX_AUTH_FAILS_IN_ROW:
                    logger.error("Too many auth failures in a row. Aborting")
                    for rest in hosts[ok + fail :]:
                        logger.warning("%s: skipped (aborted by auth limit)", rest)
                        skipped += 1
                    break
            except NetmikoTimeoutException:
                fail += 1
                auth_fails = 0
                logger.error("%s: timeout / unreachable", host)
            except Exception:
                fail += 1
                auth_fails = 0
                logger.exception("%s: backup failed", host)
            else:
                ok += 1
                auth_fails = 0
                logger.info("Backup %s OK: %s", host, ", ".join(p.name for p in saved))
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C)")

    logger.info("-" * 30)
    logger.info(
        "Backup finished: ok=%s, fail=%s, skipped=%s, total=%s",
        ok,
        fail,
        skipped,
        len(hosts),
    )
    logger.info("Backup saved to %s", day_dir)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
