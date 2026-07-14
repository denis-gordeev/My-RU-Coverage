"""
moex_blue_chip_queue.py — Проверка официальных корзин MOEX через ISS.

Показывает актуальный состав одного или нескольких индексов MOEX и отмечает,
для каких тикеров в `Pilot_Reports/` ещё нет российских карточек покрытия.
По умолчанию объединяет полностью покрытую корзину крупнейших акций (`MOEXBC`)
и более широкий ликвидный индекс (`MOEXBMI`), чтобы сформировать следующую
очередь для исследования.

Использование:
  python scripts/moex_blue_chip_queue.py
  python scripts/moex_blue_chip_queue.py --индекс MOEXBC
  python scripts/moex_blue_chip_queue.py --индекс MOEXBMI --дата 2026-04-03
  python scripts/moex_blue_chip_queue.py --json
"""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import найти_файлы_тикеров, настроить_вывод, создать_русский_парсер

АДРЕС_ISS = "https://iss.moex.com/iss/statistics/engines/stock/markets/index/analytics/MOEXBC/constituents.json"
КОДЫ_ИНДЕКСОВ_ПО_УМОЛЧАНИЮ = ["MOEXBC", "MOEXBMI"]
МЕТКИ_ИНДЕКСОВ = {
    "MOEXBC": "Индекс крупнейших акций",
    "MOEXBMI": "Индекс широкого рынка",
    "MOEXOG": "Нефть и газ",
    "MOEXTL": "Телекоммуникации",
    "MOEXFN": "Финансы",
    "MOEXMM": "Металлы и добыча",
    "MOEXEU": "Электроэнергетика",
    "MOEXCN": "Потребительский сектор",
    "MOEXCH": "Химия и нефтехимия",
}


def загрузить_состав(код_индекса, дата_торгов=None):
    params = {"iss.meta": "off"}
    if дата_торгов:
        params["date"] = дата_торгов

    iss_url = АДРЕС_ISS.replace("/MOEXBC/", f"/{код_индекса}/")
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


def _перевести_элемент(item):
    return {
        "тикер": item.get("ticker"),
        "название": item.get("shortnames"),
        "вес": item.get("weight"),
        "ранг": item.get("rank"),
        "дата_торгов": item.get("tradedate"),
    }


def построить_отчёт_по_индексу(код_индекса, items):
    покрытые = set(найти_файлы_тикеров().keys())
    отсутствующие = [item for item in items if item["ticker"] not in покрытые]
    report = {
        "код_индекса": код_индекса,
        "название_индекса": МЕТКИ_ИНДЕКСОВ.get(код_индекса, код_индекса),
        "дата_торгов": items[0]["tradedate"] if items else None,
        "количество": len(items),
        "покрыто": len(items) - len(отсутствующие),
        "отсутствует": len(отсутствующие),
        "состав": [_перевести_элемент(i) for i in items],
        "отсутствующие": [_перевести_элемент(i) for i in отсутствующие],
    }
    return report


def построить_отчёт(коды_индексов, дата_торгов=None):
    отчёты_по_индексам = []
    агрегированные_отсутствующие = {}
    даты_торгов = []

    for код_индекса in коды_индексов:
        items = загрузить_состав(код_индекса, дата_торгов)
        index_report = построить_отчёт_по_индексу(код_индекса, items)
        отчёты_по_индексам.append(index_report)
        if index_report["дата_торгов"]:
            даты_торгов.append(index_report["дата_торгов"])

        for item in index_report["отсутствующие"]:
            ticker = item["тикер"]
            existing = агрегированные_отсутствующие.get(ticker)
            if existing is None:
                агрегированные_отсутствующие[ticker] = {
                    "тикер": ticker,
                    "название": item["название"],
                    "индексы": [код_индекса],
                    "лучший_ранг": item["ранг"],
                    "максимальный_вес": item["вес"],
                }
                continue

            existing["индексы"].append(код_индекса)
            existing["лучший_ранг"] = min(existing["лучший_ранг"], item["ранг"])
            existing["максимальный_вес"] = max(existing["максимальный_вес"], item["вес"])

    next_queue = sorted(
        агрегированные_отсутствующие.values(),
        key=lambda item: (item["лучший_ранг"], -item["максимальный_вес"], item["тикер"]),
    )

    return {
        "запрошенные_индексы": коды_индексов,
        "дата_торгов": max(даты_торгов) if даты_торгов else None,
        "отчёты": отчёты_по_индексам,
        "следующая_очередь": next_queue,
    }


def вывести_отчёт(отчёт):
    for index_report in отчёт["отчёты"]:
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
            print("Без российской карточки:")
            for item in index_report["отсутствующие"]:
                print(
                    f"  - #{item['ранг']:<2} {item['тикер']} ({item['название']}), "
                    f"вес {item['вес']:.2f}%"
                )
        else:
            print("Все текущие бумаги этого индекса уже покрыты российскими карточками.")
        print("")

    if отчёт["следующая_очередь"]:
        print("Следующая агрегированная очередь покрытия:")
        for item in report["следующая_очередь"]:
            indices = ", ".join(item["индексы"])
            print(
                f"  - #{item['лучший_ранг']:<2} {item['тикер']} ({item['название']}), "
                f"индексы: {indices}, макс. вес {item['максимальный_вес']:.2f}%"
            )
    else:
        print("Объединённая очередь индексов уже полностью покрыта российскими карточками.")


def main():
    настроить_вывод()
    parser = создать_русский_парсер(
        description=(
            "Проверить актуальный состав официальных корзин MOEX через MOEX ISS "
            "и собрать следующую очередь покрытия."
        )
    )
    parser.add_argument("--дата", help="Дата состава в формате YYYY-MM-DD")
    parser.add_argument(
        "--индекс",
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
    коды_индексов = args.indices or КОДЫ_ИНДЕКСОВ_ПО_УМОЛЧАНИЮ

    try:
        report = построить_отчёт(коды_индексов, args.дата)
    except HTTPError as exc:
        print(f"Ошибка HTTP при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)
    except URLError as exc:
        print(f"Сетевой сбой при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    вывести_отчёт(report)


if __name__ == "__main__":
    main()
