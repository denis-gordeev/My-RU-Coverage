"""
utils.py — Shared utilities for all scripts.

Provides: file discovery, batch parsing, scope parsing, wikilink normalization,
category classification, valuation table rendering, metadata updates.
"""

import os
import re
import sys
import glob
from datetime import date, datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(PROJECT_ROOT, "Pilot_Reports")
TASK_FILE = os.path.join(PROJECT_ROOT, "task.md")
TICKER_PATTERN = r"[A-Z0-9][A-Z0-9._-]{0,11}"

MARKET_PROFILES = {
    ".ME": {
        "unit_label": "млн руб.",
        "price_symbol": "₽",
        "scope_label": "российский рынок",
    },
    ".TW": {
        "unit_label": "млн тайв. долл.",
        "price_symbol": "NT$",
        "scope_label": "тайваньский рынок",
    },
    ".TWO": {
        "unit_label": "млн тайв. долл.",
        "price_symbol": "NT$",
        "scope_label": "тайваньский OTC-рынок",
    },
}

DEFAULT_MARKET_SUFFIXES = [".ME", ".TW", ".TWO"]
DEFAULT_UNIT_LABEL = MARKET_PROFILES[".ME"]["unit_label"]

TICKER_SOURCE_OVERRIDES = {
    "YDEX": {
        "candidates": ["YDEX.ME", "YDEX"],
        "sector": "Communication Services",
        "industry": "Internet Content & Information",
        "identity_keywords": ["Yandex", "Яндекс", "МКПАО Яндекс"],
    },
    "T": {
        "candidates": ["TCSG.ME"],
        "sector": "Financial Services",
        "industry": "Financial Conglomerates",
        "identity_keywords": ["T-Technologies", "TCS GROUP", "Т-Технологии"],
    },
    "OZON": {
        "candidates": ["OZON.ME", "OZON"],
        "sector": "Consumer Cyclical",
        "industry": "Internet Retail",
        "identity_keywords": ["Ozon", "Озон"],
    },
    "TATN": {
        "candidates": ["TATN.ME", "TATNP.ME"],
        "sector": "Energy",
        "industry": "Oil & Gas Integrated",
        "identity_keywords": ["Tatneft", "Татнефть"],
    },
}

BUSINESS_SECTION_TITLE = "## Описание бизнеса"
SUPPLY_CHAIN_SECTION_TITLE = "## Положение в цепочке поставок"
CUSTOMERS_SECTION_TITLE = "## Ключевые клиенты и поставщики"
FINANCIAL_SECTION_TITLE = "## Финансовый обзор"
VALUATION_SECTION_TITLE = "### Оценочные мультипликаторы"
ANNUAL_SECTION_TITLE = "### Ключевые финансовые показатели по годам (3 года)"
QUARTERLY_SECTION_TITLE = "### Ключевые финансовые показатели по кварталам (4 квартала)"

SECTION_HEADER_REGEX = {
    "business": r"## (?:Описание бизнеса|業務簡介)",
    "supply_chain": r"## (?:Положение в цепочке поставок|供應鏈位置)",
    "customers": r"## (?:Ключевые клиенты и поставщики|主要客戶及供應商)",
    "financial": r"## (?:Финансовый обзор|財務概況)",
    "valuation": r"### (?:Оценочные мультипликаторы|估值指標)",
    "annual": r"### (?:Ключевые финансовые показатели по годам \(3 года\)|年度關鍵財務數據 \(近 3 年\))",
    "quarterly": r"### (?:Ключевые финансовые показатели по кварталам \(4 квартала\)|季度關鍵財務數據 \(近 4 季\))",
}

METADATA_LABEL_PATTERNS = {
    "sector": [r"\*\*Сектор:\*\*", r"\*\*板塊:\*\*"],
    "industry": [r"\*\*Отрасль:\*\*", r"\*\*產業:\*\*"],
    "market_cap": [r"\*\*Рыночная капитализация:\*\*", r"\*\*市值:\*\*"],
    "enterprise_value": [r"\*\*Стоимость предприятия \(EV\):\*\*", r"\*\*企業價值:\*\*"],
}


