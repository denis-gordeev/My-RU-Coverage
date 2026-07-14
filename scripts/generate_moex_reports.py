"""
generate_moex_reports.py — Генерация базовых MOEX-отчётов из официальной очереди ISS.

Формирует живую очередь из MOEX ISS и создаёт отсутствующие карточки через
русскоязычный процесс add_ticker.

Применение:
  python scripts/generate_moex_reports.py
  python scripts/generate_moex_reports.py --индекс MOEXBMI --лимит 5
  python scripts/generate_moex_reports.py DOMRF AKRN AFLT
  python scripts/generate_moex_reports.py --пробный-запуск --все-непокрытые
"""

import os
import sys
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from add_ticker import сгенерировать_отчёт, очистить_имя_папки
from moex_blue_chip_queue import КОДЫ_ИНДЕКСОВ_ПО_УМОЛЧАНИЮ, построить_отчёт
from utils import ДИРЕКТОРИЯ_ОТЧЁТОВ, найти_файлы_тикеров, настроить_вывод, создать_русский_парсер

ПЕРЕОПРЕДЕЛЕНИЯ_ОТЧЁТОВ = {
    "DOMRF": {
        "название": "ДОМ.РФ",
        "сектор": "Финансовые услуги",
        "отрасль": "Кредитные услуги",
    },
    "AKRN": {
        "название": "Акрон",
    },
    "AFLT": {
        "название": "Аэрофлот",
    },
    "CBOM": {
        "название": "Московский кредитный банк",
        "сектор": "Финансовые услуги",
        "отрасль": "Банки — региональные",
    },
    "BSPB": {
        "название": "Банк Санкт-Петербург",
        "сектор": "Финансовые услуги",
        "отрасль": "Банки — региональные",
    },
    "AFKS": {
        "название": "АФК Система",
    },
    "ENPG": {
        "название": "ЭН+ ГРУП",
    },
    "CNRU": {
        "название": "Циан",
    },
    "BANEP": {
        "название": "Башнефть ап",
    },
    "ASTR": {
        "название": "Астра",
    },
    "AQUA": {
        "название": "Инарктика",
    },
    "BELU": {
        "название": "НоваБев Групп",
    },
    "ETLN": {
        "название": "Эталон",
    },
    "EUTR": {
        "название": "ЕвроТранс",
    },
    "DATA": {
        "название": "Аренадата",
    },
    "APTK": {
        "название": "Аптеки 36 и 6",
    },
    "BAZA": {
        "название": "БАЗИС",
    },
    "ELFV": {
        "название": "ЭЛ5-Энерго",
    },
}

СУФФИКСЫ_КОРОТКОГО_ИМЕНИ = (" ао", " ап", "-ао", "-ап")


def нормализовать_название_компании(ticker, короткое_имя):
    override = ПЕРЕОПРЕДЕЛЕНИЯ_ОТЧЁТОВ.get(ticker, {})
    if override.get("название"):
        return override["название"]

    cleaned = (короткое_имя or ticker).strip()
    if cleaned[:1].lower() == "i" and len(cleaned) > 1 and cleaned[1].isalpha():
        cleaned = cleaned[1:]
    lowered = cleaned.lower()
    for suffix in СУФФИКСЫ_КОРОТКОГО_ИМЕНИ:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned.strip(" .") or ticker


def отобрать_элементы_очереди(отчёт, запрошенные_тикеры=None):
    queue = отчёт["следующая_очередь"]
    if not запрошенные_тикеры:
        return queue

    lookup = {item["тикер"]: item for item in queue}
    элементы = []
    for ticker in запрошенные_тикеры:
        item = lookup.get(ticker)
        if item is None:
            элементы.append(
                {
                    "тикер": ticker,
                    "название": ПЕРЕОПРЕДЕЛЕНИЯ_ОТЧЁТОВ.get(ticker, {}).get("название", ticker),
                }
            )
        else:
            элементы.append(item)
    return элементы


