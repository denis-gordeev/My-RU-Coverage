"""
utils.py — Общие утилиты для всех скриптов.

Обеспечивает: поиск файлов, разбор пакетов, определение области,
нормализацию викилинков, классификацию категорий, рендер таблиц оценки,
обновление метаданных.
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
}

DEFAULT_MARKET_SUFFIXES = [".ME"]
DEFAULT_UNIT_LABEL = MARKET_PROFILES[".ME"]["unit_label"]

TICKER_SOURCE_OVERRIDES = {
    "SNGS": {
        "candidates": ["SNGS.ME"],
        "sector": "Energy",
        "industry": "Oil & Gas Integrated",
        "identity_keywords": ["Surgutneftegas", "Сургутнефтегаз"],
    },
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
    "X5": {
        "candidates": ["X5.ME", "X5"],
        "sector": "Consumer Defensive",
        "industry": "Grocery Stores",
        "identity_keywords": ["X5", "ИКС 5", "Корпоративный центр ИКС 5"],
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
    "business": r"## Описание бизнеса",
    "supply_chain": r"## Положение в цепочке поставок",
    "customers": r"## Ключевые клиенты и поставщики",
    "financial": r"## Финансовый обзор",
    "valuation": r"### Оценочные мультипликаторы",
    "annual": r"### Ключевые финансовые показатели по годам \(3 года\)",
    "quarterly": r"### Ключевые финансовые показатели по кварталам \(4 квартала\)",
}

METADATA_LABEL_PATTERNS = {
    "sector": [r"\*\*Сектор:\*\*"],
    "industry": [r"\*\*Отрасль:\*\*"],
    "market_cap": [r"\*\*Рыночная капитализация:\*\*"],
    "enterprise_value": [r"\*\*Стоимость предприятия \(EV\):\*\*"],
}


# =============================================================================
# File Discovery
# =============================================================================

def find_ticker_files(tickers=None, sector=None):
    """Находит файлы отчётов по заданным тикерам или сектору.
    Возвращает dict: {тикер: путь_к_файлу}
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
    """Извлекает тикер и название компании из имени файла отчёта."""
    fn = os.path.basename(filepath)
    m = re.match(rf"^({TICKER_PATTERN})_(.+)\.md$", fn, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    return None, None


# =============================================================================
# Batch & Scope Parsing
# =============================================================================

def get_batch_tickers(batch_num):
    """Получает список тикеров для пакета из task.md."""
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
    """Разбирает аргументы CLI в область действия: список тикеров, сектор или None (все).
    Возвращает (список_тикеров_или_None, сектор_или_None, строка_описания)
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
    """Настраивает stdout для UTF-8 на Windows."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# =============================================================================
# Wikilink Normalization
# =============================================================================

# Canonical name mapping: alias -> canonical
# Russian market: Cyrillic aliases -> canonical names.
WIKILINK_ALIASES = {
    # Российские компании: кириллические алиасы -> канонические имена
    "Сбер": "SBER", "Сбербанк": "SBER",
    "Газпром": "GAZP", "Газпром нефть": "GAZP",
    "Яндекс": "YDEX", "МКПАО Яндекс": "YDEX",
    "Лукойл": "LKOH", "Роснефть": "ROSN", "НОВАТЭК": "NVTK",
    "Т-Технологии": "T", "Тинькофф": "T", "ТCS GROUP": "T",
    "Татнефть": "TATN",
    "Сургутнефтегаз": "SNGS",
    "Дом.РФ": "DOMRF", "ДОМ.РФ": "DOMRF",
    "Эталон": "ETLN",
    "ЕвроТранс": "EUTR",
    "Башнефть": "BANEP", "Башнефть ап": "BANEP",
    "Озон": "OZON",
    "ИКС 5": "X5", "X5 Group": "X5",
    "Аптеки 36.6": "APTK", "Аптеки 36 и 6": "APTK",
    "Астра": "ASTR",
    "Циан": "CNRU",
    "Аренадата": "DATA",
    "БАЗИС": "BAZA",
    "ЭЛ5-Энерго": "ELFV",
    # Иностранные компании: русские алиасы -> английские канонические
    "Эпл": "Apple", "Гугл": "Google", "Майкрософт": "Microsoft",
    "Тесла": "Tesla", "Амазон": "Amazon",
    # Технологические термины: стандартизация
    "SiC": "карбид кремния", "GaN": "нитрид галлия", "InP": "фосфид индия", "GaAs": "арсенид галлия",
    "IoT": "интернет вещей", "EV": "электромобиль",
    "ПК": "PCB", "Печатная плата": "PCB",
}


def normalize_wikilinks(content):
    """Нормализует все викилинки в контенте к каноническим именам.
    Также схлопывает дубликаты с круглыми скобками вроде [[X]] ([[X]]).
    Работает только на тексте до секции финансов для защиты таблиц.
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
    """Извлекает канонические цели викилинков, игнорируя опциональные алиасы."""
    wikilinks = []
    for raw in re.findall(r"\[\[([^\]]+)\]\]", content):
        wikilinks.append(raw.split("|", 1)[0].strip())
    return wikilinks


# =============================================================================
# Category Classification (shared by build_wikilink_index, build_themes, build_network)
# =============================================================================

TECH_TERMS = {
    "AI", "PCB", "5G", "HBM", "CoWoS", "EUV", "CPO", "FOPLP",
    "VCSEL", "EML", "MLCC", "MOSFET", "IGBT", "DRAM", "NAND", "SSD",
    "DDR5", "DDR4", "PCIe", "USB", "WiFi", "Bluetooth", "OLED", "AMOLED",
    "Mini LED", "Micro LED", "MCU", "SoC", "ASIC", "FPGA", "RF", "IC",
    "LED", "LCD", "TFT", "CMP", "CVD", "PVD", "ALD", "AOI", "SMT",
    "BGA", "QFN", "SOP", "SerDes", "PMIC",
    "LDO", "NOR Flash", "NAND Flash",
    "карбид кремния", "нитрид галлия", "фосфид индия", "арсенид галлия",
    "кремниевая фотоника", "оптический трансивер",
    "Astra Linux", "152-ФЗ", "ФСТЭК", "импортозамещение",
}

MATERIAL_TERMS = {
    "карбид кремния", "нитрид галлия", "фосфид индия", "арсенид галлия",
    "кремниевая подложка", "медная фольга", "стеклоткань",
    "фоторезист", "полировальная жидкость", "сверхчистая вода",
    "гелий", "неон", "титанат бария", "полиимид",
    "выводная рамка", "зондовая карта", "BT смола",
    "серебряная паста", "медная паста", "оксид алюминия",
    "золото", "алмазы", "железная руда", "коксующийся уголь", "сталь",
}

APPLICATION_TERMS = {
    "AI серверы", "электромобиль", "интернет вещей", "центр обработки данных",
    "низкоорбитальный спутник", "5G",
    "умный дом", "автомобильная электроника", "потребительская электроника",
    "зелёная энергетика", "солнечная энергия", "ветроэнергетика",
    "система хранения энергии", "офшорная ветроэнергетика", "автономное вождение",
    "умный город", "видеорегистратор", "беспилотник",
    "электроэнергетика", "строительство", "машиностроение", "автопром",
    "трубная промышленность", "ювелирный рынок", "драгоценные металлы",
    "САПР", "ЧПУ", "ИТ-компании", "ОРЭМ", "ДПМ", "АТС", "СО ЕЭС", "ЖКХ",
    "Честный ЗНАК", "льготное лекарственное обеспечение", "дженерики", "биоаналоги",
    "технологический суверенитет", "Байкал Электроник", "Эльбрус (процессор)",
    "Р7-Офис", "МойОфис", "Selectel", "Yandex Cloud", "BaaS", "DRaaS",
    "Авито Недвижимость", "Домклик", "ПИК", "Самолет", "ЕГРН", "ипотека",
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
    """Проверяет, записана ли строка преимущественно на локальном нелатинском алфавите."""
    if not s:
        return False

    cjk = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    cyrillic = sum(1 for c in s if "\u0400" <= c <= "\u04FF")
    return (cjk + cyrillic) > len(s) * 0.3


def classify_wikilink(name):
    """Классифицирует викилинк по категории."""
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
    """Возвращает настройки единиц измерения для суффикса тикера."""
    return MARKET_PROFILES.get(suffix, MARKET_PROFILES[".ME"])


def split_before_financial_section(content):
    """Разделяет контент на текст до финансовой секции и саму финансовую секцию."""
    match = re.search(SECTION_HEADER_REGEX["financial"], content)
    if not match:
        return None
    return content[: match.start()], content[match.start() :]


# =============================================================================
# Valuation Table Rendering (shared by update_financials and update_valuation)
# =============================================================================

def fetch_valuation_data(info):
    """Извлекает мультипликаторы оценки из словаря info yfinance.
    Возвращает dict с отображаемыми значениями и метаданными.
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
        "USD": "$",
        "EUR": "€",
        "CNY": "¥",
        "JPY": "¥",
        "HKD": "HK$",
    }.get(currency, "₽")

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
    """Строит раздел оценки оценки в формате markdown из словаря v."""
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
    """Обновляет метаданные рыночной капитализации и стоимости предприятия в содержимом файла."""
    market_cap_value = market_cap if market_cap not in (None, "", "None") else "Н/Д"
    enterprise_value_value = enterprise_value if enterprise_value not in (None, "", "None") else "Н/Д"

    for pattern in METADATA_LABEL_PATTERNS["market_cap"]:
        content = re.sub(rf"({pattern}) .+", rf"\1 {market_cap_value} {unit_label}", content)
    for pattern in METADATA_LABEL_PATTERNS["enterprise_value"]:
        content = re.sub(rf"({pattern}) .+", rf"\1 {enterprise_value_value} {unit_label}", content)
    return content


def update_company_classification(content, sector=None, industry=None):
    """Обновляет метаданные сектора и отрасли, когда доступны свежие значения."""
    if sector and sector not in {"", "Н/Д", "Unknown"}:
        for pattern in METADATA_LABEL_PATTERNS["sector"]:
            content = re.sub(rf"({pattern}) .+", rf"\1 {sector}", content)
    if industry and industry not in {"", "Н/Д", "Unknown"}:
        for pattern in METADATA_LABEL_PATTERNS["industry"]:
            content = re.sub(rf"({pattern}) .+", rf"\1 {industry}", content)
    return content


# =============================================================================
# Section Replacement
# =============================================================================

def replace_section(content, section_header, new_body, next_section_header=None):
    """Заменяет содержимое между section_header и next_section_header.
    Если next_section_header равен None, заменяет до конца файла.
    """
    if next_section_header:
        pattern = rf"({re.escape(section_header)}\n)(.*?)(?=\n{re.escape(next_section_header)})"
        return re.sub(pattern, rf"\g<1>{new_body}\n", content, flags=re.DOTALL)
    else:
        pattern = rf"{re.escape(section_header)}.*"
        return re.sub(pattern, f"{section_header}\n{new_body}\n", content, flags=re.DOTALL)
