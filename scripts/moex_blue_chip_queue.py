"""
moex_blue_chip_queue.py — Inspect official MOEX constituent baskets via ISS.

Shows the current constituents for one or more MOEX indices and highlights
which tickers do not yet have local coverage reports in Pilot_Reports/.
By default, combines the fully covered blue-chip basket (MOEXBC) with the
broader liquid market basket (MOEXBMI) to surface the next coverage wave.

Usage:
  python scripts/moex_blue_chip_queue.py
  python scripts/moex_blue_chip_queue.py --index MOEXBC
  python scripts/moex_blue_chip_queue.py --index MOEXBMI --date 2026-04-03
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
DEFAULT_INDEX_CODES = ["MOEXBC", "MOEXBMI"]
INDEX_LABELS = {
    "MOEXBC": "Индекс голубых фишек",
    "MOEXBMI": "Индекс широкого рынка",
}


def fetch_constituents(index_code, tradedate=None):
    params = {"iss.meta": "off"}
    if tradedate:
        params["date"] = tradedate

    iss_url = ISS_URL.replace("/MOEXBC/", f"/{index_code}/")
    url = f"{iss_url}?{urlencode(params)}"
    with urlopen(url, timeout=20) as response:
        payload = json.load(response)

    columns = payload["analytics"]["columns"]
    rows = payload["analytics"]["data"]
    items = [dict(zip(columns, row)) for row in rows]
    items.sort(key=lambda item: item.get("weight") or 0, reverse=True)
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return items


def build_index_report(index_code, items):
    covered = set(find_ticker_files().keys())
    missing = [item for item in items if item["ticker"] not in covered]
    report = {
        "index_code": index_code,
        "index_label": INDEX_LABELS.get(index_code, index_code),
        "tradedate": items[0]["tradedate"] if items else None,
        "count": len(items),
        "covered": len(items) - len(missing),
        "missing": len(missing),
        "constituents": items,
        "missing_constituents": missing,
    }
    return report


def build_report(index_codes, tradedate=None):
    index_reports = []
    aggregated_missing = {}
    tradedates = []

    for index_code in index_codes:
        items = fetch_constituents(index_code, tradedate)
        index_report = build_index_report(index_code, items)
        index_reports.append(index_report)
        if index_report["tradedate"]:
            tradedates.append(index_report["tradedate"])

        for item in index_report["missing_constituents"]:
            ticker = item["ticker"]
            existing = aggregated_missing.get(ticker)
            if existing is None:
                aggregated_missing[ticker] = {
                    "ticker": ticker,
                    "shortnames": item["shortnames"],
                    "indices": [index_code],
                    "best_rank": item["rank"],
                    "max_weight": item["weight"],
                }
                continue

            existing["indices"].append(index_code)
            existing["best_rank"] = min(existing["best_rank"], item["rank"])
            existing["max_weight"] = max(existing["max_weight"], item["weight"])

    next_queue = sorted(
        aggregated_missing.values(),
        key=lambda item: (item["best_rank"], -item["max_weight"], item["ticker"]),
    )

    return {
        "requested_indices": index_codes,
        "tradedate": max(tradedates) if tradedates else None,
        "reports": index_reports,
        "next_queue": next_queue,
    }


def print_report(report):
    for index_report in report["reports"]:
        print(
            f"{index_report['index_code']} ({index_report['index_label']}) на "
            f"{index_report['tradedate']}: {index_report['count']} бумаг | "
            f"покрыто: {index_report['covered']} | отсутствует: {index_report['missing']}"
        )
        print("")
        print("Текущий состав:")
        for item in index_report["constituents"]:
            print(
                f"  #{item['rank']:<2} {item['ticker']:<6} {item['shortnames']:<20} "
                f"{item['weight']:>5.2f}%"
            )

        print("")
        if index_report["missing_constituents"]:
            print("Без локальной карточки:")
            for item in index_report["missing_constituents"]:
                print(
                    f"  - #{item['rank']:<2} {item['ticker']} ({item['shortnames']}), "
                    f"вес {item['weight']:.2f}%"
                )
        else:
            print("Все текущие бумаги этого индекса уже покрыты локальными карточками.")
        print("")

    if report["next_queue"]:
        print("Следующая агрегированная очередь покрытия:")
        for item in report["next_queue"]:
            indices = ", ".join(item["indices"])
            print(
                f"  - #{item['best_rank']:<2} {item['ticker']} ({item['shortnames']}), "
                f"индексы: {indices}, макс. вес {item['max_weight']:.2f}%"
            )
    else:
        print("Объединённая очередь индексов уже полностью покрыта локальными карточками.")


def main():
    setup_stdout()
    parser = argparse.ArgumentParser(
        description=(
            "Проверить актуальный состав официальных корзин MOEX через MOEX ISS "
            "и собрать следующую очередь покрытия."
        )
    )
    parser.add_argument("--date", help="Дата состава в формате YYYY-MM-DD")
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
        "--json",
        action="store_true",
        help="Вывести результат в JSON",
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

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print_report(report)


if __name__ == "__main__":
    main()
