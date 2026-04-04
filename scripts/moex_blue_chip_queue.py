"""
moex_blue_chip_queue.py — Inspect the live MOEXBC basket via MOEX ISS.

Shows the current blue chip constituents and highlights which tickers do not
yet have local coverage reports in Pilot_Reports/.

Usage:
  python scripts/moex_blue_chip_queue.py
  python scripts/moex_blue_chip_queue.py --date 2026-04-03
  python scripts/moex_blue_chip_queue.py --json
"""

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import find_ticker_files, setup_stdout

ISS_URL = "https://iss.moex.com/iss/statistics/engines/stock/markets/index/analytics/MOEXBC/constituents.json"


def fetch_constituents(tradedate=None):
    params = {"iss.meta": "off"}
    if tradedate:
        params["date"] = tradedate

    url = f"{ISS_URL}?{urlencode(params)}"
    with urlopen(url, timeout=20) as response:
        payload = json.load(response)

    columns = payload["analytics"]["columns"]
    rows = payload["analytics"]["data"]
    items = [dict(zip(columns, row)) for row in rows]
    items.sort(key=lambda item: item.get("weight") or 0, reverse=True)
    return items


def build_report(items):
    covered = set(find_ticker_files().keys())
    missing = [item for item in items if item["ticker"] not in covered]
    report = {
        "tradedate": items[0]["tradedate"] if items else None,
        "count": len(items),
        "covered": len(items) - len(missing),
        "missing": len(missing),
        "constituents": items,
        "missing_constituents": missing,
    }
    return report


def print_report(report):
    print(
        f"MOEXBC на {report['tradedate']}: {report['count']} бумаг | "
        f"покрыто: {report['covered']} | отсутствует: {report['missing']}"
    )
    print("")
    print("Текущий состав:")
    for item in report["constituents"]:
        print(
            f"  {item['ticker']:<5} {item['shortnames']:<20} "
            f"{item['weight']:>5.2f}%"
        )

    print("")
    if report["missing_constituents"]:
        print("Без локальной карточки:")
        for item in report["missing_constituents"]:
            print(
                f"  - {item['ticker']} ({item['shortnames']}), вес {item['weight']:.2f}%"
            )
    else:
        print("Все текущие бумаги MOEXBC уже покрыты локальными карточками.")


def main():
    setup_stdout()
    parser = argparse.ArgumentParser(
        description="Проверить актуальный состав индекса голубых фишек MOEXBC через MOEX ISS."
    )
    parser.add_argument("--date", help="Дата состава в формате YYYY-MM-DD")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести результат в JSON",
    )
    args = parser.parse_args()

    try:
        report = build_report(fetch_constituents(args.date))
    except HTTPError as exc:
        print(f"Ошибка HTTP при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)
    except URLError as exc:
        print(f"Сетевой сбой при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print_report(report)


if __name__ == "__main__":
    main()
