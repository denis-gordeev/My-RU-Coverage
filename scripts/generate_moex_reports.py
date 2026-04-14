"""
generate_moex_reports.py — Генерация базовых MOEX-отчётов из официальной очереди ISS.

Формирует живую очередь из MOEX ISS и создаёт отсутствующие карточки через
русскоязычный workflow add_ticker вместо устаревшего тайваньского генератора.

Применение:
  python scripts/generate_moex_reports.py
  python scripts/generate_moex_reports.py --index MOEXBMI --top 5
  python scripts/generate_moex_reports.py DOMRF AKRN AFLT
  python scripts/generate_moex_reports.py --dry-run --all-missing
"""

import argparse
import os
import sys
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from add_ticker import generate_report, sanitize_folder_name
from moex_blue_chip_queue import DEFAULT_INDEX_CODES, build_report
from utils import REPORTS_DIR, find_ticker_files, setup_stdout

REPORT_OVERRIDES = {
    "DOMRF": {
        "name": "ДОМ.РФ",
        "sector": "Финансовые услуги",
        "industry": "Кредитные услуги",
    },
    "AKRN": {
        "name": "Акрон",
    },
    "AFLT": {
        "name": "Аэрофлот",
    },
    "CBOM": {
        "name": "Московский кредитный банк",
        "sector": "Финансовые услуги",
        "industry": "Банки — региональные",
    },
    "BSPB": {
        "name": "Банк Санкт-Петербург",
        "sector": "Финансовые услуги",
        "industry": "Банки — региональные",
    },
    "AFKS": {
        "name": "АФК Система",
    },
    "ENPG": {
        "name": "ЭН+ ГРУП",
    },
    "CNRU": {
        "name": "Циан",
    },
    "BANEP": {
        "name": "Башнефть ап",
    },
    "ASTR": {
        "name": "Астра",
    },
    "AQUA": {
        "name": "Инарктика",
    },
    "BELU": {
        "name": "НоваБев Групп",
    },
    "ETLN": {
        "name": "Эталон",
    },
    "EUTR": {
        "name": "ЕвроТранс",
    },
    "DATA": {
        "name": "Аренадата",
    },
    "APTK": {
        "name": "Аптеки 36 и 6",
    },
    "BAZA": {
        "name": "БАЗИС",
    },
    "ELFV": {
        "name": "ЭЛ5-Энерго",
    },
}

SHORTNAME_SUFFIXES = (" ао", " ап", "-ао", "-ап")


def normalize_company_name(ticker, shortname):
    override = REPORT_OVERRIDES.get(ticker, {})
    if override.get("name"):
        return override["name"]

    cleaned = (shortname or ticker).strip()
    if cleaned[:1].lower() == "i" and len(cleaned) > 1 and cleaned[1].isalpha():
        cleaned = cleaned[1:]
    lowered = cleaned.lower()
    for suffix in SHORTNAME_SUFFIXES:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned.strip(" .") or ticker


def select_queue_items(report, requested_tickers=None):
    queue = report["next_queue"]
    if not requested_tickers:
        return queue

    lookup = {item["ticker"]: item for item in queue}
    items = []
    for ticker in requested_tickers:
        item = lookup.get(ticker)
        if item is None:
            items.append(
                {
                    "ticker": ticker,
                    "shortnames": REPORT_OVERRIDES.get(ticker, {}).get("name", ticker),
                }
            )
        else:
            items.append(item)
    return items


def build_output_path(ticker, company_name, sector_name):
    safe_sector = sanitize_folder_name(sector_name)
    filename = f"{ticker}_{company_name}.md"
    return os.path.join(REPORTS_DIR, safe_sector, filename)


def create_reports(items, limit=None, dry_run=False):
    existing = find_ticker_files()
    created = 0
    skipped = 0

    for item in items:
        if limit is not None and created >= limit:
            break

        ticker = item["ticker"]
        if ticker in existing:
            print(f"  {ticker}: пропуск (карточка уже существует)")
            skipped += 1
            continue

        override = REPORT_OVERRIDES.get(ticker, {})
        company_name = normalize_company_name(ticker, item.get("shortnames", ticker))
        sector = override.get("sector")
        industry = override.get("industry")
        content, detected_sector = generate_report(ticker, company_name, sector, industry)
        target_sector = sector or detected_sector or "Unknown"
        output_path = build_output_path(ticker, company_name, target_sector)

        if dry_run:
            print(f"  {ticker}: черновик -> {output_path}")
            created += 1
            continue

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        print(f"  {ticker}: создано -> {output_path}")
        created += 1

    return created, skipped


def main():
    setup_stdout()
    parser = argparse.ArgumentParser(
        description=(
            "Создать базовые MOEX-карточки по живой очереди из MOEX ISS без "
            "опоры на legacy-Excel."
        )
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Явно указанные тикеры. Если не заданы, используется очередь missing из MOEX ISS.",
    )
    parser.add_argument("--date", help="Дата состава индекса в формате YYYY-MM-DD")
    parser.add_argument(
        "--index",
        dest="indices",
        action="append",
        help=(
            "Код индекса MOEX ISS. Можно повторять несколько раз; по умолчанию "
            "используются MOEXBC и MOEXBMI."
        ),
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Сколько новых карточек создать из начала очереди. По умолчанию 5.",
    )
    parser.add_argument(
        "--all-missing",
        action="store_true",
        help="Игнорировать лимит --top и обработать всю очередь missing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать, какие карточки будут созданы, без записи файлов.",
    )
    args = parser.parse_args()

    index_codes = args.indices or DEFAULT_INDEX_CODES
    try:
        report = build_report(index_codes, args.date)
    except HTTPError as exc:
        print(f"Ошибка HTTP при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)
    except URLError as exc:
        print(f"Сетевой сбой при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)

    items = select_queue_items(report, [ticker.upper() for ticker in args.tickers])
    if not items:
        print("Очередь уже покрыта: новых карточек для создания нет.")
        return

    limit = None if args.all_missing or args.tickers else max(args.top, 0)
    print(
        f"Генерирую базовые MOEX-карточки из очереди {', '.join(index_codes)} "
        f"на дату {report['tradedate']}..."
    )
    created, skipped = create_reports(items, limit=limit, dry_run=args.dry_run)
    print(f"\nГотово. Создано: {created} | Пропущено: {skipped}")


if __name__ == "__main__":
    main()
