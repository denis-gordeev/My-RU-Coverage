"""
audit_batch.py — Контроль качества отчётов по тикерам.

Проверяет: количество викилинков, общие викилинки, плейсхолдеры, английский текст,
полноту метаданных, глубину разделов.

Использование:
  python scripts/audit_batch.py <номер_пакета> [-v]     Аудит одного пакета
  python scripts/audit_batch.py --all [-v]              Аудит всех завершённых пакетов
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    REPORTS_DIR, TASK_FILE, TICKER_PATTERN,
    get_batch_tickers, setup_stdout, extract_wikilinks,
)

# --- Quality Rules (aligned with CLAUDE.md Golden Rules) ---

MIN_WIKILINKS = 8

GENERIC_WIKILINK_MARKERS = [
    "поставщик", "клиент", "компания", "предприятие", "агент",
    "производитель", "оператор", "разработчик", "сервис", "бренд",
    "дистрибьютор", "ритейлер", "подрядчик", "интегратор",
]

PLACEHOLDER_STRINGS = [
    "Нужно дополнение от исследователя или ИИ",
    "Нужно дополнение от [[AI]]",
    "(待更新)",
    "基於嚴格實名制",
    "Нужно enrichment",
    "Нужно обогащение",
]

REQUIRED_METADATA = [
    r"Сектор:",
    r"Отрасль:",
    r"Рыночная капитализация:",
    r"Стоимость предприятия \(EV\):",
]
REQUIRED_SECTIONS = [
    r"## Описание бизнеса",
    r"## Положение в цепочке поставок",
    r"## Ключевые клиенты и поставщики",
    r"## Финансовый обзор",
]

ENGLISH_INDICATORS = [
    "Business Description", "Inc.", "Ltd.", "manufactures",
    "provides", "is a company", "headquartered", "was founded",
    "specializes in", "engages in", "operates through",
    "was established", "company is", "engaged in the business",
]
def find_generic_wikilinks(wikilinks):
    generic = []
    for wl in wikilinks:
        for marker in GENERIC_WIKILINK_MARKERS:
            if marker in wl:
                generic.append(wl)
                break
    return generic


def check_metadata(content):
    issues = []
    for field in REQUIRED_METADATA:
        if not re.search(field, content):
            issues.append(f"Отсутствует метадата: {field.rstrip(':')}")
        else:
            for line in content.split("\n"):
                if re.search(field, line):
                    after_field = re.split(field, line, maxsplit=1)[1].strip()
                    if not after_field:
                        issues.append(f"Пустая метадата: {field.rstrip(':')}")
                    break
    return issues


def check_sections(content):
    return [s for s in REQUIRED_SECTIONS if not re.search(s, content)]


def check_section_depth(content):
    issues = []
    sc_match = re.search(
        r"## Положение в цепочке поставок\n(.*?)(?=\n## Ключевые клиенты и поставщики|\Z)",
        content,
        re.DOTALL,
    )
    if sc_match:
        sc_lines = [l for l in sc_match.group(1).strip().split("\n") if l.strip()]
        if len(sc_lines) < 3:
            issues.append(f"Слишком короткий блок цепочки поставок ({len(sc_lines)} строк)")

    cs_match = re.search(
        r"## Ключевые клиенты и поставщики\n(.*?)(?=\n## Финансовый обзор|\Z)",
        content,
        re.DOTALL,
    )
    if cs_match:
        cs_lines = [l for l in cs_match.group(1).strip().split("\n") if l.strip()]
        if len(cs_lines) < 4:
            issues.append(f"Слишком короткий блок клиентов и поставщиков ({len(cs_lines)} строк)")

    return issues


def check_english(content):
    for line in content.split("\n")[:20]:
        if "**" in line or ":" in line:
            continue
        for indicator in ENGLISH_INDICATORS:
            if indicator in line:
                return indicator
    return None


def audit_ticker(content):
    """Запускает все проверки качества. Возвращает (чисто, список_замечаний)."""
    issues = []

    if len(content) < 200:
        issues.append("Слишком короткое содержимое (<200 символов)")
        return False, issues

    for ph in PLACEHOLDER_STRINGS:
        if ph in content:
            issues.append(f"Найден плейсхолдер: '{ph}'")

    eng = check_english(content)
    if eng:
        issues.append(f"Обнаружен английский текст: '{eng}'")

    for ms in check_sections(content):
        issues.append(f"Отсутствует раздел: {ms}")

    issues.extend(check_metadata(content))

    wikilinks = extract_wikilinks(content)
    if len(wikilinks) < MIN_WIKILINKS:
        issues.append(f"Недостаточно викалинков: {len(wikilinks)} (минимум {MIN_WIKILINKS})")

    generic = find_generic_wikilinks(wikilinks)
    if generic:
        issues.append(f"Слишком общие викалинки ({len(generic)}): {generic}")

    issues.extend(check_section_depth(content))

    return len(issues) == 0, issues


def find_batch_files(tickers):
    """Находит файлы для списка тикеров."""
    found = {}
    for root, dirs, files in os.walk(REPORTS_DIR):
        for file in files:
            if file.endswith(".md"):
                match = re.match(rf"^({TICKER_PATTERN})", file, re.IGNORECASE)
                if match and match.group(1) in tickers:
                    found[match.group(1)] = os.path.join(root, file)
    return found


def audit_batch(batch_num, verbose=False):
    tickers = get_batch_tickers(batch_num)
    if not tickers:
        return

    print(f"АУДИТ КАЧЕСТВА: проверяю {len(tickers)} тикеров из пакета {batch_num}...")
    print(f"Правила: минимум {MIN_WIKILINKS} викалинков, без общих меток, плейсхолдеров и английского текста")
    print("=" * 60)

    clean, enrichment, quality_fix, missing = [], [], [], []
    found = find_batch_files(tickers)

    for ticker in tickers:
        if ticker not in found:
            missing.append(ticker)
            continue

        try:
            with open(found[ticker], "r", encoding="utf-8") as f:
                content = f.read()

            is_clean, issues = audit_ticker(content)

            if is_clean:
                clean.append(ticker)
                if verbose:
                    wl_count = len(extract_wikilinks(content))
                    print(f"  {ticker}: чисто ({wl_count} викалинков)")
            else:
                has_placeholder = any(ph in content for ph in PLACEHOLDER_STRINGS)
                has_english = check_english(content) is not None
                is_short = len(content) < 200

                if has_placeholder or has_english or is_short:
                    enrichment.append(ticker)
                    cat = "НУЖНО ОБОГАЩЕНИЕ"
                else:
                    quality_fix.append(ticker)
                    cat = "НУЖНА ПРАВКА КАЧЕСТВА"

                if verbose:
                    print(f"  {ticker}: {cat}")
                    for issue in issues:
                        print(f"    - {issue}")

        except Exception as e:
            print(f"Ошибка чтения {found[ticker]}: {e}")
            enrichment.append(ticker)

    print("=" * 60)
    print(f"ЧИСТО ({len(clean)}): {clean}")
    print(f"НУЖНО ОБОГАЩЕНИЕ ({len(enrichment)}): {enrichment}")
    if quality_fix:
        print(f"НУЖНА ПРАВКА КАЧЕСТВА ({len(quality_fix)}): {quality_fix}")
    print(f"ОТСУТСТВУЮТ ({len(missing)}): {missing}")

    total = len(tickers)
    pct = len(clean) / total * 100 if total > 0 else 0
    print(f"\nРезультат: {len(clean)}/{total} ({pct:.0f}%) проходят аудит качества")


def audit_all_completed(verbose=False):
    """Аудирует все пакеты, отмеченные [x] в task.md."""
    try:
        with open(TASK_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Не удалось прочитать task.md: {e}")
        return

    completed = re.findall(r"\[x\]\s*\*\*Batch\s+(\d+)\*\*", content)
    if not completed:
        print("В task.md не найдены завершённые пакеты")
        return

    print(f"Проверяю завершённые пакеты ({len(completed)}): {', '.join(completed)}")
    print("=" * 60)

    total_clean = total_tickers = 0
    all_issues = []

    for batch_num in completed:
        tickers = get_batch_tickers(batch_num)
        if not tickers:
            continue

        found = find_batch_files(tickers)
        batch_issues = []

        for ticker in tickers:
            if ticker not in found:
                continue
            try:
                with open(found[ticker], "r", encoding="utf-8") as f:
                    file_content = f.read()
                is_clean, issues = audit_ticker(file_content)
                total_tickers += 1
                if is_clean:
                    total_clean += 1
                else:
                    batch_issues.append((ticker, issues))
            except Exception:
                pass

        if batch_issues:
            print(f"\nПакет {batch_num}: у {len(batch_issues)} тикеров нужны правки качества")
            if verbose:
                for ticker, issues in batch_issues:
                    print(f"  {ticker}:")
                    for issue in issues:
                        print(f"    - {issue}")
            all_issues.extend(batch_issues)

    print("\n" + "=" * 60)
    pct = total_clean / total_tickers * 100 if total_tickers > 0 else 0
    print(f"ИТОГО: {total_clean}/{total_tickers} ({pct:.0f}%) проходят аудит качества")
    print(f"Всего тикеров с замечаниями по качеству: {len(all_issues)}")


if __name__ == "__main__":
    setup_stdout()

    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/audit_batch.py <номер_пакета> [-v]")
        print("  python scripts/audit_batch.py --all [-v]")
        sys.exit(1)

    verbose = "-v" in sys.argv

    if sys.argv[1] == "--all":
        audit_all_completed(verbose)
    else:
        audit_batch(sys.argv[1], verbose)
