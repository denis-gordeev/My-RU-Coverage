"""
update_financials.py — Обновление финансовых таблиц в отчётах тикеров.

Загружает последние годовые (3 года) и квартальные (4 кв.) данные из yfinance,
затем заменяет ТОЛЬКО раздел `## Финансовый обзор` в каждом файле отчёта.
Весь контент обогащения (описание бизнеса, цепочка поставок, контрагенты) сохраняется.

Использование:
  python scripts/update_financials.py                  # Обновить ВСЕ тикеры
  python scripts/update_financials.py SBER             # Один тикер
  python scripts/update_financials.py SBER GAZP LKOH   # Несколько тикеров
  python scripts/update_financials.py --batch 101      # Все тикеры из пакета
  python scripts/update_financials.py --sector Energy  # Весь сектор
  python scripts/update_financials.py --dry-run SBER   # Предпросмотр без записи

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

# Financial metrics to extract
METRICS_KEYS = {
    "revenue": ["Total Revenue"],
    "gross_profit": ["Gross Profit"],
    "selling_exp": ["Selling And Marketing Expense"],
    "rd_exp": ["Research And Development"],
    "admin_exp": ["General And Administrative Expense"],
    "operating_income": ["Operating Income"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "ocf": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "icf": ["Investing Cash Flow", "Total Cashflows From Investing Activities"],
    "fcf": ["Financing Cash Flow", "Total Cash From Financing Activities"],
    "capex": ["Capital Expenditure", "Capital Expenditures"],
}

METRIC_ROW_LABELS = {
    ".ME": {
        "Выручка": "Выручка",
        "Валовая прибыль": "Валовая прибыль",
        "Валовая маржа (%)": "Валовая маржа (%)",
        "Коммерческие расходы": "Коммерческие расходы",
        "Расходы на R&D": "Расходы на R&D",
        "Общехозяйственные расходы": "Общехозяйственные расходы",
        "Операционная прибыль": "Операционная прибыль",
        "Операционная маржа (%)": "Операционная маржа (%)",
        "Чистая прибыль": "Чистая прибыль",
        "Чистая маржа (%)": "Чистая маржа (%)",
        "Операционный денежный поток": "Операционный денежный поток",
        "Инвестиционный денежный поток": "Инвестиционный денежный поток",
        "Финансовый денежный поток": "Финансовый денежный поток",
        "Капитальные затраты": "Капитальные затраты",
        # Legacy English keys for backward compatibility with DataFrames
        "Revenue": "Выручка",
        "Gross Profit": "Валовая прибыль",
        "Gross Margin (%)": "Валовая маржа (%)",
        "Selling & Marketing Exp": "Коммерческие расходы",
        "R&D Exp": "Расходы на R&D",
        "General & Admin Exp": "Общехозяйственные расходы",
        "Operating Income": "Операционная прибыль",
        "Operating Margin (%)": "Операционная маржа (%)",
        "Net Income": "Чистая прибыль",
        "Net Margin (%)": "Чистая маржа (%)",
        "Op Cash Flow": "Операционный денежный поток",
        "Investing Cash Flow": "Инвестиционный денежный поток",
        "Financing Cash Flow": "Финансовый денежный поток",
        "CAPEX": "Капитальные затраты",
    },
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
    """Получает административные расходы, при отсутствии — вычисляет как SGA - Selling."""
    admin = get_series(income_stmt, METRICS_KEYS["admin_exp"])
    selling = get_series(income_stmt, METRICS_KEYS["selling_exp"])
    sga = get_series(income_stmt, ["Selling General And Administration"])

    if admin.empty and not sga.empty and not selling.empty:
        # Derive G&A = SGA - Selling
        return sga - selling
    elif not admin.empty and not sga.empty:
        # Fill NaN gaps in G&A from SGA - Selling
        derived = sga - selling
        return admin.fillna(derived)
    return admin


def extract_metrics(income_stmt, cashflow):
    if income_stmt.empty and cashflow.empty:
        return pd.DataFrame()

    data = {
        "Revenue": get_series(income_stmt, METRICS_KEYS["revenue"]),
        "Gross Profit": get_series(income_stmt, METRICS_KEYS["gross_profit"]),
        "Gross Margin (%)": calc_margin(
            get_series(income_stmt, METRICS_KEYS["gross_profit"]),
            get_series(income_stmt, METRICS_KEYS["revenue"]),
        ),
        "Selling & Marketing Exp": get_series(income_stmt, METRICS_KEYS["selling_exp"]),
        "R&D Exp": get_series(income_stmt, METRICS_KEYS["rd_exp"]),
        "General & Admin Exp": calc_admin_exp(income_stmt),
        "Operating Income": get_series(income_stmt, METRICS_KEYS["operating_income"]),
        "Operating Margin (%)": calc_margin(
            get_series(income_stmt, METRICS_KEYS["operating_income"]),
            get_series(income_stmt, METRICS_KEYS["revenue"]),
        ),
        "Net Income": get_series(income_stmt, METRICS_KEYS["net_income"]),
        "Net Margin (%)": calc_margin(
            get_series(income_stmt, METRICS_KEYS["net_income"]),
            get_series(income_stmt, METRICS_KEYS["revenue"]),
        ),
        "Op Cash Flow": get_series(cashflow, METRICS_KEYS["ocf"]),
        "Investing Cash Flow": get_series(cashflow, METRICS_KEYS["icf"]),
        "Financing Cash Flow": get_series(cashflow, METRICS_KEYS["fcf"]),
        "CAPEX": get_series(cashflow, METRICS_KEYS["capex"]),
    }

    # Derive CAPEX from FCF when CAPEX is missing: CAPEX = FCF - OCF (negative)
    capex = data["CAPEX"]
    ocf = data["Op Cash Flow"]
    fcf = get_series(cashflow, ["Free Cash Flow"])
    if not capex.empty and not ocf.empty and not fcf.empty:
        derived_capex = fcf - ocf
        data["CAPEX"] = capex.fillna(derived_capex)
    elif capex.empty and not ocf.empty and not fcf.empty:
        data["CAPEX"] = fcf - ocf

    df = pd.DataFrame(data).T
    # Clean column headers: remove time component from datetime
    df.columns = [
        col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        for col in df.columns
    ]
    return df


def localize_metric_labels(df, suffix):
    """Переименовывает строки финансовых метрик в язык отчёта для конкретного рынка."""
    labels = METRIC_ROW_LABELS.get(suffix, METRIC_ROW_LABELS[".ME"])
    return df.rename(index=labels)


def get_source_candidates(ticker):
    """Возвращает приоритизированный список кандидатов источников финансов для тикера."""
    override = TICKER_SOURCE_OVERRIDES.get(ticker, {})
    candidates = override.get("candidates")
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
    keywords = override.get("identity_keywords", [])
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

    if "Revenue" in df.index:
        valid_cols = df.columns[df.loc["Revenue"].notna()]
        df = df[valid_cols]
    else:
        df = df.dropna(axis=1, how="all")

    df = df[sorted(df.columns, reverse=True)]
    non_pct = [row for row in df.index if "%" not in row]
    df.loc[non_pct] = df.loc[non_pct] / 1_000_000
    df = df.iloc[:, :max_columns]
    return localize_metric_labels(df, suffix)


def score_source(data):
    annual_cols = 0 if data["annual"] is None else len(data["annual"].columns)
    quarterly_cols = 0 if data["quarterly"] is None else len(data["quarterly"].columns)
    has_market_cap = 1 if data.get("market_cap") not in (None, "Н/Д") else 0
    has_sector = 1 if data.get("sector") not in (None, "", "Н/Д", "Unknown") else 0
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
                "annual": df_annual,
                "quarterly": df_quarterly,
                "valuation": valuation,
                "market_cap": market_cap,
                "enterprise_value": enterprise_value,
                "sector": info.get("sector") or override.get("sector", "N/A"),
                "industry": info.get("industry") or override.get("industry", "N/A"),
                "suffix": suffix,
                "unit_label": market_profile["unit_label"],
                "source_symbol": symbol,
            }

            if data["annual"].empty and data["quarterly"].empty and market_cap == "N/A" and enterprise_value == "N/A":
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
    # Format numbers first while dtype is still float
    md = df.to_markdown(floatfmt=".2f")
    # Replace nan strings that to_markdown generates for NaN values
    md = md.replace(" nan ", " - ")
    md = md.replace(" nan|", " -|")
    md = md.replace("|nan ", "|- ")
    # Also handle edge cases with padding
    md = re.sub(r'\bnan\b', '-', md)
    return md


def build_financial_section(data):
    unit_label = data.get("unit_label", "млн руб.")
    section = f"{FINANCIAL_SECTION_TITLE} (единицы: {unit_label}, маржа указана в %)\n"

    # Valuation snapshot
    v = data.get("valuation", {})
    if v:
        section += build_valuation_table(v) + "\n\n"

    section += f"{ANNUAL_SECTION_TITLE}\n"
    if data["annual"] is not None and not data["annual"].empty:
        section += df_to_clean_markdown(data["annual"]) + "\n\n"
    else:
        section += "Нет доступных данных.\n\n"
    section += f"{QUARTERLY_SECTION_TITLE}\n"
    if data["quarterly"] is not None and not data["quarterly"].empty:
        section += df_to_clean_markdown(data["quarterly"]) + "\n"
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

    if re.search(SECTION_HEADER_REGEX["financial"], content):
        new_content = re.sub(rf"{SECTION_HEADER_REGEX['financial']}.*", new_fin, content, flags=re.DOTALL)
    else:
        new_content = content.rstrip() + "\n\n" + new_fin

    # Update metadata
    new_content = update_metadata(
        new_content,
        data.get("market_cap"),
        data.get("enterprise_value"),
        data.get("unit_label", "млн руб."),
    )
    new_content = update_company_classification(
        new_content,
        data.get("sector"),
        data.get("industry"),
    )

    if dry_run:
        print(f"  {ticker}: черновое обновление ({data['source_symbol']})")
        return True

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  {ticker}: обновлено ({data['source_symbol']})")
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
