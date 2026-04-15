"""
build_themes.py — Генерация тематических инвестиционных экранов из графа викилинков.

Сканирует все отчёты тикеров на викилинки, группирует компании по темам (технология,
материал, применение) и генерирует markdown-страницы с полной цепочкой создания
для каждой темы.

Использование:
  python scripts/build_themes.py              # Пересобрать все темы
  python scripts/build_themes.py --list       # Список доступных тем
  python scripts/build_themes.py "CoWoS"      # Пересобрать одну тему

Вывод: папка themes/ с одним .md на тему.
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import TICKER_PATTERN, extract_wikilinks

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "Pilot_Reports")
THEMES_DIR = os.path.join(os.path.dirname(__file__), "..", "themes")

RU_THEME_TAGS = [
    "банки",
    "финтех",
    "нефтегаз",
    "нефтепереработка",
    "природный газ",
    "электроэнергетика",
    "телеком",
    "продуктовый ритейл",
    "доставка",
    "электронная коммерция",
    "золото",
    "сталь",
    "алмазы",
    "цветные металлы",
    "экосистемы",
    "интернет-платформы",
    "маркетплейсы",
    "биржевая инфраструктура",
    "финансовый рынок",
    "удобрения",
    "агрохимия",
    "строительство",
    "логистика",
    "онлайн-реклама",
    "недвижимость",
    "импортозамещение",
    "кибербезопасность",
    "автомобилестроение",
    "АЗС",
    "конгломерат",
    "программное обеспечение",
]

RU_PRIORITY_QUEUE = ["DOMRF", "AKRN", "AFLT", "CBOM", "BSPB"]

# Curated themes with supply chain role hints
# Format: theme_wikilink -> { display_name, description, related_tags }
THEME_DEFINITIONS = {
    # === Russia / CIS market themes ===
    "банки": {
        "name": "Банковский сектор России",
        "desc": "Крупнейшие банки и финансовые платформы российского рынка: кредитование, платежи, транзакционный бизнес и экосистемные сервисы",
        "related": ["финтех", "экосистемы"],
    },
    "финтех": {
        "name": "Финтех и платёжные сервисы",
        "desc": "Цифровые платежи, банковские приложения, кредитные сервисы и смежная инфраструктура",
        "related": ["банки", "экосистемы", "телеком"],
    },
    "нефтегаз": {
        "name": "Нефтегазовый сектор",
        "desc": "Добыча, транспортировка, переработка и экспорт нефти и природного газа в российском контексте",
        "related": ["нефтепереработка", "природный газ", "СПГ"],
    },
    "нефтепереработка": {
        "name": "Нефтепереработка и топливный сбыт",
        "desc": "Переработка нефти, выпуск моторных топлив, экспорт нефтепродуктов и сбыт через внутренние каналы реализации",
        "related": ["нефтегаз", "АЗС", "трубная промышленность"],
    },
    "природный газ": {
        "name": "Природный газ",
        "desc": "Добыча газа, транспортная инфраструктура, экспортные маршруты и внутренний спрос",
        "related": ["нефтегаз", "СПГ"],
    },
    "телеком": {
        "name": "Телеком и цифровая инфраструктура",
        "desc": "Мобильная связь, фиксированный ШПД, корпоративные ИКТ-сервисы и цифровые экосистемы",
        "related": ["финтех", "экосистемы"],
    },
    "продуктовый ритейл": {
        "name": "Продуктовый ритейл",
        "desc": "Сети магазинов повседневного спроса, логистика FMCG и омниканальные форматы продаж",
        "related": ["доставка", "электронная коммерция", "e-grocery", "экосистемы"],
    },
    "доставка": {
        "name": "Доставка и last-mile сервисы",
        "desc": "Курьерская логистика, доставка до дома и сервисные модели, ускоряющие оборот интернет-платформ и ритейла",
        "related": ["электронная коммерция", "маркетплейсы", "продуктовый ритейл"],
    },
    "электронная коммерция": {
        "name": "Электронная коммерция",
        "desc": "Российские сервисы онлайн-заказа, цифровые витрины, merchant-tools и платёжно-логистическая инфраструктура вокруг e-commerce",
        "related": ["маркетплейсы", "доставка", "интернет-платформы", "финтех"],
    },
    "цветные металлы": {
        "name": "Цветные металлы",
        "desc": "Добыча и переработка никеля, меди, палладия, платины и других цветных металлов",
        "related": ["электромобили", "аккумуляторы"],
    },
    "экосистемы": {
        "name": "Экосистемные платформы",
        "desc": "Компании, монетизирующие базовый бизнес через финтех, подписки, ИТ-сервисы и смежные цифровые продукты",
        "related": ["финтех", "телеком", "банки"],
    },
    "интернет-платформы": {
        "name": "Интернет-платформы и цифровые сервисы",
        "desc": "Российские платформы с масштабным пользовательским трафиком, рекламой, подписками, сервисными и облачными вертикалями",
        "related": ["экосистемы", "маркетплейсы", "финтех"],
    },
    "маркетплейсы": {
        "name": "Маркетплейсы и e-commerce",
        "desc": "Площадки, связывающие продавцов и покупателей через ассортимент, рекламу, логистику и платёжные сервисы",
        "related": ["интернет-платформы", "экосистемы", "финтех"],
    },
    "биржевая инфраструктура": {
        "name": "Биржевая инфраструктура",
        "desc": "Площадки, клиринг, депозитарные и пост-трейдинговые сервисы, обеспечивающие функционирование локального рынка капитала",
        "related": ["финансовый рынок", "финтех", "банки"],
    },
    "финансовый рынок": {
        "name": "Российский финансовый рынок",
        "desc": "Биржевая торговля, брокерская дистрибуция, денежный рынок и инструменты фондирования внутри российского контура",
        "related": ["биржевая инфраструктура", "банки", "финтех"],
    },
    "удобрения": {
        "name": "Удобрения и агрохимия",
        "desc": "Производители минеральных удобрений, фосфорной и азотной химии, завязанные на аграрный цикл и экспорт",
        "related": ["агрохимия", "природный газ"],
    },
    "агрохимия": {
        "name": "Агрохимия",
        "desc": "Химические продукты для сельского хозяйства: удобрения, сырьё, компоненты и связанная логистика",
        "related": ["удобрения", "природный газ"],
    },
    "золото": {
        "name": "Золото и золотодобыча",
        "desc": "Добыча золота, разработка месторождений, аффинаж и каналы реализации металла в российском контуре",
        "related": ["драгоценные металлы", "цветные металлы"],
    },
    "сталь": {
        "name": "Сталь и чёрная металлургия",
        "desc": "Производство стали, проката и металлопродукции с привязкой к внутреннему промышленному и строительному спросу",
        "related": ["строительство", "машиностроение", "трубная промышленность"],
    },
    "алмазы": {
        "name": "Алмазы и алмазодобыча",
        "desc": "Добыча алмазного сырья, сортировка, экспорт и связь с ювелирным рынком",
        "related": ["ювелирный рынок", "драгоценные металлы"],
    },
    "электроэнергетика": {
        "name": "Электроэнергетика России",
        "desc": "Генерация, сбыт, энерготрейдинг и инфраструктура оптового рынка электроэнергии в российском контуре",
        "related": ["природный газ", "финансовый рынок"],
    },
    "строительство": {
        "name": "Строительство и девелопмент",
        "desc": "Жилое и коммерческое строительство, строительные материалы, девелоперские проекты и связанная инфраструктура",
        "related": ["недвижимость", "сталь", "логистика"],
    },
    "логистика": {
        "name": "Логистика и грузоперевозки",
        "desc": "Транспортная инфраструктура, грузовые и пассажирские перевозки, портовая и железнодорожная логистика",
        "related": ["строительство", "доставка", "электронная коммерция"],
    },
    "онлайн-реклама": {
        "name": "Онлайн-реклама и digital-маркетинг",
        "desc": "Цифровая реклама, программатик, поисковая и контекстная реклама в российском интернет-пространстве",
        "related": ["интернет-платформы", "электронная коммерция", "экосистемы"],
    },
    "недвижимость": {
        "name": "Недвижимость и проптех",
        "desc": "Рынок жилой и коммерческой недвижимости, онлайн-платформы объявлений, девелопмент и управление активами",
        "related": ["строительство", "биржевая инфраструктура"],
    },
    "импортозамещение": {
        "name": "Импортозамещение и технологический суверенитет",
        "desc": "Российские ИТ-решения, производственные и технологические замены зарубежных продуктов и оборудования",
        "related": ["кибербезопасность", "банки", "электроэнергетика"],
    },
    "кибербезопасность": {
        "name": "Кибербезопасность и защита информации",
        "desc": "Российские решения по защите данных, информационной безопасности и суверенным ИТ-стекам",
        "related": ["импортозамещение", "телеком", "банки"],
    },
    "автомобилестроение": {
        "name": "Автомобилестроение России",
        "desc": "Российское автомобилестроение: производство легковых и грузовых автомобилей, автокомпоненты и сборка",
        "related": ["сталь", "цветные металлы", "логистика"],
    },
    "АЗС": {
        "name": "АЗС и топливный ритейл",
        "desc": "Автозаправочные станции, розничный сбыт моторного топлива и сопутствующие сервисы на трассах",
        "related": ["нефтепереработка", "нефтегаз", "логистика"],
    },
    "конгломерат": {
        "name": "Многопрофильные конгломераты",
        "desc": "Российские многопрофильные холдинги, объединяющие активы в различных отраслях и секторах экономики",
        "related": ["экосистемы", "финансовый рынок", "телеком"],
    },
    "программное обеспечение": {
        "name": "Программное обеспечение и ИТ-решения",
        "desc": "Российские разработчики ОС, СУБД, офисных и корпоративных решений, ориентированные на импортозамещение",
        "related": ["импортозамещение", "кибербезопасность", "интернет-платформы"],
    },
}


def ru_plural(value, form1, form2, form5):
    value = abs(value) % 100
    if 11 <= value <= 19:
        return form5
    last = value % 10
    if last == 1:
        return form1
    if 2 <= last <= 4:
        return form2
    return form5


def scan_wikilinks():
    """Scan all reports, return {wikilink: [(ticker, company, sector, context)]}."""
    wl_map = defaultdict(list)

    for sector_dir in os.listdir(REPORTS_DIR):
        sector_path = os.path.join(REPORTS_DIR, sector_dir)
        if not os.path.isdir(sector_path):
            continue
        for f in os.listdir(sector_path):
            if not f.endswith(".md"):
                continue
            m = re.match(rf"^({TICKER_PATTERN})_(.+)\.md$", f, re.IGNORECASE)
            if not m:
                continue
            ticker, company = m.group(1), m.group(2)
            filepath = os.path.join(sector_path, f)
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()

            # Split content into sections for context
            sections = {
                "desc": "",
                "supply_chain": "",
                "customers": "",
            }
            parts = re.split(r"## ", content)
            for part in parts:
                if re.match(r"^(?:Описание бизнеса|業務簡介)", part):
                    sections["desc"] = part
                elif re.match(r"^(?:Положение в цепочке поставок|供應鏈位置)", part):
                    sections["supply_chain"] = part
                elif re.match(r"^(?:Ключевые клиенты и поставщики|主要客戶及供應商)", part):
                    sections["customers"] = part

            # Find all wikilinks in non-financial sections
            text = sections["desc"] + sections["supply_chain"] + sections["customers"]
            for wl in set(extract_wikilinks(text)):
                # Determine role from context
                role = "related"
                if wl in sections["supply_chain"]:
                    context = sections["supply_chain"].split(wl)[0][-100:].lower()
                    if "上游" in context or "верх" in context:
                        role = "upstream"
                    elif "下游" in context or "ниж" in context:
                        role = "downstream"
                    elif "中游" in context or "средн" in context:
                        role = "midstream"

                wl_map[wl].append(
                    {
                        "ticker": ticker,
                        "company": company,
                        "sector": sector_dir,
                        "role": role,
                    }
                )

    return wl_map


def build_theme_page(theme_tag, theme_def, wl_map):
    """Строит страницу темы в формате markdown."""
    entries = wl_map.get(theme_tag, [])
    if not entries:
        return None

    lines = []
    lines.append(f"# {theme_def['name']}")
    lines.append("")
    lines.append(f"> {theme_def['desc']}")
    lines.append("")
    lines.append("**Контур:** активная российская тема | [Ко всем темам](README.md)")
    lines.append("")
    entry_count = len(entries)
    lines.append(f"**Количество компаний:** {entry_count} {ru_plural(entry_count, 'компания', 'компании', 'компаний')}")
    lines.append("")

    # Related themes
    related = theme_def.get("related", [])
    related_with_counts = []
    for r in related:
        count = len(wl_map.get(r, []))
        if count > 0:
            related_with_counts.append(f"[[{r}]] ({count})")
    if related_with_counts:
        lines.append(f"**Связанные темы:** {' | '.join(related_with_counts)}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Group by role
    upstream = [e for e in entries if e["role"] == "upstream"]
    midstream = [e for e in entries if e["role"] == "midstream"]
    downstream = [e for e in entries if e["role"] == "downstream"]
    other = [e for e in entries if e["role"] == "related"]

    def format_entries(entries):
        # Group by sector
        by_sector = defaultdict(list)
        for e in entries:
            by_sector[e["sector"]].append(e)
        result = []
        for sector in sorted(by_sector.keys()):
            items = sorted(by_sector[sector], key=lambda x: x["ticker"])
            for item in items:
                result.append(
                    f"- **{item['ticker']} {item['company']}** ({sector})"
                )
        return result

    if upstream:
        lines.append(f"## Верхний контур ({len(upstream)} {ru_plural(len(upstream), 'компания', 'компании', 'компаний')})")
        lines.append("")
        lines.extend(format_entries(upstream))
        lines.append("")

    if midstream:
        lines.append(f"## Ключевое звено ({len(midstream)} {ru_plural(len(midstream), 'компания', 'компании', 'компаний')})")
        lines.append("")
        lines.extend(format_entries(midstream))
        lines.append("")

    if downstream:
        lines.append(f"## Конечный спрос ({len(downstream)} {ru_plural(len(downstream), 'компания', 'компании', 'компаний')})")
        lines.append("")
        lines.extend(format_entries(downstream))
        lines.append("")

    if other:
        lines.append(f"## Связанные компании ({len(other)} {ru_plural(len(other), 'компания', 'компании', 'компаний')})")
        lines.append("")
        lines.extend(format_entries(other))
        lines.append("")

    return "\n".join(lines)


def build_index(themes_built):
    """Build themes/README.md index."""
    lines = []
    ru_built = sum(1 for tag in RU_THEME_TAGS if tag in themes_built)
    ru_total_companies = sum(themes_built[tag] for tag in RU_THEME_TAGS if tag in themes_built)

    lines.append("# Тематические подборки")
    lines.append("")
    lines.append("> Автогенерируемые карты цепочек стоимости и смежных компаний.")
    lines.append("> Навигация собрана с российским приоритетом: только российские темы.")
    lines.append("> Пересборка: `python scripts/build_themes.py`")
    lines.append("")
    lines.append(f"> Тем в индексе: {ru_built}.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Фокус текущего покрытия")
    lines.append("")
    lines.append(
        f"- Российский контур сейчас охватывает {ru_built} {ru_plural(ru_built, 'тему', 'темы', 'тем')} "
        f"и {ru_total_companies} тематических вхождений компаний."
    )
    lines.append(f"- Следующая автоматическая очередь `MOEXBMI`: {', '.join(f'`{ticker}`' for ticker in RU_PRIORITY_QUEUE)}.")
    lines.append("")

    lines.append("## Российский рынок")
    lines.append("")
    for tag in RU_THEME_TAGS:
        if tag in themes_built:
            count = themes_built[tag]
            safe_name = tag.replace(" ", "_").replace("/", "_")
            lines.append(f"- [{tag}]({safe_name}.md) — {count} {ru_plural(count, 'компания', 'компании', 'компаний')}")
    lines.append("")

    return "\n".join(lines)


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    os.makedirs(THEMES_DIR, exist_ok=True)

    args = sys.argv[1:]

    if "--list" in args:
        for tag, defn in sorted(THEME_DEFINITIONS.items()):
            print(f"  {tag}: {defn['name']}")
        return

    print("Сканирую викалинки по всем отчётам...")
    wl_map = scan_wikilinks()
    print(f"Найдено уникальных викалинков: {len(wl_map)}.\n")

    # Filter to requested theme or build all
    if args and args[0] != "--list":
        themes_to_build = {args[0]: THEME_DEFINITIONS.get(args[0])}
        if not themes_to_build[args[0]]:
            print(f"Тема '{args[0]}' отсутствует в THEME_DEFINITIONS. Используйте --list для списка доступных тем.")
            return
    else:
        themes_to_build = THEME_DEFINITIONS

    themes_built = {}
    for tag, defn in themes_to_build.items():
        page = build_theme_page(tag, defn, wl_map)
        if page:
            safe_name = tag.replace(" ", "_").replace("/", "_")
            filepath = os.path.join(THEMES_DIR, f"{safe_name}.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(page)
            count = len(wl_map.get(tag, []))
            themes_built[tag] = count
            print(f"  {tag}: {count} {ru_plural(count, 'компания', 'компании', 'компаний')} -> {safe_name}.md")

    # Build index
    index = build_index(themes_built)
    with open(os.path.join(THEMES_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"\nГотово. Сгенерировано тематических страниц: {len(themes_built)} в каталоге themes/")


if __name__ == "__main__":
    main()
