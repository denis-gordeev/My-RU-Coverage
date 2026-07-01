"""
update_financials.py — Обновление финансовых таблиц в отчётах тикеров.

Загружает последние годовые (3 года) и квартальные (4 кв.) данные из yfinance,
затем заменяет ТОЛЬКО раздел `## Финансовый обзор` в каждом файле отчёта.
Всё содержимое обогащения (описание деятельности, цепочка поставок, контрагенты) сохраняется.

Использование:
  python scripts/update_financials.py                       # Обновить ВСЕ тикеры
  python scripts/update_financials.py SBER                  # Один тикер
  python scripts/update_financials.py SBER GAZP LKOH        # Несколько тикеров
  python scripts/update_financials.py --sector Энергетика   # Весь сектор
  python scripts/update_financials.py --dry-run SBER        # Предпросмотр без записи

Единицы измерения зависят от суффикса биржи: `.ME` -> млн руб.
"""

import os
import re
import sys
import time

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    find_ticker_files, parse_scope_args, setup_stdout,
    fetch_valuation_data, build_valuation_table, update_metadata,
    update_company_classification, DEFAULT_MARKET_SUFFIXES, get_market_profile,
    FINANCIAL_SECTION_TITLE, ANNUAL_SECTION_TITLE, QUARTERLY_SECTION_TITLE,
    SECTION_HEADER_REGEX, TICKER_SOURCE_OVERRIDES,
)

# Финансовые метрики для извлечения
METRICS_KEYS = {
    "выручка": ["Total Revenue"],
    "валовая_прибыль": ["Gross Profit"],
    "коммерческие_расходы": ["Selling And Marketing Expense"],
    "расходы_ниокр": ["Research And Development"],
    "общехозяйственные_расходы": ["General And Administrative Expense"],
    "операционная_прибыль": ["Operating Income"],
    "чистая_прибыль": ["Net Income", "Net Income Common Stockholders"],
    "операционный_поток": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "инвестиционный_поток": ["Investing Cash Flow", "Total Cashflows From Investing Activities"],
    "финансовый_поток": ["Financing Cash Flow", "Total Cash From Financing Activities"],
    "капитальные_затраты": ["Capital Expenditure", "Capital Expenditures"],
}

METRIC_LABELS = {
    "выручка": "Выручка",
    "валовая_прибыль": "Валовая прибыль",
    "валовая_маржа": "Валовая маржа (%)",
    "коммерческие_расходы": "Коммерческие расходы",
    "расходы_ниокр": "Расходы на НИОКР",
    "общехозяйственные_расходы": "Общехозяйственные расходы",
    "операционная_прибыль": "Операционная прибыль",
    "операционная_маржа": "Операционная маржа (%)",
    "чистая_прибыль": "Чистая прибыль",
    "чистая_маржа": "Чистая маржа (%)",
    "операционный_поток": "Операционный денежный поток",
    "инвестиционный_поток": "Инвестиционный денежный поток",
    "финансовый_поток": "Финансовый денежный поток",
    "капитальные_затраты": "Капитальные затраты",
}


def get_series(df, keys):
    for key in keys:
        if key in df.index:
            return df.loc[key]
    return pd.Series(dtype=float)


def calc_margin(numerator, denominator):
    if denominator.empty or numerator.empty:
        return pd.Series(dtype=float)
    result = (numerator / denominator) * 100
    result = result.replace([float("inf"), float("-inf")], float("nan"))
    return result


def calc_admin_exp(income_stmt):
    """Получает административные расходы, при отсутствии — вычисляет как SGA − коммерческие расходы."""
    admin = get_series(income_stmt, METRICS_KEYS["общехозяйственные_расходы"])
    selling = get_series(income_stmt, METRICS_KEYS["коммерческие_расходы"])
    sga = get_series(income_stmt, ["Selling General And Administration"])

    if admin.empty and not sga.empty and not selling.empty:
        # Выводим управленческие расходы = SGA − коммерческие
        return sga - selling
    elif not admin.empty and not sga.empty:
        # Заполняем пропуски в управленческих расходах из SGA − коммерческие
        derived = sga - selling
        return admin.fillna(derived)
    return admin


