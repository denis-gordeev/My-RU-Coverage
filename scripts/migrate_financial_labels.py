"""
migrate_financial_labels.py — Миграция английских названий строк в финансовых таблицах.

Заменяет английские метрики (Revenue, Gross Profit и т.д.) на русские
в существующих финансовых таблицах отчётов.
"""

import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import REPORTS_DIR, PROJECT_ROOT, setup_stdout

# Маппинг английских финансовых метрик на русские
FINANCIAL_LABELS = {
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
}


def migrate_financial_labels(filepath):
    """Переводит финансовые метрики в одном файле. Возвращает True, если были изменения."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Находим строки таблиц вида: | Revenue                 | ...
    # Заменяем только в первых 20 символах после |
    for eng, rus in FINANCIAL_LABELS.items():
        # Pattern: pipe, optional spaces, English label, then whitespace until next pipe
        pattern = rf"(\|\s*){re.escape(eng)}(\s+\|)"
        replacement = rf"\g<1>{rus}\g<2>"
        content = re.sub(pattern, replacement, content)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def main():
    setup_stdout()
    print("Миграция названий финансовых метрик на русский язык...")

    migrated = 0
    skipped = 0

    for fp in glob.glob(os.path.join(REPORTS_DIR, "**", "*.md"), recursive=True):
        # Пропускаем legacy
        if "Pilot_Reports_LEGACY" in fp:
            continue
        if migrate_financial_labels(fp):
            migrated += 1
            print(f"  Обновлён: {os.path.basename(fp)}")
        else:
            skipped += 1

    print(f"\nФайлы: обновлено {migrated}, без изменений {skipped}")
    print("Миграция завершена.")


if __name__ == "__main__":
    main()
