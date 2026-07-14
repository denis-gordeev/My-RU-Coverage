"""
update_valuation.py — Обновление ТОЛЬКО оценочных мультипликаторов в отчётах тикеров.

Гораздо быстрее, чем update_financials.py, так как загружает только stock.info (без финансовых отчётов).
Обновляет: P/E (за 12 мес.), Прогнозный P/E, P/S, P/B, EV/EBITDA, цену акции и даты периодов.
Сохраняет всё остальное содержимое, включая финансовые таблицы.

Использование:
  python scripts/update_valuation.py                        # ВСЕ тикеры
  python scripts/update_valuation.py SBER                   # Один тикер
  python scripts/update_valuation.py SBER GAZP LKOH         # Несколько тикеров
  python scripts/update_valuation.py --сектор Энергетика    # По сектору
  python scripts/update_valuation.py --пробный-запуск SBER  # Предпросмотр без записи
"""

import os
import re
import sys
import time

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    найти_файлы_тикеров, разобрать_аргументы_области, настроить_вывод,
    загрузить_данные_мультипликаторов, построить_таблицу_мультипликаторов, обновить_метаданные,
    СУФФИКСЫ_РЫНКА_ПО_УМОЛЧАНИЮ, получить_профиль_рынка,
    РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ,
)


def загрузить_оценку(ticker):
    """Загружает только оценочные мультипликаторы. Пробует суффиксы в приоритетном порядке."""
    for suffix in СУФФИКСЫ_РЫНКА_ПО_УМОЛЧАНИЮ:
        try:
            stock = yf.Ticker(f"{ticker}{suffix}")
            info = stock.info
            if not info or not info.get("currentPrice"):
                continue

            valuation = загрузить_данные_мультипликаторов(info)

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
            market_profile = получить_профиль_рынка(suffix)
            return {
                "оценка": valuation,
                "рыночная_капитализация": market_cap,
                "стоимость_предприятия": enterprise_value,
                "суффикс": suffix,
                "единица_измерения": market_profile["единица"],
            }
        except Exception:
            continue
    return None


def обновить_файл(путь, ticker, пробный_запуск=False):
    """Обновляет только раздел оценки в файле тикера."""
    with open(путь, "r", encoding="utf-8") as f:
        content = f.read()

    data = загрузить_оценку(ticker)
    if data is None:
        print(f"  {ticker}: пропуск (нет данных)")
        return False

    new_table = построить_таблицу_мультипликаторов(data["оценка"])

    if re.search(РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ["оценочные_мультипликаторы"], content):
        content = re.sub(
            rf"{РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ['оценочные_мультипликаторы']}.*?(?=\n{РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ['годовые_показатели']})",
            new_table + "\n",
            content,
            flags=re.DOTALL,
        )
    elif re.search(РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ["финансовый_обзор"], content):
        annual_match = re.search(РЕГЕКСЫ_ЗАГОЛОВКОВ_СЕКЦИЙ["годовые_показатели"], content)
        if annual_match:
            content = content[: annual_match.start()] + new_table + "\n\n" + content[annual_match.start() :]

    content = обновить_метаданные(
        content,
        data.get("рыночная_капитализация"),
        data.get("стоимость_предприятия"),
        data.get("единица_измерения", "млн руб."),
    )

    if пробный_запуск:
        print(f"  {ticker}: черновое обновление ({data['суффикс']})")
        return True

    with open(путь, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  {ticker}: обновлено ({data['суффикс']})")
    return True


def main():
    настроить_вывод()

    args = list(sys.argv[1:])
    пробный_запуск = "--пробный-запуск" in args
    if пробный_запуск:
        args.remove("--пробный-запуск")

    tickers, sector, desc = разобрать_аргументы_области(args)
    print(f"Обновляю оценочные мультипликаторы для области: {desc}...")
    files = найти_файлы_тикеров(tickers, sector)

    if not files:
        print("Подходящие файлы не найдены.")
        return

    print(f"Найдено файлов: {len(files)}.\n")
    обновлено = с_ошибкой = пропущено = 0

    for ticker in sorted(files.keys()):
        try:
            if обновить_файл(files[ticker], ticker, пробный_запуск):
                обновлено += 1
            else:
                пропущено += 1
        except Exception as e:
            print(f"  {ticker}: ошибка ({e})")
            с_ошибкой += 1
        time.sleep(0.3)

    print(f"\nГотово. Обновлено: {обновлено} | Пропущено: {пропущено} | Ошибок: {с_ошибкой}")


if __name__ == "__main__":
    main()
