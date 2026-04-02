"""
discover.py — Обратный поиск компаний по ключевому слову или теме.

Если нужно понять, какие эмитенты связаны с темой вроде "импортозамещение",
"редкоземы", "СПГ" или "CPO", скрипт:

1. Ищет упоминания по всем релевантным карточкам эмитентов
2. При необходимости добавляет [[wikilinks]] для найденного термина
3. Показывает, какие компании и в каком контексте связаны с темой
4. По запросу пересобирает темы, граф и индекс викалинков

Примеры:
  python scripts/discover.py "импортозамещение"                            # искать по всем секторам
  python scripts/discover.py "СПГ" --apply                                 # проставить [[wikilinks]]
  python scripts/discover.py "CPO" --apply --rebuild                       # + пересобрать темы/граф/индекс
  python scripts/discover.py "редкоземы" --smart                           # автофильтр секторов
  python scripts/discover.py "CPO" --sector Semiconductors                 # ограничить одним сектором
  python scripts/discover.py "CPO" --sectors "Semiconductors,Electronic Components"

Фильтрация секторов:
  Технологические ключевые слова обычно пропускают банки, страхование,
  недвижимость, продукты питания, текстиль и прочие нерелевантные сектора.
  Используйте --smart для автофильтрации или --sector/--sectors вручную.
"""

import os
import re
import sys
import subprocess
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import REPORTS_DIR, PROJECT_ROOT, setup_stdout, TICKER_PATTERN, SECTION_HEADER_REGEX

# Группы секторов для умной фильтрации
TECH_SECTORS = {
    "Semiconductors", "Semiconductor Equipment & Materials",
    "Electronic Components", "Computer Hardware", "Communication Equipment",
    "Consumer Electronics", "Software (Application)", "Software (Infrastructure)",
    "Electronics & Computer Distribution", "Information Technology Services",
    "Scientific & Technical Instruments",
}

INDUSTRIAL_SECTORS = {
    "Specialty Industrial Machinery", "Industrial Distribution",
    "Metal Fabrication", "Electrical Equipment & Parts",
    "Pollution & Treatment Controls", "Conglomerates",
    "Engineering & Construction", "Building Products & Equipment",
    "Tools & Accessories", "Auto Parts", "Aerospace & Defense",
}

MATERIALS_SECTORS = {
    "Chemicals", "Specialty Chemicals", "Steel", "Aluminum",
    "Copper", "Other Industrial Metals & Mining",
}

ENERGY_SECTORS = {
    "Solar", "Utilities - Renewable", "Utilities - Regulated Electric",
    "Oil & Gas Equipment & Services",
}

CONSUMER_SECTORS = {
    "Footwear & Accessories", "Textile Manufacturing",
    "Household & Personal Products", "Packaging & Containers",
    "Furnishings, Fixtures & Appliances", "Leisure",
    "Restaurants", "Grocery Stores", "Specialty Retail",
}

FINANCE_SECTORS = {
    "Banks - Diversified", "Banks - Regional", "Insurance - Life",
    "Insurance - Property & Casualty", "Capital Markets",
    "Financial - Credit Services", "Financial Conglomerates",
}

REAL_ESTATE_SECTORS = {
    "Real Estate - Development", "Real Estate - Diversified",
    "REIT - Diversified",
}

# Карта профилей: тип темы -> какие группы секторов искать
SMART_PROFILES = {
    "tech": TECH_SECTORS | INDUSTRIAL_SECTORS | MATERIALS_SECTORS,
    "energy": TECH_SECTORS | INDUSTRIAL_SECTORS | ENERGY_SECTORS | MATERIALS_SECTORS,
    "consumer": CONSUMER_SECTORS | TECH_SECTORS,
    "all": None,  # None = search everything
}

# Подсказки для автоопределения профиля
TECH_KEYWORDS = [
    "半導體", "晶片", "IC", "AI", "伺服器", "封裝", "製程", "光電",
    "通訊", "5G", "衛星", "記憶體", "電池", "充電", "散熱", "矽",
    "雷射", "光纖", "感測", "量子", "ASIC", "GPU", "HBM", "PCB",
    "LED", "OLED", "EUV", "SiC", "GaN", "MEMS", "RF", "CPO",
    "полупровод", "чип", "микросхем", "сервер", "дата-центр", "ЦОД",
    "связь", "телеком", "спутник", "батаре", "заряд", "охлажден",
    "квант", "фотон", "оптик", "GPU", "ASIC", "CPO",
]