def extract_metrics(income_stmt, cashflow):
    if income_stmt.empty and cashflow.empty:
        return pd.DataFrame()

    data = {
        METRIC_LABELS["выручка"]: get_series(income_stmt, METRICS_KEYS["выручка"]),
        METRIC_LABELS["валовая_прибыль"]: get_series(income_stmt, METRICS_KEYS["валовая_прибыль"]),
        METRIC_LABELS["валовая_маржа"]: calc_margin(
            get_series(income_stmt, METRICS_KEYS["валовая_прибыль"]),
            get_series(income_stmt, METRICS_KEYS["выручка"]),
        ),
        METRIC_LABELS["коммерческие_расходы"]: get_series(income_stmt, METRICS_KEYS["коммерческие_расходы"]),
        METRIC_LABELS["расходы_ниокр"]: get_series(income_stmt, METRICS_KEYS["расходы_ниокр"]),
        METRIC_LABELS["общехозяйственные_расходы"]: calc_admin_exp(income_stmt),
        METRIC_LABELS["операционная_прибыль"]: get_series(income_stmt, METRICS_KEYS["операционная_прибыль"]),
        METRIC_LABELS["операционная_маржа"]: calc_margin(
            get_series(income_stmt, METRICS_KEYS["операционная_прибыль"]),
            get_series(income_stmt, METRICS_KEYS["выручка"]),
        ),
        METRIC_LABELS["чистая_прибыль"]: get_series(income_stmt, METRICS_KEYS["чистая_прибыль"]),
        METRIC_LABELS["чистая_маржа"]: calc_margin(
            get_series(income_stmt, METRICS_KEYS["чистая_прибыль"]),
            get_series(income_stmt, METRICS_KEYS["выручка"]),
        ),
        METRIC_LABELS["операционный_поток"]: get_series(cashflow, METRICS_KEYS["операционный_поток"]),
        METRIC_LABELS["инвестиционный_поток"]: get_series(cashflow, METRICS_KEYS["инвестиционный_поток"]),
        METRIC_LABELS["финансовый_поток"]: get_series(cashflow, METRICS_KEYS["финансовый_поток"]),
        METRIC_LABELS["капитальные_затраты"]: get_series(cashflow, METRICS_KEYS["капитальные_затраты"]),
    }

    # Выводим CAPEX из FCF при отсутствии: CAPEX = FCF − операционный поток (отрицательный)
    capex = data[METRIC_LABELS["капитальные_затраты"]]
    ocf = data[METRIC_LABELS["операционный_поток"]]
    fcf = get_series(cashflow, ["Free Cash Flow"])
    if not capex.empty and not ocf.empty and not fcf.empty:
        derived_capex = fcf - ocf
        data[METRIC_LABELS["капитальные_затраты"]] = capex.fillna(derived_capex)
    elif capex.empty and not ocf.empty and not fcf.empty:
        data[METRIC_LABELS["капитальные_затраты"]] = fcf - ocf

    df = pd.DataFrame(data).T
    # Очищаем заголовки столбцов: убираем временную часть из datetime
    df.columns = [
        col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        for col in df.columns
    ]
    return df


def localize_metric_labels(df, suffix):
    """Устаревшая функция — метрики уже создаются с русскими подписями."""
    return df


def get_source_candidates(ticker):
    """Возвращает приоритизированный список кандидатов источников финансов для тикера."""
    override = TICKER_SOURCE_OVERRIDES.get(ticker, {})
    candidates = override.get("кандидаты")
    if candidates:
        return candidates
    return [f"{ticker}{suffix}" for suffix in DEFAULT_MARKET_SUFFIXES]


def infer_market_suffix(symbol):
    for suffix in DEFAULT_MARKET_SUFFIXES:
        if symbol.endswith(suffix):
            return suffix
    return ".ME"


def is_identity_match(ticker, symbol, info):
    """Отклоняет очевидные совпадения символов, например `T` -> AT&T."""
    override = TICKER_SOURCE_OVERRIDES.get(ticker, {})
    keywords = override.get("ключевые_слова_идентификации", [])
    if not keywords:
        return True

    haystack = " ".join(
        str(info.get(key, "") or "")
        for key in ("shortName", "longName", "displayName", "symbol")
    ).lower()

    if not haystack.strip():
        return symbol == get_source_candidates(ticker)[0]

    return any(keyword.lower() in haystack for keyword in keywords)


def prepare_statement_df(df, suffix, max_columns):
    if df.empty:
        return df

    if METRIC_LABELS["выручка"] in df.index:
        valid_cols = df.columns[df.loc[METRIC_LABELS["выручка"]].notna()]
        df = df[valid_cols]
    else:
        df = df.dropna(axis=1, how="all")

    df = df[sorted(df.columns, reverse=True)]
    non_pct = [row for row in df.index if "%" not in row]
    df.loc[non_pct] = df.loc[non_pct] / 1_000_000
    df = df.iloc[:, :max_columns]
    return localize_metric_labels(df, suffix)


def score_source(data):
    annual_cols = 0 if data["годовые"] is None else len(data["годовые"].columns)
    quarterly_cols = 0 if data["квартальные"] is None else len(data["квартальные"].columns)
    has_market_cap = 1 if data.get("рыночная_капитализация") not in (None, "Н/Д") else 0
    has_sector = 1 if data.get("сектор") not in (None, "", "Н/Д", "Не определено") else 0
    return (annual_cols + quarterly_cols, has_market_cap, has_sector)