# =============================================================================
# File Discovery
# =============================================================================

def find_ticker_files(tickers=None, sector=None):
    """Find report files matching given tickers or sector.
    Returns dict: {ticker: filepath}
    """
    files = {}
    for fp in glob.glob(os.path.join(REPORTS_DIR, "**", "*.md"), recursive=True):
        fn = os.path.basename(fp)
        m = re.match(rf"^({TICKER_PATTERN})_", fn, re.IGNORECASE)
        if not m:
            continue
        t = m.group(1)

        if sector:
            folder = os.path.basename(os.path.dirname(fp))
            if folder.lower() != sector.lower():
                continue

        if tickers is None or t in tickers:
            files[t] = fp

    return files


def get_ticker_from_filename(filepath):
    """Extract ticker number and company name from a report filename."""
    fn = os.path.basename(filepath)
    m = re.match(rf"^({TICKER_PATTERN})_(.+)\.md$", fn, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    return None, None


# =============================================================================
# Batch & Scope Parsing
# =============================================================================

def get_batch_tickers(batch_num):
    """Get ticker list for a batch from task.md."""
    try:
        with open(TASK_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Не удалось прочитать task.md: {e}")
        return []

    pattern = re.compile(
        r"Batch\s+" + str(batch_num) + r"\*\*.*?:[:\s]*(.*)$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(content)
    if match:
        raw = match.group(1).strip().rstrip(".")
        return [
            re.search(r"(\d{4})", t).group(1)
            for t in raw.split(",")
            if re.search(r"\d{4}", t)
        ]
    print(f"Пакет {batch_num} не найден в task.md")
    return []


def parse_scope_args(args):
    """Parse CLI arguments into scope: tickers list, sector, or None (all).
    Returns (tickers_list_or_None, sector_or_None, description_string)
    """
    if not args:
        return None, None, "все тикеры"
    elif args[0] == "--batch":
        if len(args) < 2:
            print("Параметр --batch требует номер пакета")
            sys.exit(1)
        batch_num = args[1]
        tickers = get_batch_tickers(batch_num)
        return tickers, None, f"{len(tickers)} тикеров из пакета {batch_num}"
    elif args[0] == "--sector":
        if len(args) < 2:
            print("Параметр --sector требует название сектора")
            sys.exit(1)
        sector = " ".join(args[1:])
        return None, sector, f"все тикеры из сектора: {sector}"
    else:
        tickers = [
            t.strip() for t in args if re.match(rf"^{TICKER_PATTERN}$", t.strip(), re.IGNORECASE)
        ]
        return tickers, None, f"{len(tickers)} тикеров: {', '.join(tickers)}"


def setup_stdout():
    """Configure stdout for UTF-8 on Windows."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# =============================================================================
# Wikilink Normalization
# =============================================================================

# Canonical name mapping: alias -> canonical
# Local companies use local naming, foreign companies use global naming.
WIKILINK_ALIASES = {
    # Local market companies: English -> Chinese aliases kept for legacy corpus
    "TSMC": "台積電", "MediaTek": "聯發科", "Foxconn": "鴻海",
    "UMC": "聯電", "ASE": "日月光投控", "SPIL": "矽品",
    "Pegatron": "和碩", "Compal": "仁寶", "Quanta": "廣達",
    "Wistron": "緯創", "Inventec": "英業達",
    "ASUS": "華碩", "Acer": "宏碁", "Realtek": "瑞昱",
    "Novatek": "聯詠", "Himax": "奇景光電",
    "AUO": "友達", "Innolux": "群創",
    "Yageo": "國巨", "GlobalWafers": "環球晶",
    "KYEC": "京元電子", "ChipMOS": "南茂",
    "Unimicron": "欣興", "Delta": "台達電", "Lite-On": "光寶",
    "Largan": "大立光", "CTCI": "中鼎", "PTI": "力成",
    "WIN Semi": "穩懋", "Walsin": "華新科",
    "日月光": "日月光投控",
    # Foreign companies: local-language aliases -> English canonical
    "艾司摩爾": "ASML", "應用材料": "Applied Materials", "AMAT": "Applied Materials",
    "東京威力": "Tokyo Electron", "TEL": "Tokyo Electron",
    "科林研發": "Lam Research", "科磊": "KLA", "愛德萬": "Advantest",
    "英特爾": "Intel", "高通": "Qualcomm", "博通": "Broadcom",
    "輝達": "NVIDIA", "美光": "Micron", "海力士": "SK Hynix",
    "英飛凌": "Infineon", "恩智浦": "NXP", "瑞薩": "Renesas",
    "德州儀器": "Texas Instruments", "意法半導體": "STMicroelectronics",
    "安森美": "ON Semiconductor",
    "蘋果": "Apple", "三星": "Samsung", "索尼": "Sony",
    "谷歌": "Google", "微軟": "Microsoft", "特斯拉": "Tesla",
    "亞馬遜": "Amazon", "戴爾": "Dell", "惠普": "HP",
    "聯想": "Lenovo", "思科": "Cisco",
    "新思": "Synopsys", "益華": "Cadence", "安謀": "Arm", "ARM": "Arm",
    "博世": "Bosch", "電裝": "Denso",
    "信越": "Shin-Etsu", "信越化學": "Shin-Etsu",
    "Sumco": "SUMCO", "味之素": "Ajinomoto",
    "西門子": "Siemens", "霍尼韋爾": "Honeywell", "漢威": "Honeywell",
    "勞斯萊斯": "Rolls-Royce", "奇異": "GE Aerospace",
    "耐吉": "Nike", "耐克": "Nike", "愛迪達": "Adidas", "戴森": "Dyson",
    # Tech terms: standardize
    "SiC": "碳化矽", "GaN": "氮化鎵", "InP": "磷化銦", "GaAs": "砷化鎵",
    "共封裝光學": "CPO", "Co-Packaged Optics": "CPO",
    "IoT": "物聯網", "EV": "電動車", "印刷電路板": "PCB",
}


def normalize_wikilinks(content):
    """Normalize all wikilinks in content to canonical names.
    Also collapses duplicate parentheticals like [[X]] ([[X]]).
    Only operates on text before the financial section to protect tables.
    """
    split_parts = split_before_financial_section(content)
    if split_parts is None:
        return content

    text, financial_part = split_parts

    # Step 1: Replace alias wikilinks with canonical names
    for alias, canonical in WIKILINK_ALIASES.items():
        text = text.replace("[[" + alias + "]]", "[[" + canonical + "]]")

    # Step 2: Collapse [[X]] ([[X]]) duplicate parentheticals
    text = re.sub(
        r"\[\[([^\]]+)\]\]\s*[\(（]\[\[([^\]]+)\]\][\)）]",
        lambda m: f"[[{m.group(1)}]]" if m.group(1) == m.group(2) else m.group(0),
        text,
    )

    return text + financial_part


def extract_wikilinks(content):
    """Extract canonical wikilink targets, ignoring optional display aliases."""
    wikilinks = []
    for raw in re.findall(r"\[\[([^\]]+)\]\]", content):
        wikilinks.append(raw.split("|", 1)[0].strip())
    return wikilinks


# =============================================================================
# Category Classification (shared by build_wikilink_index, build_themes, build_network)
# =============================================================================

TECH_TERMS = {
    "AI", "PCB", "5G", "HBM", "CoWoS", "InFO", "EUV", "CPO", "FOPLP",
    "VCSEL", "EML", "MLCC", "MOSFET", "IGBT", "DRAM", "NAND", "SSD",
    "DDR5", "DDR4", "PCIe", "USB", "WiFi", "Bluetooth", "OLED", "AMOLED",
    "Mini LED", "Micro LED", "MCU", "SoC", "ASIC", "FPGA", "RF", "IC",
    "LED", "LCD", "TFT", "CMP", "CVD", "PVD", "ALD", "AOI", "SMT",
    "BGA", "QFN", "SOP", "ABF 載板", "BT 載板", "ABF", "SerDes", "PMIC",
    "LDO", "NOR Flash", "NAND Flash", "矽光子", "光收發模組",
}

MATERIAL_TERMS = {
    "碳化矽", "氮化鎵", "磷化銦", "砷化鎵", "矽晶圓", "銅箔", "玻纖布",
    "光阻液", "研磨液", "超純水", "氦氣", "氖氣", "鈦酸鋇", "聚醯亞胺",
    "導線架", "探針卡", "BT 樹脂", "銀漿", "銅漿", "氧化鋁",
    "золото", "алмазы", "железная руда", "коксующийся уголь", "сталь",
}

APPLICATION_TERMS = {
    "AI 伺服器", "電動車", "物聯網", "資料中心", "低軌衛星", "5G",
    "智慧家庭", "車用電子", "消費電子", "綠能", "太陽能", "風電",
    "儲能系統", "離岸風電", "自動駕駛", "智慧城市", "行車記錄器", "無人機",
    "электроэнергетика", "строительство", "машиностроение", "автопром",
    "трубная промышленность", "ювелирный рынок", "драгоценные металлы",
}

CATEGORY_COLORS = {
    "local_company": "#e74c3c",
    "international_company": "#3498db",
    "technology": "#2ecc71",
    "material": "#f39c12",
    "application": "#9b59b6",
}

CATEGORY_LABELS = {
    "local_company": "Локальная компания",
    "international_company": "Иностранная компания",
    "technology": "Технология / стандарт",
    "material": "Материал / подложка",
    "application": "Конечный рынок",
}


def is_local_language_name(s):
    """Check if a string is primarily written in a local non-Latin script."""
    if not s:
        return False

    cjk = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    cyrillic = sum(1 for c in s if "\u0400" <= c <= "\u04FF")
    return (cjk + cyrillic) > len(s) * 0.3


def classify_wikilink(name):
    """Classify a wikilink into a category."""
    if name in TECH_TERMS:
        return "technology"
    if name in MATERIAL_TERMS:
        return "material"
    if name in APPLICATION_TERMS:
        return "application"
    if is_local_language_name(name):
        return "local_company"
    return "international_company"


def get_market_profile(suffix=None):
    """Return unit/price settings for a ticker suffix."""
    return MARKET_PROFILES.get(suffix, MARKET_PROFILES[".ME"])


def split_before_financial_section(content):
    """Split content into pre-financial text and the financial section."""
    match = re.search(SECTION_HEADER_REGEX["financial"], content)
    if not match:
        return None
    return content[: match.start()], content[match.start() :]


# =============================================================================
# Valuation Table Rendering (shared by update_financials and update_valuation)
# =============================================================================

def fetch_valuation_data(info):
    """Extract valuation multiples from yfinance info dict.
    Returns dict with display values and metadata.
    """
    valuation = {}
    for key, label in [
        ("trailingPE", "P/E (TTM)"),
        ("forwardPE", "Forward P/E"),
        ("priceToSalesTrailing12Months", "P/S (TTM)"),
        ("priceToBook", "P/B"),
        ("enterpriseToEbitda", "EV/EBITDA"),
    ]:
        val = info.get(key)
        valuation[label] = f"{val:.2f}" if val else "N/A"

    # Price
    cur_price = info.get("currentPrice")
    valuation["_price"] = f"{cur_price:,.2f}" if cur_price else None
    currency = (info.get("currency") or "").upper()
    valuation["_currency_symbol"] = {
        "RUB": "₽",
        "TWD": "NT$",
        "USD": "$",
        "EUR": "€",
        "CNY": "¥",
        "JPY": "¥",
        "HKD": "HK$",
    }.get(currency, "$")

    # Period info
    mrq = info.get("mostRecentQuarter")
    nfy = info.get("nextFiscalYearEnd")
    valuation["_ttm_end"] = (
        datetime.fromtimestamp(mrq).strftime("%Y-%m-%d") if mrq else None
    )
    valuation["_fwd_end"] = (
        datetime.fromtimestamp(nfy).strftime("%Y-%m-%d") if nfy else None
    )

    return valuation


def build_valuation_table(v):
    """Build the valuation markdown section from valuation dict."""
    headers = ["P/E (TTM)", "Forward P/E", "P/S (TTM)", "P/B", "EV/EBITDA"]
    values = [v.get(h, "N/A") for h in headers]
    widths = [max(len(h), len(val)) for h, val in zip(headers, values)]
    header_row = "| " + " | ".join(h.rjust(w) for h, w in zip(headers, widths)) + " |"
    sep_row = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    val_row = "| " + " | ".join(val.rjust(w) for val, w in zip(values, widths)) + " |"

    today = date.today().strftime("%Y-%m-%d")
    period_parts = []
    if v.get("_price"):
        period_parts.append(f"Цена {v.get('_currency_symbol', '$')}{v['_price']} на {today}")
    if v.get("_ttm_end"):
        period_parts.append(f"TTM на {v['_ttm_end']}")
    if v.get("_fwd_end"):
        period_parts.append(f"Forward до {v['_fwd_end']}")
    period_note = " | ".join(period_parts) if period_parts else ""

    title = (
        f"{VALUATION_SECTION_TITLE} ({period_note})\n"
        if period_note
        else f"{VALUATION_SECTION_TITLE}\n"
    )
    return title + header_row + "\n" + sep_row + "\n" + val_row


def update_metadata(content, market_cap, enterprise_value, unit_label=DEFAULT_UNIT_LABEL):
    """Update market cap and EV metadata in file content."""
    market_cap_value = market_cap if market_cap not in (None, "", "None") else "N/A"
    enterprise_value_value = enterprise_value if enterprise_value not in (None, "", "None") else "N/A"

    for pattern in METADATA_LABEL_PATTERNS["market_cap"]:
        content = re.sub(rf"({pattern}) .+", rf"\1 {market_cap_value} {unit_label}", content)
    for pattern in METADATA_LABEL_PATTERNS["enterprise_value"]:
        content = re.sub(rf"({pattern}) .+", rf"\1 {enterprise_value_value} {unit_label}", content)
    return content


def update_company_classification(content, sector=None, industry=None):
    """Update sector and industry metadata when fresh values are available."""
    if sector and sector not in {"", "N/A", "Unknown"}:
        for pattern in METADATA_LABEL_PATTERNS["sector"]:
            content = re.sub(rf"({pattern}) .+", rf"\1 {sector}", content)
    if industry and industry not in {"", "N/A", "Unknown"}:
        for pattern in METADATA_LABEL_PATTERNS["industry"]:
            content = re.sub(rf"({pattern}) .+", rf"\1 {industry}", content)
    return content


# =============================================================================
# Section Replacement
# =============================================================================

def replace_section(content, section_header, new_body, next_section_header=None):
    """Replace content between section_header and next_section_header.
    If next_section_header is None, replaces to end of file.
    """
    if next_section_header:
        pattern = rf"({re.escape(section_header)}\n)(.*?)(?=\n{re.escape(next_section_header)})"
        return re.sub(pattern, rf"\g<1>{new_body}\n", content, flags=re.DOTALL)
    else:
        pattern = rf"{re.escape(section_header)}.*"
        return re.sub(pattern, f"{section_header}\n{new_body}\n", content, flags=re.DOTALL)
