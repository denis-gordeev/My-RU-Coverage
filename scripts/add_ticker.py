"""
add_ticker.py — Генерация отчёта нового тикера с финансовыми данными и базовой структурой.

Создаёт новый .md файл в Pilot_Reports/{сектор}/ с:
- Заголовком с викилинком на название компании
- Метаданными (сектор, отрасль, рыночная кап., стоимость предприятия)
- Секциями-заглушками для обогащения
- Финансовыми таблицами из yfinance (годовые 3г + квартальные 4кв)

Использование:
  python scripts/add_ticker.py GAZP Газпром                         # Автоопределение сектора
  python scripts/add_ticker.py GAZP Газпром --сектор Энергетика      # Указать сектор

После генерации используйте update_enrichment.py для добавления описаний деятельности.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    find_ticker_files, ДИРЕКТОРИЯ_ОТЧЁТОВ, КОРЕНЬ_ПРОЕКТА,
    ЗАГОЛОВОК_СЕКЦИИ_ОПИСАНИЯ, ЗАГОЛОВОК_СЕКЦИИ_ЦЕПОЧКИ, ЗАГОЛОВОК_СЕКЦИИ_КЛИЕНТОВ,
    ЗАГОЛОВОК_СЕКЦИИ_ФИНАНСОВ, ЗАГОЛОВОК_СЕКЦИИ_ГОДОВЫХ, ЗАГОЛОВОК_СЕКЦИИ_КВАРТАЛЬНЫХ,
)

# Импорт загрузчика финансовых данных
from update_financials import fetch_financials, build_financial_section


def generate_report(ticker, name, sector=None, industry=None):
    """Генерирует полный файл отчёта для нового тикера."""
    fin_data = fetch_financials(ticker)

    if fin_data:
        if not sector:
            sector = fin_data.get("сектор", "Не определено")
        if not industry:
            industry = fin_data.get("отрасль", "Не определено")
        market_cap = fin_data.get("рыночная_капитализация") or "Н/Д"
        enterprise_value = fin_data.get("стоимость_предприятия") or "Н/Д"
        unit_label = fin_data.get("единица_измерения", "млн руб.")
        fin_section = build_financial_section(fin_data)
    else:
        if not sector:
            sector = "Не определено"
        if not industry:
            industry = "Не определено"
        market_cap = "Н/Д"
        enterprise_value = "Н/Д"
        unit_label = "млн руб."
        fin_section = (
            f"{ЗАГОЛОВОК_СЕКЦИИ_ФИНАНСОВ} (единицы: {unit_label}, маржа указана в %)\n"
            f"{ЗАГОЛОВОК_СЕКЦИИ_ГОДОВЫХ}\nНет доступных данных.\n\n"
            f"{ЗАГОЛОВОК_СЕКЦИИ_КВАРТАЛЬНЫХ}\nНет доступных данных.\n"
        )

    content = f"""# {ticker} - [[{name}]]

{ЗАГОЛОВОК_СЕКЦИИ_ОПИСАНИЯ}
**Сектор:** {sector}
**Отрасль:** {industry}
**Рыночная капитализация:** {market_cap} {unit_label}
**Стоимость предприятия (EV):** {enterprise_value} {unit_label}

*(Нужно обогащение: заполните описание через `update_enrichment.py`.)*

{ЗАГОЛОВОК_СЕКЦИИ_ЦЕПОЧКИ}
*(Нужно обогащение.)*

{ЗАГОЛОВОК_СЕКЦИИ_КЛИЕНТОВ}
*(Нужно обогащение.)*

{fin_section}"""

    return content, sector


def sanitize_folder_name(name):
    """Очищает название сектора для использования в имени папки."""
    # Заменяем символы, проблемные для путей Windows
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]

    if not args or args[0] in {"-h", "--help"}:
        print("Использование:")
        print("  python scripts/add_ticker.py <тикер> <название>")
        print("  python scripts/add_ticker.py <тикер> <название> --сектор <сектор>")
        return

    # Разбор аргументов
    ticker = args[0]
    name = args[1] if len(args) > 1 else "Без названия"

    sector = None
    if "--сектор" in args:
        idx = args.index("--сектор")
        sector = " ".join(args[idx + 1 :])

    # Проверяем, не существует ли уже тикер
    existing = find_ticker_files([ticker])
    if existing:
        print(f"Тикер {ticker} уже существует: {existing[ticker]}")
        print("Для обновления используйте update_financials.py или update_enrichment.py.")
        return

    print(f"Создаю карточку для {ticker} ({name})...")
    content, detected_sector = generate_report(ticker, name, sector)

    # Определяем папку вывода
    folder_name = sanitize_folder_name(sector or detected_sector)
    output_dir = os.path.join(ДИРЕКТОРИЯ_ОТЧЁТОВ, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    # Записываем файл
    filename = f"{ticker}_{name}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Создан файл: {filepath}")
    print(f"Сектор: {folder_name}")
    print("\nДальше: используйте update_enrichment.py, чтобы добавить описание деятельности, цепочку поставок и контрагентов.")


if __name__ == "__main__":
    main()
