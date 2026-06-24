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
        "sector": "Энергетика",
        "industry": "Нефтегазовая интегрированная",
        "identity_keywords": ["Surgutneftegas", "Сургутнефтегаз"],
    },
    "YDEX": {
        "candidates": ["YDEX.ME", "YDEX"],
        "sector": "Связь",
        "industry": "Интернет-контент и информация",
        "identity_keywords": ["Yandex", "Яндекс", "МКПАО Яндекс"],
    },
    "T": {
        "candidates": ["TCSG.ME"],
        "sector": "Финансовые услуги",
        "industry": "Финансовые холдинги",
        "identity_keywords": ["T-Technologies", "TCS GROUP", "Т-Технологии"],
    },
    "OZON": {
        "candidates": ["OZON.ME", "OZON"],
        "sector": "Потребительские товары и услуги",
        "industry": "Интернет-розница",
        "identity_keywords": ["Ozon", "Озон"],
    },
    "X5": {
        "candidates": ["X5.ME", "X5"],
        "sector": "Потребительские товары повседневного спроса",
        "industry": "Продуктовые магазины",
        "identity_keywords": ["X5", "ИКС 5", "Корпоративный центр ИКС 5"],
    },
    "TATN": {
        "candidates": ["TATN.ME", "TATNP.ME"],
        "sector": "Энергетика",
        "industry": "Нефтегазовая интегрированная",
        "identity_keywords": ["Tatneft", "Татнефть"],
    },
}

# Соответствие английских названий секторов/отраслей русским (для обратной совместимости и миграции)
SECTOR_TRANSLATION = {
    "Energy": "Энергетика",
    "Financial Services": "Финансовые услуги",
    "Communication Services": "Связь",
    "Consumer Defensive": "Потребительские товары повседневного спроса",
    "Consumer Cyclical": "Потребительские товары и услуги",
    "Technology": "Технологии",
    "Healthcare": "Здравоохранение",
    "Industrials": "Промышленность",
    "Basic Materials": "Основные материалы",
    "Materials": "Материалы",
    "Steel": "Сталь",
    "Telecom Services": "Телекоммуникации",
    "Real Estate": "Недвижимость",
    "Real Estate Services": "Услуги в сфере недвижимости",
    "Other Industrial Metals & Mining": "Прочие промышленные металлы и добыча",
    "Agricultural Inputs": "Сельскохозяйственные ресурсы",
    "Software - Application": "Программное обеспечение — приложения",
    "Utilities - Regulated Electric": "Коммунальные услуги — регулируемая электроэнергетика",
    "Utilities": "Коммунальные услуги",
    "Grocery Stores": "Продуктовые магазины",
    "Internet Retail": "Интернет-розница",
    "Internet Content & Information": "Интернет-контент и информация",
    "Unknown": "Не определено",
}

INDUSTRY_TRANSLATION = {
    # Энергетика
    "Oil & Gas Integrated": "Нефтегазовая интегрированная",
    "Oil & Gas E&P": "Нефтегазовая разведка и добыча",
    # Финансовые услуги
    "Banks - Regional": "Банки — региональные",
    "Financial Conglomerates": "Финансовые холдинги",
    "Credit Services": "Кредитные услуги",
    "Financial Data & Stock Exchanges": "Финансовые данные и фондовые биржи",
    # Связь
    "Telecom Services": "Телекоммуникационные услуги",
    "Internet Content & Information": "Интернет-контент и информация",
    # Потребительские товары повседневного спроса
    "Grocery Stores": "Продуктовые магазины",
    "Farm Products": "Сельскохозяйственная продукция",
    "Beverages - Wineries & Distilleries": "Напитки — виноделие и ликёро-водочная продукция",
    # Потребительские товары и услуги
    "Internet Retail": "Интернет-розница",
    "Discount Stores": "Магазины низких цен",
    # Технологии
    "Software - Application": "Программное обеспечение — приложения",
    "Software - Infrastructure": "Программное обеспечение — инфраструктура",
    "Information Technology Services": "ИТ-услуги",
    # Промышленность
    "Airlines": "Авиакомпании",
    "Railroads": "Железные дороги",
    # Материалы / Основные материалы
    "Aluminum": "Алюминий",
    "Gold": "Золото",
    "Steel": "Сталь",
    "Agricultural Inputs": "Сельскохозяйственные ресурсы",
    # Прочие промышленные металлы и добыча
    "Other Industrial Metals & Mining": "Прочие промышленные металлы и добыча",
    "Other Precious Metals & Mining": "Прочие драгоценные металлы и добыча",
    # Недвижимость
    "Real Estate - Development": "Недвижимость — застройка",
    "Real Estate Services": "Услуги в сфере недвижимости",
    # Здравоохранение
    "Pharmaceutical Retailers": "Аптечные сети",
    # Коммунальные услуги
    "Utilities - Regulated Electric": "Коммунальные услуги — регулируемая электроэнергетика",
    "Utilities - Renewable": "Коммунальные услуги — возобновляемая энергетика",
}