def fetch_financials(ticker):
    """Загружает финансовые данные с проверкой приоритета источников."""
    override = TICKER_SOURCE_OVERRIDES.get(ticker, {})
    best_data = None
    best_score = (-1, -1, -1)

    for symbol in get_source_candidates(ticker):
        try:
            stock = yf.Ticker(symbol)
            info = stock.info or {}
            if not is_identity_match(ticker, symbol, info):
                continue

            suffix = infer_market_suffix(symbol)
            df_annual = prepare_statement_df(
                extract_metrics(stock.income_stmt, stock.cashflow), suffix, 3
            )
            df_quarterly = prepare_statement_df(
                extract_metrics(stock.quarterly_income_stmt, stock.quarterly_cashflow),
                suffix,
                4,
            )

            market_cap = (
                f"{info['marketCap'] / 1_000_000:,.0f}"
                if info.get("marketCap")
                else "Н/Д"
            )
            enterprise_value = (
                f"{info['enterpriseValue'] / 1_000_000:,.0f}"
                if info.get("enterpriseValue")
                else "Н/Д"
            )

            valuation = fetch_valuation_data(info)
            market_profile = get_market_profile(suffix)
            data = {
                "годовые": df_annual,
                "квартальные": df_quarterly,
                "оценка": valuation,
                "рыночная_капитализация": market_cap,
                "стоимость_предприятия": enterprise_value,
                "сектор": info.get("sector") or override.get("сектор", "Н/Д"),
                "отрасль": info.get("industry") or override.get("отрасль", "Н/Д"),
                "суффикс": suffix,
                "единица_измерения": market_profile["единица"],
                "символ_источника": symbol,
            }

            if data["годовые"].empty and data["квартальные"].empty and market_cap == "Н/Д" and enterprise_value == "Н/Д":
                continue

            data_score = score_source(data)
            if data_score > best_score:
                best_data = data
                best_score = data_score
        except Exception:
            continue
    return best_data


def df_to_clean_markdown(df):
    """Форматирует DataFrame в markdown с точностью .2f, затем заменяет NaN на -."""
    # Форматируем числа, пока тип данных ещё float
    md = df.to_markdown(floatfmt=".2f")
    # Заменяем строки nan, которые to_markdown генерирует для значений NaN
    md = md.replace(" nan ", " - ")
    md = md.replace(" nan|", " -|")
    md = md.replace("|nan ", "|- ")
    # Также обрабатываем краевые случаи с отступами
    md = re.sub(r'\bnan\b', '-', md)
    return md


def build_financial_section(data):
    unit_label = data.get("единица_измерения", "млн руб.")
    section = f"{FINANCIAL_SECTION_TITLE} (единицы: {unit_label}, маржа указана в %)\n"

    v = data.get("оценка", {})
    if v:
        section += build_valuation_table(v) + "\n\n"

    section += f"{ANNUAL_SECTION_TITLE}\n"
    if data["годовые"] is not None and not data["годовые"].empty:
        section += df_to_clean_markdown(data["годовые"]) + "\n\n"
    else:
        section += "Нет доступных данных.\n\n"
    section += f"{QUARTERLY_SECTION_TITLE}\n"
    if data["квартальные"] is not None and not data["квартальные"].empty:
        section += df_to_clean_markdown(data["квартальные"]) + "\n"
    else:
        section += "Нет доступных данных.\n"
    return section


def update_file(filepath, ticker, dry_run=False):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    data = fetch_financials(ticker)
    if data is None:
        print(f"  {ticker}: пропуск (yfinance не вернул данные)")
        return False

    new_fin = build_financial_section(data)

    if re.search(SECTION_HEADER_REGEX["финансовый_обзор"], content):
        new_content = re.sub(rf"{SECTION_HEADER_REGEX['финансовый_обзор']}.*", new_fin, content, flags=re.DOTALL)
    else:
        new_content = content.rstrip() + "\n\n" + new_fin

    # Обновляем метаданные
    new_content = update_metadata(
        new_content,
        data.get("рыночная_капитализация"),
        data.get("стоимость_предприятия"),
        data.get("единица_измерения", "млн руб."),
    )
    new_content = update_company_classification(
        new_content,
        data.get("сектор"),
        data.get("отрасль"),
    )

    if dry_run:
        print(f"  {ticker}: черновое обновление ({data['символ_источника']})")
        return True

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  {ticker}: обновлено ({data['символ_источника']})")
    return True


def main():
    setup_stdout()

    args = list(sys.argv[1:])
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")

    tickers, sector, desc = parse_scope_args(args)
    print(f"Обновляю финансовый блок для области: {desc}...")
    files = find_ticker_files(tickers, sector)

    if not files:
        print("Подходящие файлы не найдены.")
        return

    print(f"Найдено файлов: {len(files)}.\n")
    updated = failed = skipped = 0

    for ticker in sorted(files.keys()):
        try:
            if update_file(files[ticker], ticker, dry_run):
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  {ticker}: ошибка ({e})")
            failed += 1
        time.sleep(0.5)

    print(f"\nГотово. Обновлено: {updated} | Пропущено: {skipped} | Ошибок: {failed}")


if __name__ == "__main__":
    main()
