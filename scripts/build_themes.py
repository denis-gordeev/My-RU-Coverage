"""
build_themes.py — Generate thematic investment screens from wikilink graph.

Scans all ticker reports for wikilinks, groups companies by theme (technology,
material, application), and generates markdown pages showing the full value chain
for each theme.

Usage:
  python scripts/build_themes.py              # Rebuild all themes
  python scripts/build_themes.py --list       # List available themes
  python scripts/build_themes.py "CoWoS"      # Rebuild single theme

Output: themes/ folder with one .md per theme.
"""

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import TICKER_PATTERN, extract_wikilinks

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "Pilot_Reports")
THEMES_DIR = os.path.join(os.path.dirname(__file__), "..", "themes")

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
        "related": ["природный газ", "СПГ"],
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
        "related": ["e-grocery", "экосистемы"],
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
    # === Advanced Packaging ===
    "CoWoS": {
        "name": "CoWoS 先進封裝",
        "desc": "台積電 Chip-on-Wafer-on-Substrate 2.5D 先進封裝技術，AI 晶片關鍵製程",
        "related": ["HBM", "2.5D 封裝", "3D 封裝", "ABF 載板", "矽中介層"],
    },
    "HBM": {
        "name": "HBM 高頻寬記憶體",
        "desc": "High Bandwidth Memory，AI 加速器必備的高速堆疊記憶體",
        "related": ["CoWoS", "AI 伺服器", "DRAM"],
    },
    "CPO": {
        "name": "CPO 共封裝光學",
        "desc": "Co-Packaged Optics，將光學元件整合於晶片封裝中以突破頻寬瓶頸",
        "related": ["矽光子", "光收發模組", "AI 伺服器", "資料中心"],
    },
    # === Photonics ===
    "矽光子": {
        "name": "矽光子 Silicon Photonics",
        "desc": "以矽基製程整合光學元件，實現高速光互連，下一代資料中心核心技術",
        "related": ["CPO", "EML", "VCSEL", "光收發模組", "資料中心"],
    },
    "VCSEL": {
        "name": "VCSEL 垂直共振腔面射型雷射",
        "desc": "3D 感測、光通訊及 LiDAR 核心光源元件",
        "related": ["矽光子", "光收發模組", "砷化鎵"],
    },
    # === Compound Semiconductors ===
    "碳化矽": {
        "name": "碳化矽 SiC",
        "desc": "第三代半導體材料，耐高壓高溫，電動車逆變器及充電樁關鍵材料",
        "related": ["電動車", "MOSFET", "IGBT", "氮化鎵"],
    },
    "氮化鎵": {
        "name": "氮化鎵 GaN",
        "desc": "第三代半導體材料，高頻高效，5G 基站、快充及衛星通訊核心",
        "related": ["5G", "碳化矽", "磷化銦"],
    },
    "磷化銦": {
        "name": "磷化銦 InP",
        "desc": "III-V 族化合物半導體，光通訊雷射及高速光電元件基板材料",
        "related": ["矽光子", "EML", "光收發模組", "砷化鎵"],
    },
    # === AI / Data Center ===
    "AI 伺服器": {
        "name": "AI 伺服器供應鏈",
        "desc": "AI 訓練與推論伺服器完整供應鏈，從晶片到系統到散熱",
        "related": ["CoWoS", "HBM", "NVIDIA", "CPO", "資料中心"],
    },
    "資料中心": {
        "name": "資料中心供應鏈",
        "desc": "超大規模資料中心基礎設施，涵蓋伺服器、網通、電源、散熱",
        "related": ["AI 伺服器", "CPO", "矽光子", "PCB"],
    },
    # === EV / Automotive ===
    "電動車": {
        "name": "電動車供應鏈",
        "desc": "電動車完整供應鏈，從電池材料到功率元件到車用電子",
        "related": ["碳化矽", "IGBT", "MOSFET", "車用電子"],
    },
    # === Applications ===
    "5G": {
        "name": "5G 通訊供應鏈",
        "desc": "5G 基礎建設與終端應用，涵蓋基站、天線、射頻前端、濾波器",
        "related": ["氮化鎵", "RF", "低軌衛星"],
    },
    "低軌衛星": {
        "name": "低軌衛星 LEO Satellite",
        "desc": "低軌道衛星通訊供應鏈，天線、地面站、射頻模組",
        "related": ["5G", "氮化鎵", "RF"],
    },
    # === Process / Equipment ===
    "EUV": {
        "name": "EUV 極紫外光微影",
        "desc": "先進製程關鍵微影技術，7nm 以下節點必備",
        "related": ["光阻液", "ASML"],
    },
    # === Materials ===
    "光阻液": {
        "name": "光阻液 Photoresist",
        "desc": "半導體微影製程關鍵化學材料",
        "related": ["EUV", "微影"],
    },
    "ABF 載板": {
        "name": "ABF 載板",
        "desc": "Ajinomoto Build-up Film 載板，高階 IC 封裝基板",
        "related": ["CoWoS", "AI 伺服器", "PCB"],
    },
    "矽晶圓": {
        "name": "矽晶圓",
        "desc": "半導體製造最基礎的原材料",
        "related": ["碳化矽", "磊晶"],
    },
    # === Key customers (cross-industry) ===
    "Apple": {
        "name": "Apple 蘋果供應鏈",
        "desc": "蘋果公司台灣供應鏈成員",
        "related": ["台積電", "鴻海"],
    },
    "NVIDIA": {
        "name": "NVIDIA 輝達供應鏈",
        "desc": "NVIDIA GPU 及 AI 平台台灣供應鏈",
        "related": ["CoWoS", "HBM", "AI 伺服器", "台積電"],
    },
    "Tesla": {
        "name": "Tesla 特斯拉供應鏈",
        "desc": "特斯拉電動車台灣供應鏈成員",
        "related": ["電動車", "碳化矽"],
    },
}


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
    """Build a single theme markdown page."""
    entries = wl_map.get(theme_tag, [])
    if not entries:
        return None

    lines = []
    lines.append(f"# {theme_def['name']}")
    lines.append("")
    lines.append(f"> {theme_def['desc']}")
    lines.append("")
    lines.append(f"**Количество компаний:** {len(entries)}")
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
        lines.append(f"## Верхний контур ({len(upstream)})")
        lines.append("")
        lines.extend(format_entries(upstream))
        lines.append("")

    if midstream:
        lines.append(f"## Ключевое звено ({len(midstream)})")
        lines.append("")
        lines.extend(format_entries(midstream))
        lines.append("")

    if downstream:
        lines.append(f"## Конечный спрос ({len(downstream)})")
        lines.append("")
        lines.extend(format_entries(downstream))
        lines.append("")

    if other:
        lines.append(f"## Связанные компании ({len(other)})")
        lines.append("")
        lines.extend(format_entries(other))
        lines.append("")

    return "\n".join(lines)