def построить_путь_вывода(ticker, название_компании, название_сектора):
    safe_sector = очистить_имя_папки(название_сектора)
    filename = f"{ticker}_{название_компании}.md"
    return os.path.join(ДИРЕКТОРИЯ_ОТЧЁТОВ, safe_sector, filename)


def создать_отчёты(элементы, limit=None, пробный_запуск=False):
    existing = найти_файлы_тикеров()
    создано = 0
    пропущено = 0

    for item in элементы:
        if limit is not None and создано >= limit:
            break

        ticker = item["тикер"]
        if ticker in existing:
            print(f"  {ticker}: пропуск (карточка уже существует)")
            пропущено += 1
            continue

        override = ПЕРЕОПРЕДЕЛЕНИЯ_ОТЧЁТОВ.get(ticker, {})
        название_компании = нормализовать_название_компании(ticker, item.get("название", ticker))
        sector = override.get("сектор")
        industry = override.get("отрасль")
        content, detected_sector = сгенерировать_отчёт(ticker, название_компании, sector, industry)
        target_sector = sector or detected_sector or "Не определено"
        output_path = построить_путь_вывода(ticker, название_компании, target_sector)

        if пробный_запуск:
            print(f"  {ticker}: черновик -> {output_path}")
            создано += 1
            continue

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        print(f"  {ticker}: создано -> {output_path}")
        создано += 1

    return создано, пропущено


def main():
    настроить_вывод()
    parser = создать_русский_парсер(
        description=(
            "Создать базовые MOEX-карточки по живой очереди из MOEX ISS без "
            "опоры на устаревший Excel."
        )
    )
    parser.add_argument(
        "тикеры",
        nargs="*",
        help="Явно указанные тикеры. Если не заданы, используется очередь непокрытых тикеров из MOEX ISS.",
    )
    parser.add_argument("--дата", help="Дата состава индекса в формате YYYY-MM-DD")
    parser.add_argument(
        "--индекс",
        dest="индексы",
        action="append",
        help=(
            "Код индекса MOEX ISS. Можно повторять несколько раз; по умолчанию "
            "используются MOEXBC и MOEXBMI."
        ),
    )
    parser.add_argument(
        "--лимит",
        type=int,
        default=5,
        help="Сколько новых карточек создать из начала очереди. По умолчанию 5.",
    )
    parser.add_argument(
        "--все-непокрытые",
        action="store_true",
        help="Игнорировать лимит --лимит и обработать всю очередь непокрытых тикеров.",
    )
    parser.add_argument(
        "--пробный-запуск",
        action="store_true",
        help="Показать, какие карточки будут созданы, без записи файлов.",
    )
    args = parser.parse_args()

    коды_индексов = args.индексы or КОДЫ_ИНДЕКСОВ_ПО_УМОЛЧАНИЮ
    try:
        report = построить_отчёт(коды_индексов, args.дата)
    except HTTPError as exc:
        print(f"Ошибка HTTP при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)
    except URLError as exc:
        print(f"Сетевой сбой при запросе MOEX ISS: {exc}", file=sys.stderr)
        sys.exit(1)

    элементы = отобрать_элементы_очереди(отчёт, [ticker.upper() for ticker in args.тикеры])
    if not элементы:
        print("Очередь уже покрыта: новых карточек для создания нет.")
        return

    limit = None if args.все_непокрытые or args.тикеры else max(args.лимит, 0)
    print(
        f"Генерирую базовые MOEX-карточки из очереди {', '.join(коды_индексов)} "
        f"на дату {report['дата_торгов']}..."
    )
    создано, пропущено = создать_отчёты(элементы, limit=limit, пробный_запуск=args.пробный_запуск)
    print(f"\nГотово. Создано: {создано} | Пропущено: {пропущено}")


if __name__ == "__main__":
    main()
