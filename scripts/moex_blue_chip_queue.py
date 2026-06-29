"""
moex_blue_chip_queue.py — Проверка официальных корзин MOEX через ISS.

Показывает актуальный состав одного или нескольких индексов MOEX и отмечает,
для каких тикеров в `Pilot_Reports/` ещё нет локальных карточек покрытия.
По умолчанию объединяет полностью покрытую корзину голубых фишек (`MOEXBC`)
и более широкий ликвидный индекс (`MOEXBMI`), чтобы сформировать следующую
очередь для исследования.

Использование:
  python scripts/moex_blue_chip_queue.py
  python scripts/moex_blue_chip_queue.py --index MOEXBC
  python scripts/moex_blue_chip_queue.py --index MOEXBMI --date 2026-04-03
  python scripts/moex_blue_chip_queue.py --json
"""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import find_ticker_files, setup_stdout, make_ru_parser

ISS_URL = "https://iss.moex.com/iss/statistics/engines/stock/markets/index/analytics/MOEXBC/constituents.json"
DEFAULT_INDEX_CODES = ["MOEXBC", "MOEXBMI"]
INDEX_LABELS = {
    "MOEXBC": "Индекс голубых фишек",
    "MOEXBMI": "Индекс широкого рынка",
    "MOEXOG": "Нефть и газ",
    "MOEXTL": "Телекоммуникации",
    "MOEXFN": "Финансы",
    "MOEXMM": "Металлы и добыча",
    "MOEXEU": "Электроэнергетика",
    "MOEXCN": "Потребительский сектор",
    "MOEXCH": "Химия и нефтехимия",
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


def _translate_item(item):
    return {
        "тикер": item.get("ticker"),
        "название": item.get("shortnames"),
        "вес": item.get("weight"),
        "ранг": item.get("rank"),
        "дата_торгов": item.get("tradedate"),
    }


def build_index_report(index_code, items):
    covered = set(find_ticker_files().keys())
    missing = [item for item in items if item["ticker"] not in covered]
    report = {
        "код_индекса": index_code,
        "название_индекса": INDEX_LABELS.get(index_code, index_code),
        "дата_торгов": items[0]["tradedate"] if items else None,
        "количество": len(items),
        "покрыто": len(items) - len(missing),
        "отсутствует": len(missing),
        "состав": [_translate_item(i) for i in items],
        "отсутствующие": [_translate_item(i) for i in missing],
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
        if index_report["дата_торгов"]:
            tradedates.append(index_report["дата_торгов"])

        for item in index_report["отсутствующие"]:
            ticker = item["тикер"]
            existing = aggregated_missing.get(ticker)
            if existing is None:
                aggregated_missing[ticker] = {
                    "тикер": ticker,
                    "название": item["название"],
                    "индексы": [index_code],
                    "лучший_ранг": item["ранг"],
                    "максимальный_вес": item["вес"],
                }
                continue

            existing["индексы"].append(index_code)
            existing["лучший_ранг"] = min(existing["лучший_ранг"], item["ранг"])
            existing["максимальный_вес"] = max(existing["максимальный_вес"], item["вес"])

    next_queue = sorted(
        aggregated_missing.values(),
        key=lambda item: (item["лучший_ранг"], -item["максимальный_вес"], item["тикер"]),
    )

    return {
        "запрошенные_индексы": index_codes,
        "дата_торгов": max(tradedates) if tradedates else None,
        "отчёты": index_reports,
        "следующая_очередь": next_queue,
    }


def print_report(report):
    for index_report in report["отчёты"]:
        print(
            f"{index_report['код_индекса']} ({index_report['название_индекса']}) на "
            f"{index_report['дата_торгов']}: {index_report['количество']} бумаг | "
            f"покрыто: {index_report['покрыто']} | отсутствует: {index_report['отсутствует']}"
        )
        print("")
        print("Текущий состав:")
        for item in index_report["состав"]:
            print(
                f"  #{item['ранг']:<2} {item['тикер']:<6} {item['название']:<20} "
                f"{item['вес']:>5.2f}%"
            )

        print("")
        if index_report["отсутствующие"]:
            print("Без локальной карточки:")
            for item in index_report["отсутствующие"]:
                print(
                    f"  - #{item['ранг']:<2} {item['тикер']} ({item['название']}), "
                    f"вес {item['вес']:.2f}%"
                )
        else:
            print("Все текущие бумаги этого индекса уже покрыты локальными карточками.")
        print("")

    if report["следующая_очередь"]:
        print("Следующая агрегированная очередь покрытия:")
        for item in report["следующая_очередь"]:
            indices = ", ".join(item["индексы"])
            print(
                f"  - #{item['лучший_ранг']:<2} {item['тикер']} ({item['название']}), "
                f"индексы: {indices}, макс. вес {item['максимальный_вес']:.2f}%"
            )
    else:
        print("Объединённая очередь индексов уже полностью покрыта локальными карточками.")


def main():
    setup_stdout()
    parser = make_ru_parser(
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