ENERGY_KEYWORDS = [
    "能源", "電力", "風電", "太陽能", "儲能", "氫能", "核", "碳",
    "綠電", "充電", "電網",
    "энерг", "электро", "ветер", "солнеч", "накопител",
    "водород", "атом", "углерод", "сеть", "нефт", "газ", "СПГ", "LNG",
]


def detect_profile(buzzword):
    """Автоопределение профиля секторов по содержанию запроса."""
    for kw in TECH_KEYWORDS:
        if kw in buzzword:
            return "tech"
    for kw in ENERGY_KEYWORDS:
        if kw in buzzword:
            return "energy"
    return "all"


def search_reports(buzzword, sectors_filter=None):
    """Ищет упоминания темы по карточкам эмитентов."""
    results = []

    for sector_dir in sorted(os.listdir(REPORTS_DIR)):
        sector_path = os.path.join(REPORTS_DIR, sector_dir)
        if not os.path.isdir(sector_path):
            continue

        # Ограничение по списку секторов
        if sectors_filter and sector_dir not in sectors_filter:
            continue

        for f in sorted(os.listdir(sector_path)):
            if not f.endswith(".md"):
                continue
            m = re.match(rf"^({TICKER_PATTERN})_(.+)\.md$", f, re.IGNORECASE)
            if not m:
                continue

            ticker, company = m.group(1), m.group(2)
            filepath = os.path.join(sector_path, f)

            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()

            financial_split = re.split(SECTION_HEADER_REGEX["financial"], content, maxsplit=1)
            text = financial_split[0]

            # Уже проставленные [[wikilinks]]
            linked_count = len(re.findall(r"\[\[" + re.escape(buzzword) + r"\]\]", text))

            # Обычные упоминания вне [[ ]]
            bare_pattern = r"(?<!\[\[)" + re.escape(buzzword) + r"(?!\]\])"
            bare_matches = list(re.finditer(bare_pattern, text))
            bare_count = len(bare_matches)

            if linked_count > 0 or bare_count > 0:
                # Короткие контекстные сниппеты
                contexts = []
                for match in bare_matches[:3]:
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    snippet = text[start:end].replace("\n", " ").strip()
                    contexts.append(f"...{snippet}...")

                # Примерно определяем роль по разделу
                role = "mentioned"
                for section_name, role_name in [
                    (SECTION_HEADER_REGEX["business"], "core_business"),
                    (SECTION_HEADER_REGEX["supply_chain"], "supply_chain"),
                    (SECTION_HEADER_REGEX["customers"], "customer_supplier"),
                ]:
                    section_match = re.search(
                        rf"{section_name}\n(.*?)(?=\n## |\Z)", text, re.DOTALL
                    )
                    if section_match and buzzword in section_match.group(1):
                        role = role_name
                        break

                results.append({
                    "ticker": ticker,
                    "company": company,
                    "sector": sector_dir,
                    "filepath": filepath,
                    "linked": linked_count,
                    "bare": bare_count,
                    "role": role,
                    "contexts": contexts,
                })

    return results


def apply_wikilinks(results, buzzword):
    """Добавляет [[wikilinks]] там, где термин найден без разметки."""
    applied = 0
    for r in results:
        if r["bare"] == 0:
            continue

        with open(r["filepath"], "r", encoding="utf-8") as f:
            content = f.read()

        # Финансовый раздел не трогаем
        financial_match = re.search(SECTION_HEADER_REGEX["financial"], content)
        if not financial_match:
            continue

        text = content[: financial_match.start()]
        financial_part = content[financial_match.start() :]
        # Не даём задвоить существующие [[wikilinks]]
        pattern = (
            r"(?<!\[\[)"
            + re.escape(buzzword)
            + r"(?!\]\])(?![A-Za-z\u0400-\u04FF\u4e00-\u9fff])"
        )
        new_text, count = re.subn(pattern, f"[[{buzzword}]]", text)

        if count > 0:
            content = new_text + financial_part
            with open(r["filepath"], "w", encoding="utf-8") as f:
                f.write(content)
            applied += count

    return applied