def translate_sector(sector: str) -> str:
    """Переводит название сектора на русский, если есть в списке соответствий."""
    if not sector:
        return sector
    return SECTOR_TRANSLATION.get(sector, sector)


def translate_industry(industry: str) -> str:
    """Переводит название отрасли на русский, если есть в списке соответствий."""
    if not industry:
        return industry
    return INDUSTRY_TRANSLATION.get(industry, industry)

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
# Поиск файлов
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
# Разбор области действия
# =============================================================================

def parse_scope_args(args):
    """Разбирает аргументы CLI в область действия: список тикеров, сектор или None (все).
    Возвращает (список_тикеров_или_None, сектор_или_None, строка_описания)
    """
    if not args:
        return None, None, "все тикеры"
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
# Нормализация викилинков
# =============================================================================

# Соответствие канонических имён: алиас -> каноническое
# Российский рынок: кириллические алиасы -> канонические имена.
WIKILINK_ALIASES = {
    "Сбер": "SBER", "Сбербанк": "SBER",
    "Газпром": "GAZP",
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
    "ИКС 5": "X5",     "X5 Group": "X5", "X5 Группа": "X5",
    "Аптеки 36.6": "APTK", "Аптеки 36 и 6": "APTK",
    "Астра": "ASTR",
    "Циан": "CNRU",
    "Аренадата": "DATA",
    "БАЗИС": "BAZA",
    "ЭЛ5-Энерго": "ELFV",
    "SiC": "карбид кремния", "GaN": "нитрид галлия", "InP": "фосфид индия", "GaAs": "арсенид галлия",
    "IoT": "интернет вещей",
    "FMCG": "ТНП",
    "BaaS": "резервное копирование как услуга", "DRaaS": "аварийное восстановление как услуга",
    "SaaS": "программное обеспечение как услуга", "IaaS": "инфраструктура как услуга",
    "SLA": "соглашение об уровне обслуживания",
    "Yandex Cloud": "Yandex Облако", "Яндекс Облако": "Yandex Облако",
    "VK Cloud": "VK Облако",
    "МТС Cloud": "МТС Облако",
    "МТС Premium": "МТС Премиум",
    "SCM Group": "Группа SCM",
    "маркетплейс": "торговая площадка",
    "дата-центр": "центр обработки данных",
    "инжиниринговые": "инженерно-технические",
    "трейдеры": "торговые компании",
    "дистрибьюторы": "оптовые поставщики",
    "дистрибуция": "распределение",
    "риелторы": "агенты по недвижимости",
    "маркетмейкеры": "поставщики ликвидности",
    "нефтетрейдеры": "торговые компании по нефти",
    "энерготрейдинг": "торговля электроэнергией",
    "софт": "программное обеспечение",
    "биллинг": "расчётно-учётная система",
    "контент-менеджеры": "редакторы содержимого",
    "концерн": "холдинг",
    "драйверы": "движущие силы",
    "промоактивность": "мероприятия по продвижению",
    "продуктовый микс": "ассортимент",
    "экспозиция": "доля",
    "дифференцируется": "выделяется",
    "дженерики": "препараты-аналоги",
    "логистика": "транспортно-складское обеспечение",
    "логистический": "транспортно-складской",
    "бизнес": "предприятие",
    "брокер": "торговой посредник на фондовом рынке",
    "брокерские": "посреднические",
    "клиринг": "взаимозачёт обязательств",
    "клиринговый": "взаимозачётный",
    "кластер": "узел",
    "трафик": "поток посетителей",
    "контент": "информационное наполнение",
    "медиа": "информационно-развлекательные сервисы",
    "спрэд": "разница цен",
    "интегратор": "поставщик комплексных решений",
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

    # Шаг 1: Заменяем алиасы викилинков на канонические имена
    for alias, canonical in WIKILINK_ALIASES.items():
        text = text.replace("[[" + alias + "]]", "[[" + canonical + "]]")

    # Шаг 2: Схлопываем дубликаты [[X]] ([[X]])
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
# Классификация категорий (общее для build_wikilink_index, build_themes, build_network)
# =============================================================================

TECH_TERMS = {
    "AI", "5G", "IoT", "OLED", "AMOLED",
    "MCU", "SoC", "ASIC", "FPGA", "RF", "IC",
    "LED",
    "карбид кремния", "нитрид галлия", "фосфид индия", "арсенид галлия",
    "Astra Linux", "152-ФЗ", "ФСТЭК", "импортозамещение",
}

MATERIAL_TERMS = {
    "карбид кремния", "нитрид галлия", "фосфид индия", "арсенид галлия",
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
    "Честный ЗНАК", "льготное лекарственное обеспечение", "препараты-аналоги", "биоаналоги",
    "технологический суверенитет", "Байкал Электроник", "Эльбрус (процессор)",
    "Р7-Офис", "МойОфис", "Селектел", "Yandex Облако",
    "резервное копирование как услуга", "аварийное восстановление как услуга",
    "программное обеспечение как услуга", "инфраструктура как услуга",
    "соглашение об уровне обслуживания",
    "Авито Недвижимость", "Домклик", "ПИК", "Самолет", "ЕГРН", "ипотека",
    "ТНП", "ЦОД", "воспроизведённые лекарственные препараты",
}

GEO_TERMS = {
    "Россия", "Китай", "Мурманская область", "Карелия", "Башкортостан",
    "Москва", "Санкт-Петербург", "Сибирь", "Дальний Восток", "Урал",
    "Татарстан", "Ямало-Ненецкий АО", "ХМАО", "Кузбасс", "Воронежская область",
}

REGULATORY_TERMS = {
    "44-ФЗ", "223-ФЗ", "152-ФЗ", "ОРЭМ", "ДПМ", "АТС", "ЖКХ",
    "ФСТЭК", "ФАС", "ЦБ", "Минцифры", "СО ЕЭС",
}

CATEGORY_COLORS = {
    "локальная_компания": "#e74c3c",
    "иностранная_компания": "#3498db",
    "технология": "#2ecc71",
    "материал": "#f39c12",
    "конечный_рынок": "#9b59b6",
    "географический_объект": "#1abc9c",
    "регулирование": "#e67e22",
}

CATEGORY_LABELS = {
    "локальная_компания": "Российская компания",
    "иностранная_компания": "Иностранная компания",
    "технология": "Технология / стандарт",
    "материал": "Материал / сырьё",
    "конечный_рынок": "Конечный рынок",
    "географический_объект": "Географический объект",
    "регулирование": "Регулирование / стандарт",
}


def is_local_language_name(s):
    """Проверяет, записана ли строка преимущественно на кириллице."""
    if not s:
        return False

    cyrillic = sum(1 for c in s if "\u0400" <= c <= "\u04FF")
    return cyrillic > len(s) * 0.3


LOCAL_COMPANY_TICKERS = {
    "MOEX", "SBER", "GAZP", "LKOH", "ROSN", "NVTK", "TATN", "SNGS",
    "YDEX", "OZON", "X5", "MGNT", "VTBR", "MTSS", "AFKS", "T",
    "PLZL", "GMKN", "ALRS", "MAGN", "CHMF", "NLMK", "PHOR", "AKRN",
    "ENPG", "IRAO", "HYDR", "AFLT", "BANEP", "CBOM", "BSPB", "DOMRF",
    "ETLN", "EUTR", "APTK", "ASTR", "CNRU", "DATA", "BAZA", "ELFV",
    "AQUA", "BELU",
    "VK Облако", "Kaspersky", "YADRO", "DataPro", "Wildberries",
    "VK", "LSR", "IMOEX", "Astra Linux SE", "Селектел",
    "МТС Облако", "Ростелеком Центр обработки данных",
}

def classify_wikilink(name):
    """Классифицирует викилинк по категории."""
    lower = name.lower()
    if lower in {t.lower() for t in TECH_TERMS} or name in TECH_TERMS:
        return "технология"
    if lower in {t.lower() for t in MATERIAL_TERMS} or name in MATERIAL_TERMS:
        return "материал"
    if lower in {t.lower() for t in APPLICATION_TERMS} or name in APPLICATION_TERMS:
        return "конечный_рынок"
    if name in LOCAL_COMPANY_TICKERS:
        return "локальная_компания"
    if name in REGULATORY_TERMS:
        return "регулирование"
    if name in GEO_TERMS:
        return "географический_объект"
    if is_local_language_name(name):
        return "локальная_компания"
    return "иностранная_компания"


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
# Рендер таблиц оценки (общее для update_financials и update_valuation)
# =============================================================================

def fetch_valuation_data(info):
    """Извлекает мультипликаторы оценки из словаря info yfinance.
    Возвращает dict с отображаемыми значениями и метаданными.
    """
    valuation = {}
    for key, label in [
        ("trailingPE", "P/E (за 12 мес.)"),
        ("forwardPE", "Прогнозный P/E"),
        ("priceToSalesTrailing12Months", "P/S (за 12 мес.)"),
        ("priceToBook", "P/B"),
        ("enterpriseToEbitda", "EV/EBITDA"),
    ]:
        val = info.get(key)
        valuation[label] = f"{val:.2f}" if val else "Н/Д"

    # Цена
    cur_price = info.get("currentPrice")
    valuation["_price"] = f"{cur_price:,.2f}" if cur_price else None
    currency = (info.get("currency") or "").upper()
    valuation["_currency_symbol"] = {
        "RUB": "₽",
        "USD": "$",
        "EUR": "€",
        "CNY": "¥",
    }.get(currency, "₽")

    # Информация о периодах
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
    """Строит раздел оценочных мультипликаторов в формате markdown из словаря v."""
    headers = ["P/E (за 12 мес.)", "Прогнозный P/E", "P/S (за 12 мес.)", "P/B", "EV/EBITDA"]
    values = [v.get(h, "Н/Д") for h in headers]
    widths = [max(len(h), len(val)) for h, val in zip(headers, values)]
    header_row = "| " + " | ".join(h.rjust(w) for h, w in zip(headers, widths)) + " |"
    sep_row = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    val_row = "| " + " | ".join(val.rjust(w) for val, w in zip(values, widths)) + " |"

    today = date.today().strftime("%Y-%m-%d")
    period_parts = []
    if v.get("_price"):
        period_parts.append(f"Цена {v.get('_currency_symbol', '₽')}{v['_price']} на {today}")
    if v.get("_ttm_end"):
        period_parts.append(f"за 12 мес. на {v['_ttm_end']}")
    if v.get("_fwd_end"):
        period_parts.append(f"Прогноз до {v['_fwd_end']}")
    period_note = " | ".join(period_parts) if period_parts else ""

    title = (
        f"{VALUATION_SECTION_TITLE} ({period_note})\n"
        if period_note
        else f"{VALUATION_SECTION_TITLE}\n"
    )
    footnote = "\n*P/E — цена/прибыль, P/S — цена/выручка, P/B — цена/балансовая стоимость, EV/EBITDA — стоимость предприятия/прибыль до вычета процентов, налогов и амортизации*"
    return title + header_row + "\n" + sep_row + "\n" + val_row + footnote


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
    """Обновляет метаданные сектора и отрасли, когда доступны свежие значения.
    Автоматически переводит английские названия на русский.
    """
    if sector and sector not in {"", "Н/Д", "Не определено"}:
        sector = translate_sector(sector)
        for pattern in METADATA_LABEL_PATTERNS["sector"]:
            content = re.sub(rf"({pattern}) .+", rf"\1 {sector}", content)
    if industry and industry not in {"", "Н/Д", "Не определено"}:
        industry = translate_industry(industry)
        for pattern in METADATA_LABEL_PATTERNS["industry"]:
            content = re.sub(rf"({pattern}) .+", rf"\1 {industry}", content)
    return content


# =============================================================================
# Замена секций
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
