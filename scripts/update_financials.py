"""
update_financials.py — Refresh financial tables in ticker reports.

Fetches latest annual (3yr) and quarterly (4Q) data from yfinance,
then replaces ONLY the `## Финансовый обзор` section in each report file.
All enrichment content (business description, supply chain, counterparties) is preserved.

Usage:
  python scripts/update_financials.py                  # Update ALL tickers
  python scripts/update_financials.py SBER             # Single ticker
  python scripts/update_financials.py SBER GAZP LKOH   # Multiple tickers
  python scripts/update_financials.py --batch 101      # All tickers in a batch
  python scripts/update_financials.py --sector Energy  # Entire sector
  python scripts/update_financials.py --dry-run SBER   # Preview without writing

Units depend on the exchange suffix: `.ME` -> млн руб., `.TW/.TWO` -> млн тайв. долл.
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
    DEFAULT_MARKET_SUFFIXES, get_market_profile,
    FINANCIAL_SECTION_TITLE, ANNUAL_SECTION_TITLE, QUARTERLY_SECTION_TITLE,
    SECTION_HEADER_REGEX,
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
    "default": {
        "Revenue": "Revenue",
        "Gross Profit": "Gross Profit",
        "Gross Margin (%)": "Gross Margin (%)",
        "Selling & Marketing Exp": "Selling & Marketing Exp",
        "R&D Exp": "R&D Exp",
        "General & Admin Exp": "General & Admin Exp",
        "Operating Income": "Operating Income",
        "Operating Margin (%)": "Operating Margin (%)",
        "Net Income": "Net Income",
        "Net Margin (%)": "Net Margin (%)",
        "Op Cash Flow": "Op Cash Flow",
        "Investing Cash Flow": "Investing Cash Flow",
        "Financing Cash Flow": "Financing Cash Flow",
        "CAPEX": "CAPEX",
    },
    ".ME": {
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
    """Get G&A expense, falling back to SGA - Selling if G&A is missing."""
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
    """Rename financial metric rows for market-specific report language."""
    labels = METRIC_ROW_LABELS.get(suffix, METRIC_ROW_LABELS["default"])
    return df.rename(index=labels)


def fetch_financials(ticker):
    """Fetch financial data. Tries local suffixes in configured priority order."""
    for suffix in DEFAULT_MARKET_SUFFIXES:
        try:
            stock = yf.Ticker(f"{ticker}{suffix}")
            income = stock.income_stmt
            if income is None or income.empty:
                continue

            df_annual = extract_metrics(stock.income_stmt, stock.cashflow)
            if not df_annual.empty:
                if "Revenue" in df_annual.index:
                    valid_cols = df_annual.columns[df_annual.loc["Revenue"].notna()]
                    df_annual = df_annual[valid_cols]
                else:
                    df_annual = df_annual.dropna(axis=1, how="all")
                # Sort newest-first, take latest 3 years
                df_annual = df_annual[sorted(df_annual.columns, reverse=True)]
                non_pct = [r for r in df_annual.index if "%" not in r]
                df_annual.loc[non_pct] = df_annual.loc[non_pct] / 1_000_000
                df_annual = df_annual.iloc[:, :3]
                df_annual = localize_metric_labels(df_annual, suffix)

            df_quarterly = extract_metrics(
                stock.quarterly_income_stmt, stock.quarterly_cashflow
            )
            if not df_quarterly.empty:
                # Drop quarters where Revenue is NaN (unreported)
                if "Revenue" in df_quarterly.index:
                    valid_cols = df_quarterly.columns[df_quarterly.loc["Revenue"].notna()]
                    df_quarterly = df_quarterly[valid_cols]
                else:
                    df_quarterly = df_quarterly.dropna(axis=1, how="all")
                # Sort newest-first, take latest 4 quarters
                df_quarterly = df_quarterly[sorted(df_quarterly.columns, reverse=True)]
                non_pct = [r for r in df_quarterly.index if "%" not in r]
                df_quarterly.loc[non_pct] = df_quarterly.loc[non_pct] / 1_000_000
                df_quarterly = df_quarterly.iloc[:, :4]
                df_quarterly = localize_metric_labels(df_quarterly, suffix)

            info = stock.info
            market_cap = (
                f"{info['marketCap'] / 1_000_000:,.0f}"
                if info.get("marketCap")
                else None
            )
            enterprise_value = (
                f"{info['enterpriseValue'] / 1_000_000:,.0f}"
                if info.get("enterpriseValue")
                else None
            )

            valuation = fetch_valuation_data(info)
            market_profile = get_market_profile(suffix)
            return {
                "annual": df_annual,
                "quarterly": df_quarterly,
                "valuation": valuation,
                "market_cap": market_cap,
                "enterprise_value": enterprise_value,
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "suffix": suffix,
                "unit_label": market_profile["unit_label"],
            }
        except Exception:
            continue
    return None


def df_to_clean_markdown(df):
    """Format DataFrame to markdown with .2f precision, then replace NaN with -."""
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
        print(f"  {ticker}: SKIP (no data from yfinance)")
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

    if dry_run:
        print(f"  {ticker}: WOULD UPDATE ({data['suffix']})")
        return True

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  {ticker}: UPDATED ({data['suffix']})")
    return True


def main():
    setup_stdout()

    args = list(sys.argv[1:])
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")

    tickers, sector, desc = parse_scope_args(args)
    print(f"Updating financials for {desc}...")
    files = find_ticker_files(tickers, sector)

    if not files:
        print("No matching files found.")
        return

    print(f"Found {len(files)} files.\n")
    updated = failed = skipped = 0

    for ticker in sorted(files.keys()):
        try:
            if update_file(files[ticker], ticker, dry_run):
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  {ticker}: ERROR ({e})")
            failed += 1
        time.sleep(0.5)

    print(f"\nDone. Updated: {updated} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    main()
