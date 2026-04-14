"""
migrate_sectors_industries.py — Миграция всех секторов/отраслей в отчётах на русский язык.

Запускается один раз для обновления всех существующих файлов.
"""

import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    REPORTS_DIR, PROJECT_ROOT, setup_stdout,
    SECTOR_TRANSLATION, INDUSTRY_TRANSLATION,
    translate_sector, translate_industry,
)


def migrate_file(filepath):
    """Переводит Сектор и Отрасль в одном файле. Возвращает True, если были изменения."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Перевод **Сектор:**
    def replace_sector(match):
        prefix = match.group(1)  # "**Сектор:** "
        old_value = match.group(2).strip()
        new_value = translate_sector(old_value)
        return f"{prefix}{new_value}"

    content = re.sub(
        r"(\*\*Сектор:\*\* )(.+)",
        replace_sector,
        content,
    )

    # Перевод **Отрасль:**
    def replace_industry(match):
        prefix = match.group(1)  # "**Отрасль:** "
        old_value = match.group(2).strip()
        new_value = translate_industry(old_value)
        return f"{prefix}{new_value}"

    content = re.sub(
        r"(\*\*Отрасль:\*\* )(.+)",
        replace_industry,
        content,
    )

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


def rename_folders():
    """Переименовывает папки секторов из английских названий в русские."""
    # Маппинг папок: старое -> новое
    folder_mapping = {}
    for eng, rus in SECTOR_TRANSLATION.items():
        folder_mapping[eng] = rus

    # Также обратный маппинг для industry-папок
    # Собираем уникальные имена папок
    existing_folders = set()
    for entry in os.listdir(REPORTS_DIR):
        full_path = os.path.join(REPORTS_DIR, entry)
        if os.path.isdir(full_path):
            existing_folders.add(entry)

    renamed = 0
    for folder_name in sorted(existing_folders):
        if folder_name in folder_mapping:
            new_name = folder_mapping[folder_name]
            old_path = os.path.join(REPORTS_DIR, folder_name)
            new_path = os.path.join(REPORTS_DIR, new_name)
            if old_path != new_path and os.path.exists(old_path):
                print(f"  Переименование: {folder_name} -> {new_name}")
                os.rename(old_path, new_path)
                renamed += 1

    return renamed


def main():
    setup_stdout()
    print("Миграция секторов/отраслей на русский язык...")

    # Шаг 1: Обновляем содержимое файлов
    migrated = 0
    skipped = 0

    for fp in glob.glob(os.path.join(REPORTS_DIR, "**", "*.md"), recursive=True):
        # Пропускаем legacy
        if "Pilot_Reports_LEGACY" in fp:
            continue
        if migrate_file(fp):
            migrated += 1
            print(f"  Обновлён: {os.path.basename(fp)}")
        else:
            skipped += 1

    print(f"\nФайлы: обновлено {migrated}, без изменений {skipped}")

    # Шаг 2: Переименовываем папки
    print("\nПереименование папок секторов...")
    folders_renamed = rename_folders()
    print(f"Папки: переименовано {folders_renamed}")

    print("\nМиграция завершена.")


if __name__ == "__main__":
    main()