def print_report(results, buzzword):
    """Печатает сводку по найденным совпадениям."""
    if not results:
        print(f"\nНе найдено компаний, где упоминается «{buzzword}».")
        return

    # Группировка по типу связи
    by_role = defaultdict(list)
    for r in results:
        by_role[r["role"]].append(r)

    print(f"\n{'=' * 60}")
    print(f"Компании, связанные с темой «{buzzword}»: {len(results)}")
    print(f"{'=' * 60}")

    role_labels = {
        "core_business": "Связь через основной бизнес",
        "supply_chain": "Связь через цепочку поставок",
        "customer_supplier": "Связь через клиентов/поставщиков",
        "mentioned": "Прочие упоминания",
    }

    for role, label in role_labels.items():
        entries = by_role.get(role, [])
        if not entries:
            continue
        print(f"\n### {label} ({len(entries)})")
        for r in sorted(entries, key=lambda x: x["ticker"]):
            link_status = "✓" if r["linked"] > 0 else "○"
            bare_note = f" (+{r['bare']} без [[wikilink]])" if r["bare"] > 0 else ""
            print(f"  {link_status} {r['ticker']} {r['company']} ({r['sector']}){bare_note}")
            for ctx in r["contexts"][:1]:
                print(f"    -> {ctx}")


def main():
    setup_stdout()

    if len(sys.argv) < 2:
        print("Использование:")
        print('  python scripts/discover.py "импортозамещение"        # искать по всем секторам')
        print('  python scripts/discover.py "СПГ" --smart              # автофильтр секторов')
        print('  python scripts/discover.py "CPO" --sector Semiconductors')
        print('  python scripts/discover.py "редкоземы" --apply        # проставить [[wikilinks]]')
        print('  python scripts/discover.py "СПГ" --apply --rebuild    # + пересобрать темы/граф')
        sys.exit(1)

    buzzword = sys.argv[1]
    args = sys.argv[2:]

    # Разбор флагов
    do_apply = "--apply" in args
    do_rebuild = "--rebuild" in args
    smart = "--smart" in args

    # Разбор фильтра по секторам
    sectors_filter = None
    if "--sector" in args:
        idx = args.index("--sector")
        if idx + 1 < len(args):
            sectors_filter = {args[idx + 1]}
    elif "--sectors" in args:
        idx = args.index("--sectors")
        if idx + 1 < len(args):
            sectors_filter = set(s.strip() for s in args[idx + 1].split(","))
    elif smart:
        profile = detect_profile(buzzword)
        sectors_filter = SMART_PROFILES[profile]
        if sectors_filter:
            print(
                f"Умный режим: профиль '{profile}', поиск по {len(sectors_filter)} секторам"
            )
            print("  Внимание: возможны пропуски межсекторальных совпадений. Для полного охвата запускайте без --smart.")

    # Поиск
    print(f"Ищу «{buzzword}»...")
    results = search_reports(buzzword, sectors_filter)

    # Отчёт
    print_report(results, buzzword)

    # Применение [[wikilinks]]
    if do_apply and results:
        bare_count = sum(r["bare"] for r in results)
        if bare_count > 0:
            applied = apply_wikilinks(results, buzzword)
            print(f"\nДобавлено {applied} вхождений [[{buzzword}]].")
        else:
            print(f"\nВсе упоминания уже размечены как [[{buzzword}]].")

    # Пересборка производных артефактов
    if do_rebuild:
        print("\nПересобираю тематические страницы...")
        subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "build_themes.py")],
            cwd=PROJECT_ROOT,
        )
        print("Пересобираю сетевой граф...")
        subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "build_network.py")],
            cwd=PROJECT_ROOT,
        )
        print("Пересобираю индекс викалинков...")
        subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "build_wikilink_index.py")],
            cwd=PROJECT_ROOT,
        )

    # Итог
    linked = sum(1 for r in results if r["linked"] > 0)
    unlinked = sum(1 for r in results if r["bare"] > 0 and r["linked"] == 0)
    print(f"\nИтог: {len(results)} компаний упоминают «{buzzword}»")
    print(f"  Уже размечено: {linked} | Только голые упоминания: {unlinked}")


if __name__ == "__main__":
    main()