def build_index(themes_built):
    """Build themes/README.md index."""
    lines = []
    ru_theme_tags = [
        "банки",
        "финтех",
        "нефтегаз",
        "природный газ",
        "электроэнергетика",
        "телеком",
        "продуктовый ритейл",
        "золото",
        "сталь",
        "алмазы",
        "цветные металлы",
        "экосистемы",
        "биржевая инфраструктура",
        "финансовый рынок",
        "удобрения",
        "агрохимия",
    ]
    legacy_theme_tags = [
        "CoWoS",
        "HBM",
        "CPO",
        "矽光子",
        "VCSEL",
        "碳化矽",
        "氮化鎵",
        "磷化銦",
        "AI 伺服器",
        "資料中心",
        "電動車",
        "5G",
        "低軌衛星",
        "EUV",
        "光阻液",
        "ABF 載板",
        "矽晶圓",
        "Apple",
        "NVIDIA",
        "Tesla",
    ]
    ru_built = sum(1 for tag in ru_theme_tags if tag in themes_built)
    legacy_built = sum(1 for tag in legacy_theme_tags if tag in themes_built)

    lines.append("# Тематические подборки")
    lines.append("")
    lines.append("> Автогенерируемые карты цепочек стоимости и смежных компаний.")
    lines.append("> Навигация собрана в mixed-режиме: российские темы идут первыми, legacy-тайваньский корпус сохранён ниже для обратной совместимости.")
    lines.append("> Пересборка: `python scripts/build_themes.py`")
    lines.append("")
    lines.append(f"> Российских тем в индексе: {ru_built}. Legacy/global тем: {legacy_built}.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by category
    categories = {
        "Российский рынок": ru_theme_tags,
        "Legacy / Тайвань: передовая упаковка": ["CoWoS", "HBM", "CPO"],
        "Legacy / Тайвань: фотоника и compound semis": ["矽光子", "VCSEL", "碳化矽", "氮化鎵", "磷化銦"],
        "Legacy / Тайвань: AI и дата-центры": ["AI 伺服器", "資料中心", "NVIDIA"],
        "Legacy / Тайвань: электромобили и авто": ["電動車", "Tesla"],
        "Legacy / Тайвань: связь": ["5G", "低軌衛星"],
        "Legacy / Тайвань: процесс и оборудование": ["EUV"],
        "Legacy / Тайвань: материалы": ["光阻液", "ABF 載板", "矽晶圓"],
        "Legacy / Тайвань: брендовые цепочки": ["Apple", "NVIDIA", "Tesla"],
    }

    for cat_name, tags in categories.items():
        lines.append(f"## {cat_name}")
        lines.append("")
        for tag in tags:
            if tag in themes_built:
                count = themes_built[tag]
                safe_name = tag.replace(" ", "_").replace("/", "_")
                lines.append(f"- [{tag}]({safe_name}.md) — {count} компаний")
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
            print(f"  {tag}: {count} компаний -> {safe_name}.md")

    # Build index
    index = build_index(themes_built)
    with open(os.path.join(THEMES_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"\nГотово. Сгенерировано тематических страниц: {len(themes_built)} в каталоге themes/")


if __name__ == "__main__":
    main()
