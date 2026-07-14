"""
update_financials.py — Обновление финансовых таблиц в отчётах тикеров.

Загружает последние годовые (3 года) и квартальные (4 кв.) данные из yfinance,
затем заменяет ТОЛЬКО раздел `## Финансовый обзор` в каждом файле отчёта.
Всё содержимое обогащения (описание деятельности, цепочка поставок, контрагенты) сохраняется.

Использование:
  python scripts/update_financials.py                       # Обновить ВСЕ тикеры
  python scripts/update_financials.py SBER                  # Один тикер
  python scripts/update_financials.py SBER GAZP LKOH        # Несколько тикеров
  python scripts/update_financials.py --сектор Энергетика   # Весь сектор
  python scripts/update_financials.py --пробный-запуск SBER # Предпросмотр без записи

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
    найти_файлы_тикеров, разобрать_аргументы_области, настроить_вывод,
    загрузить_данные_мультипликаторов, построить_таблицу_мультипликаторов, обновить_метаданные,
    обновить_классификацию_компании, СУФФИКСЫ_РЫНКА_ПО_УМОЛЧАНИЮ, получить_профиль_рынка,
    ЗАГОЛОВОК_СЕКЦИИ_ФИНАНСОВ, ЗАГОЛОВОК_СЕКЦИИ_ГОДОВЫХ, ЗАГОЛОВОК_СЕКЦИИ_КВАРТАЛЬНЫХ,
    РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ, ПЕРЕОПРЕДЕЛЕНИЯ_ИСТОЧНИКОВ_ТИКЕРОВ,
)

# Финансовые метрики для извлечения
КЛЮЧИ_МЕТРИК = {
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

МЕТКИ_МЕТРИК = {
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


def получить_ряд(df, ключи):
    for key in ключи:
        if key in df.index:
            return df.loc[key]
    return pd.Series(dtype=float)


def вычислить_маржу(числитель, знаменатель):
    if знаменатель.empty or числитель.empty:
        return pd.Series(dtype=float)
    result = (числитель / знаменатель) * 100
    result = result.replace([float("inf"), float("-inf")], float("nan"))
    return result


def вычислить_управленческие_расходы(отчёт_о_прибылях):
    """Получает административные расходы, при отсутствии — вычисляет как управленческие и коммерческие расходы (SGA) − коммерческие расходы."""
    admin = получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["общехозяйственные_расходы"])
    selling = получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["коммерческие_расходы"])
    sga = получить_ряд(отчёт_о_прибылях, ["Selling General And Administration"])

    if admin.empty and not sga.empty and not selling.empty:
        return sga - selling
    elif not admin.empty and not sga.empty:
        derived = sga - selling
        return admin.fillna(derived)
    return admin


def извлечь_метрики(отчёт_о_прибылях, денежный_поток):
    if отчёт_о_прибылях.empty and денежный_поток.empty:
        return pd.DataFrame()

    data = {
        МЕТКИ_МЕТРИК["выручка"]: получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["выручка"]),
        МЕТКИ_МЕТРИК["валовая_прибыль"]: получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["валовая_прибыль"]),
        МЕТКИ_МЕТРИК["валовая_маржа"]: вычислить_маржу(
            получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["валовая_прибыль"]),
            получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["выручка"]),
        ),
        МЕТКИ_МЕТРИК["коммерческие_расходы"]: получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["коммерческие_расходы"]),
        МЕТКИ_МЕТРИК["расходы_ниокр"]: получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["расходы_ниокр"]),
        МЕТКИ_МЕТРИК["общехозяйственные_расходы"]: вычислить_управленческие_расходы(отчёт_о_прибылях),
        МЕТКИ_МЕТРИК["операционная_прибыль"]: получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["операционная_прибыль"]),
        МЕТКИ_МЕТРИК["операционная_маржа"]: вычислить_маржу(
            получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["операционная_прибыль"]),
            получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["выручка"]),
        ),
        МЕТКИ_МЕТРИК["чистая_прибыль"]: получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["чистая_прибыль"]),
        МЕТКИ_МЕТРИК["чистая_маржа"]: вычислить_маржу(
            получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["чистая_прибыль"]),
            получить_ряд(отчёт_о_прибылях, КЛЮЧИ_МЕТРИК["выручка"]),
        ),
        МЕТКИ_МЕТРИК["операционный_поток"]: получить_ряд(денежный_поток, КЛЮЧИ_МЕТРИК["операционный_поток"]),
        МЕТКИ_МЕТРИК["инвестиционный_поток"]: получить_ряд(денежный_поток, КЛЮЧИ_МЕТРИК["инвестиционный_поток"]),
        МЕТКИ_МЕТРИК["финансовый_поток"]: получить_ряд(денежный_поток, КЛЮЧИ_МЕТРИК["финансовый_поток"]),
        МЕТКИ_МЕТРИК["капитальные_затраты"]: получить_ряд(денежный_поток, КЛЮЧИ_МЕТРИК["капитальные_затраты"]),
    }

    # Выводим капитальные затраты (CAPEX) из свободного денежного потока (FCF) при отсутствии: CAPEX = FCF − операционный поток (отрицательный)
    capex = data[МЕТКИ_МЕТРИК["капитальные_затраты"]]
    ocf = data[МЕТКИ_МЕТРИК["операционный_поток"]]
    fcf = получить_ряд(денежный_поток, ["Free Cash Flow"])
    if not capex.empty and not ocf.empty and not fcf.empty:
        derived_capex = fcf - ocf
        data[МЕТКИ_МЕТРИК["капитальные_затраты"]] = capex.fillna(derived_capex)
    elif capex.empty and not ocf.empty and not fcf.empty:
        data[МЕТКИ_МЕТРИК["капитальные_затраты"]] = fcf - ocf

    df = pd.DataFrame(data).T
    # Очищаем заголовки столбцов: убираем временную часть из datetime
    df.columns = [
        col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
        for col in df.columns
    ]
    return df


def локализовать_подписи_метрик(df, суффикс):
    """Устаревшая функция — метрики уже создаются с русскими подписями."""
    return df


def получить_кандидатов_источника(ticker):
    """Возвращает приоритизированный список кандидатов источников финансов для тикера."""
    override = ПЕРЕОПРЕДЕЛЕНИЯ_ИСТОЧНИКОВ_ТИКЕРОВ.get(ticker, {})
    candidates = override.get("кандидаты")
    if candidates:
        return candidates
    return [f"{ticker}{suffix}" for suffix in СУФФИКСЫ_РЫНКА_ПО_УМОЛЧАНИЮ]


def определить_суффикс_рынка(symbol):
    for suffix in СУФФИКСЫ_РЫНКА_ПО_УМОЛЧАНИЮ:
        if symbol.endswith(suffix):
            return suffix
    return ".ME"


def проверить_совпадение_личности(ticker, symbol, info):
    """Отклоняет очевидные совпадения символов, например `T` -> AT&T."""
    override = ПЕРЕОПРЕДЕЛЕНИЯ_ИСТОЧНИКОВ_ТИКЕРОВ.get(ticker, {})
    keywords = override.get("ключевые_слова_идентификации", [])
    if not keywords:
        return True

    haystack = " ".join(
        str(info.get(key, "") or "")
        for key in ("shortName", "longName", "displayName", "symbol")
    ).lower()

    if not haystack.strip():
        return symbol == получить_кандидатов_источника(ticker)[0]

    return any(keyword.lower() in haystack for keyword in keywords)


def подготовить_таблицу_отчёта(df, суффикс, макс_столбцов):
    if df.empty:
        return df

    if МЕТКИ_МЕТРИК["выручка"] in df.index:
        valid_cols = df.columns[df.loc[МЕТКИ_МЕТРИК["выручка"]].notna()]
        df = df[valid_cols]
    else:
        df = df.dropna(axis=1, how="all")

    df = df[sorted(df.columns, reverse=True)]
    non_pct = [row for row in df.index if "%" not in row]
    df.loc[non_pct] = df.loc[non_pct] / 1_000_000
    df = df.iloc[:, :макс_столбцов]
    return локализовать_подписи_метрик(df, суффикс)


def оценить_источник(data):
    годовых_столбцов = 0 if data["годовые"] is None else len(data["годовые"].columns)
    квартальных_столбцов = 0 if data["квартальные"] is None else len(data["квартальные"].columns)
    есть_рыночная_кап = 1 if data.get("рыночная_капитализация") not in (None, "Н/Д") else 0
    есть_сектор = 1 if data.get("сектор") not in (None, "", "Н/Д", "Не определено") else 0
    return (годовых_столбцов + квартальных_столбцов, есть_рыночная_кап, есть_сектор)


def загрузить_финансы(ticker):
    """Загружает финансовые данные с проверкой приоритета источников."""
    override = ПЕРЕОПРЕДЕЛЕНИЯ_ИСТОЧНИКОВ_ТИКЕРОВ.get(ticker, {})
    лучшие_данные = None
    лучший_результат = (-1, -1, -1)

    for symbol in получить_кандидатов_источника(ticker):
        try:
            stock = yf.Ticker(symbol)
            info = stock.info or {}
            if not проверить_совпадение_личности(ticker, symbol, info):
                continue

            suffix = определить_суффикс_рынка(symbol)
            df_annual = подготовить_таблицу_отчёта(
                извлечь_метрики(stock.income_stmt, stock.cashflow), suffix, 3
            )
            df_quarterly = подготовить_таблицу_отчёта(
                извлечь_метрики(stock.quarterly_income_stmt, stock.quarterly_cashflow),
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

            valuation = загрузить_данные_мультипликаторов(info)
            market_profile = получить_профиль_рынка(suffix)
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

            data_score = оценить_источник(data)
            if data_score > лучший_результат:
                лучшие_данные = data
                лучший_результат = data_score
        except Exception:
            continue
    return лучшие_данные


def датафрейм_в_чистый_markdown(df):
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


def построить_финансовую_секцию(data):
    unit_label = data.get("единица_измерения", "млн руб.")
    section = f"{ЗАГОЛОВОК_СЕКЦИИ_ФИНАНСОВ} (единицы: {unit_label}, маржа указана в %)\n"

    v = data.get("оценка", {})
    if v:
        section += построить_таблицу_мультипликаторов(v) + "\n\n"

    section += f"{ЗАГОЛОВОК_СЕКЦИИ_ГОДОВЫХ}\n"
    if data["годовые"] is not None and not data["годовые"].empty:
        section += датафрейм_в_чистый_markdown(data["годовые"]) + "\n\n"
    else:
        section += "Нет доступных данных.\n\n"
    section += f"{ЗАГОЛОВОК_СЕКЦИИ_КВАРТАЛЬНЫХ}\n"
    if data["квартальные"] is not None and not data["квартальные"].empty:
        section += датафрейм_в_чистый_markdown(data["квартальные"]) + "\n"
    else:
        section += "Нет доступных данных.\n"
    return section


def обновить_файл(путь, ticker, пробный_запуск=False):
    with open(путь, "r", encoding="utf-8") as f:
        content = f.read()

    data = загрузить_финансы(ticker)
    if data is None:
        print(f"  {ticker}: пропуск (yfinance не вернул данные)")
        return False

    new_fin = построить_финансовую_секцию(data)

    if re.search(РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ["финансовый_обзор"], content):
        new_content = re.sub(rf"{РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ['финансовый_обзор']}.*", new_fin, content, flags=re.DOTALL)
    else:
        new_content = content.rstrip() + "\n\n" + new_fin

    # Обновляем метаданные
    new_content = обновить_метаданные(
        new_content,
        data.get("рыночная_капитализация"),
        data.get("стоимость_предприятия"),
        data.get("единица_измерения", "млн руб."),
    )
    new_content = обновить_классификацию_компании(
        new_content,
        data.get("сектор"),
        data.get("отрасль"),
    )

    if пробный_запуск:
        print(f"  {ticker}: черновое обновление ({data['символ_источника']})")
        return True

    with open(путь, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  {ticker}: обновлено ({data['символ_источника']})")
    return True


def main():
    настроить_вывод()

    args = list(sys.argv[1:])
    пробный_запуск = "--пробный-запуск" in args
    if пробный_запуск:
        args.remove("--пробный-запуск")

    tickers, sector, desc = разобрать_аргументы_области(args)
    print(f"Обновляю финансовый блок для области: {desc}...")
    files = найти_файлы_тикеров(tickers, sector)

    if not files:
        print("Подходящие файлы не найдены.")
        return

    print(f"Найдено файлов: {len(files)}.\n")
    updated = failed = skipped = 0

    for ticker in sorted(files.keys()):
        try:
            if обновить_файл(files[ticker], ticker, пробный_запуск):
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
