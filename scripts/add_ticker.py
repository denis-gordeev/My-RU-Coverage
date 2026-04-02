"""
add_ticker.py — Generate a new ticker report with financials and base structure.

Creates a new .md file under Pilot_Reports/{sector}/ with:
- Title with wikilinked company name
- Metadata (sector, industry, market cap, enterprise value)
- Placeholder sections for enrichment
- Financial tables from yfinance (annual 3yr + quarterly 4Q)

Usage:
  python scripts/add_ticker.py GAZP Газпром                    # Auto-detect sector
  python scripts/add_ticker.py GAZP Газпром --sector Energy    # Specify sector

After generating, use update_enrichment.py to add business descriptions.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    find_ticker_files, REPORTS_DIR, PROJECT_ROOT,
    BUSINESS_SECTION_TITLE, SUPPLY_CHAIN_SECTION_TITLE, CUSTOMERS_SECTION_TITLE,
    FINANCIAL_SECTION_TITLE, ANNUAL_SECTION_TITLE, QUARTERLY_SECTION_TITLE,
)

# Import financials fetcher
from update_financials import fetch_financials, build_financial_section


def generate_report(ticker, name, sector=None, industry=None):
    """Generate a complete report file for a new ticker."""
    # Fetch financial data (also gives us sector/industry if not specified)
    fin_data = fetch_financials(ticker)

    if fin_data:
        if not sector:
            sector = fin_data.get("sector", "Unknown")
        if not industry:
            industry = fin_data.get("industry", "Unknown")
        market_cap = fin_data.get("market_cap", "N/A")
        enterprise_value = fin_data.get("enterprise_value", "N/A")
        unit_label = fin_data.get("unit_label", "млн руб.")
        fin_section = build_financial_section(fin_data)
    else:
        if not sector:
            sector = "Unknown"
        if not industry:
            industry = "Unknown"
        market_cap = "N/A"
        enterprise_value = "N/A"
        unit_label = "млн руб."
        fin_section = (
            f"{FINANCIAL_SECTION_TITLE} (единицы: {unit_label}, маржа указана в %)\n"
            f"{ANNUAL_SECTION_TITLE}\nНет доступных данных.\n\n"
            f"{QUARTERLY_SECTION_TITLE}\nНет доступных данных.\n"
        )

    content = f"""# {ticker} - [[{name}]]

{BUSINESS_SECTION_TITLE}
**Сектор:** {sector}
**Отрасль:** {industry}
**Рыночная капитализация:** {market_cap} {unit_label}
**Стоимость предприятия (EV):** {enterprise_value} {unit_label}

*(Нужно обогащение: заполните описание через `update_enrichment.py`.)*

{SUPPLY_CHAIN_SECTION_TITLE}
*(Нужно обогащение.)*

{CUSTOMERS_SECTION_TITLE}
*(Нужно обогащение.)*

{fin_section}"""

    return content, sector


def sanitize_folder_name(name):
    """Clean up sector name for use as folder name."""
    # Replace characters that are problematic in Windows paths
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]

    if not args or args[0] in {"-h", "--help"}:
        print("Использование:")
        print("  python scripts/add_ticker.py <ticker> <name>")
        print("  python scripts/add_ticker.py <ticker> <name> --sector <sector>")
        return

    # Parse arguments
    ticker = args[0]
    name = args[1] if len(args) > 1 else "Unknown"

    sector = None
    if "--sector" in args:
        idx = args.index("--sector")
        sector = " ".join(args[idx + 1 :])

    # Check if ticker already exists
    existing = find_ticker_files([ticker])
    if existing:
        print(f"Тикер {ticker} уже существует: {existing[ticker]}")
        print("Для обновления используйте update_financials.py или update_enrichment.py.")
        return

    print(f"Создаю карточку для {ticker} ({name})...")
    content, detected_sector = generate_report(ticker, name, sector)

    # Determine output folder
    folder_name = sanitize_folder_name(sector or detected_sector)
    output_dir = os.path.join(REPORTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    # Write file
    filename = f"{ticker}_{name}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Создан файл: {filepath}")
    print(f"Сектор: {folder_name}")
    print("\nДальше: используйте update_enrichment.py, чтобы добавить описание бизнеса, цепочку поставок и контрагентов.")


if __name__ == "__main__":
    main()
