"""
update_enrichment.py — Обновление контента обогащения (описание, цепочка поставок, клиенты)
в отчётах тикеров. Сохраняет финансовые таблицы.

Этот скрипт применяет данные обогащения из JSON-файла или встроенного словаря DATA
к файлам отчётов тикеров. Заменяет разделы бизнеса, цепочки поставок и контрагентов,
сохраняя метаданные и финансовый блок.

Использование:
  python scripts/update_enrichment.py --data enrichment.json             # Из JSON-файла
  python scripts/update_enrichment.py --data enrichment.json SBER        # Один тикер из JSON
  python scripts/update_enrichment.py --data enrichment.json --sector Энергетика

Формат JSON:
{
  "SBER": {
    "desc": "Русскоязычное описание с [[wikilinks]]...",
    "supply_chain": "**Верхний контур:**\\n- ...\\n**Ключевое звено:**\\n- ...\\n**Конечный спрос:**\\n- ...",
    "cust": "### Ключевые клиенты\\n- ...\\n\\n### Ключевые поставщики\\n- ..."
  }
}

При вызове через Claude /update-enrichment skill, Claude:
1. Исследует тикеры через веб-поиск
2. Записывает enrichment.json
3. Запускает этот скрипт
"""

import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    find_ticker_files, parse_scope_args, PROJECT_ROOT, normalize_wikilinks,
    BUSINESS_SECTION_TITLE, SUPPLY_CHAIN_SECTION_TITLE, CUSTOMERS_SECTION_TITLE,
    SECTION_HEADER_REGEX,
)


def apply_enrichment(filepath, ticker, data):
    """Применяет данные обогащения к одному файлу. Сохраняет метаданные и финансовые данные."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Добавляем блок метаданных, если отсутствует
    if not re.search(r"\*\*Сектор:\*\*", content) and not re.search(r"\*\*Рыночная капитализация:\*\*", content):
        sector = data.get("sector", "Н/Д")
        industry = data.get("industry", "Н/Д")
        meta = (
            f"**Сектор:** {sector}\n"
            f"**Отрасль:** {industry}\n"
            f"**Рыночная капитализация:** Н/Д млн руб.\n"
            f"**Стоимость предприятия (EV):** Н/Д млн руб.\n\n"
        )
        content = re.sub(SECTION_HEADER_REGEX["business"] + r"\n", BUSINESS_SECTION_TITLE + "\n" + meta, content, count=1)

    # Заменяем описание бизнеса (сохраняя блок метаданных выше)
    if "desc" in data:
        def repl_desc(m):
            return f"{m.group(1)}{data['desc']}\n"
        content = re.sub(
            r"((?:## Описание бизнеса)\n(?:.*?(?:Стоимость предприятия \(EV\)):.*?\n\n|))(.*?)(?=\n(?:## Положение в цепочке поставок))",
            repl_desc,
            content,
            flags=re.DOTALL,
        )

    # Заменяем секцию цепочки поставок
    if "supply_chain" in data:
        sc = data["supply_chain"] + "\n"
        content = re.sub(
            r"((?:## Положение в цепочке поставок)\n)(.*?)(?=\n(?:## Ключевые клиенты и поставщики))",
            rf"\g<1>{sc}",
            content,
            flags=re.DOTALL,
        )

    # Заменяем секцию клиентов/поставщиков
    if "cust" in data:
        ct = data["cust"] + "\n"
        content = re.sub(
            r"((?:## Ключевые клиенты и поставщики)\n)(.*?)(?=\n(?:## Финансовый обзор))",
            rf"\g<1>{ct}",
            content,
            flags=re.DOTALL,
        )

    content = re.sub(SECTION_HEADER_REGEX["business"], BUSINESS_SECTION_TITLE, content)
    content = re.sub(SECTION_HEADER_REGEX["supply_chain"], SUPPLY_CHAIN_SECTION_TITLE, content)
    content = re.sub(SECTION_HEADER_REGEX["customers"], CUSTOMERS_SECTION_TITLE, content)

    # Нормализуем викалинки: стандартизируем алиасы, схлопываем дубли
    content = normalize_wikilinks(content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    try:
        print(f"  {ticker}: обогащено ({os.path.basename(filepath)})")
    except UnicodeEncodeError:
        print(f"  {ticker}: обогащено")
    return True


def load_enrichment_data(json_path):
    """Загружает данные обогащения из JSON-файла."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = [a for a in sys.argv[1:]]

    # Извлекаем флаг --data
    json_path = None
    if "--data" in args:
        idx = args.index("--data")
        json_path = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if not json_path:
        print("Использование: python scripts/update_enrichment.py --data <json_file> [scope]")
        print("  Область: SBER | SBER GAZP | --sector Энергетика | без аргументов = все")
        return

    # Загружаем данные обогащения
    if not os.path.isabs(json_path):
        json_path = os.path.join(PROJECT_ROOT, json_path)
    enrichment_data = load_enrichment_data(json_path)
    print(f"Загружено записей по тикерам: {len(enrichment_data)} из {os.path.basename(json_path)}")

    # Разбираем область действия
    tickers, sector, desc = parse_scope_args(args)
    print(f"Область применения: {desc}\n")

    # Ищем подходящие файлы
    # Если указаны конкретные тикеры, пересекаем с данными обогащения
    available_tickers = list(enrichment_data.keys())
    if tickers:
        target_tickers = [t for t in tickers if t in enrichment_data]
    else:
        target_tickers = available_tickers

    files = find_ticker_files(target_tickers, sector)

    if not files:
        print("Подходящие файлы не найдены.")
        return

    enriched = skipped = 0
    for ticker in sorted(files.keys()):
        if ticker in enrichment_data:
            apply_enrichment(files[ticker], ticker, enrichment_data[ticker])
            enriched += 1
        else:
            skipped += 1

    print(f"\nГотово. Обогащено: {enriched} | Пропущено: {skipped}")


if __name__ == "__main__":
    main()
