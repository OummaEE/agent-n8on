"""
main.py — CLI entrypoint  Facebook Group Events Scraper v4.0

Запуск:
    python main.py                              # читает всё из .env
    python main.py --force --headless           # принудительный запуск, headless
    python main.py --groups "url1,url2"         # переопределить группы
    python main.py --no-supabase                # пропустить Supabase
    python main.py --output events_test.csv     # другой выходной файл
    python main.py --log-level DEBUG            # подробные логи

n8n (Execute Command, Windows):
    python "C:\\path\\to\\main.py" --headless --force
"""

import argparse
import asyncio
import logging
import os
import sys


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Facebook Group Events Scraper — CLI entrypoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
примеры:
  python main.py
  python main.py --force --headless
  python main.py --groups "https://www.facebook.com/groups/g1,https://www.facebook.com/groups/g2"
  python main.py --no-supabase --output events_test.csv
  python main.py --log-level DEBUG --log-file debug.log
        """.strip(),
    )
    p.add_argument(
        "--groups", metavar="URLS",
        help="Через запятую URL групп (переопределяет GROUP_URLS из .env)",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Принудительный запуск, игнорируя суточный лимит (FORCE_RUN=true)",
    )
    p.add_argument(
        "--no-supabase", action="store_true", dest="no_supabase",
        help="Пропустить Supabase upsert, сохранять только в CSV",
    )
    p.add_argument(
        "--output", metavar="FILE",
        help="Выходной CSV файл (переопределяет OUTPUT_FILE из .env)",
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Запустить браузер в headless режиме (переопределяет HEADLESS из .env)",
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        dest="log_level", metavar="LEVEL",
        help="Уровень логирования (по умолчанию: INFO)",
    )
    p.add_argument(
        "--log-file", default="scraper.log", metavar="FILE",
        dest="log_file",
        help="Файл лога (по умолчанию: scraper.log)",
    )
    return p.parse_args()


def _apply_cli_to_env(args: argparse.Namespace) -> None:
    """
    Применяет CLI-аргументы как переменные окружения.
    Вызывается ДО импорта scraper-модулей, так как config.py читает os.getenv
    при импорте.
    """
    if args.groups:
        os.environ["GROUP_URLS"] = args.groups
    if args.force:
        os.environ["FORCE_RUN"] = "true"
    if args.no_supabase:
        # Очищаем Supabase credentials → supabase_client.is_configured() вернёт False
        os.environ["SUPABASE_URL"] = ""
        os.environ["SUPABASE_KEY"] = ""
    if args.output:
        os.environ["OUTPUT_FILE"] = args.output
    if args.headless:
        os.environ["HEADLESS"] = "true"


def _setup_logging(level: str = "INFO", log_file: str = "scraper.log") -> None:
    """Настраивает единый формат логов для всех модулей."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s  [%(levelname)s]  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Убираем шум от внешних библиотек
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


if __name__ == "__main__":
    args = _parse_args()

    # Применяем CLI → env ДО импорта scraper (config.py читает env при import)
    _apply_cli_to_env(args)
    _setup_logging(level=args.log_level, log_file=args.log_file)

    # Импортируем run только после патча env
    from scraper.run import run  # noqa: E402

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[WARN] Остановлено пользователем.")
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code)
