"""Legacy-утилита организации тайваньских отчётов по папкам.

Сохраняется как исторический скрипт и не является частью текущего российского workflow.
"""

import os
import shutil

def organize_reports():
    base_dir = 'f:/My TW Coverage/Pilot_Reports'
    
    if not os.path.exists(base_dir):
        print(f"[LEGACY] Каталог не найден: {base_dir}")
        return

    files = [f for f in os.listdir(base_dir) if f.endswith('.md')]
    print(f"[LEGACY] Найдено отчётов для раскладки: {len(files)}.")
    
    count = 0
    errors = 0

    for filename in files:
        filepath = os.path.join(base_dir, filename)
        industry = "Uncategorized"
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines:
                    # Look for line starting with **產業:**
                    if line.strip().startswith("**產業:**"):
                        # Extract value after colon
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            industry = parts[1].strip()
                        break
            
            # Sanitize industry name for folder use
            safe_industry = industry.replace("/", "_").replace("\\", "_").replace(":", "").replace("*", "")
            
            if safe_industry == "N/A" or not safe_industry:
                safe_industry = "Uncategorized"

            # Create Industry Directory
            industry_dir = os.path.join(base_dir, safe_industry)
            if not os.path.exists(industry_dir):
                os.makedirs(industry_dir)
            
            # Move File
            if not os.path.exists(os.path.join(industry_dir, filename)):
                 shutil.move(filepath, os.path.join(industry_dir, filename))
                 count += 1
                 if count % 100 == 0:
                     print(f"[LEGACY] Разложено файлов: {count}...")
            else:
                print(f"[LEGACY] Пропускаю {filename}: уже существует в {safe_industry}")

        except Exception as e:
            print(f"[LEGACY] Ошибка обработки {filename}: {e}")
            errors += 1

    print("[LEGACY] Раскладка завершена.")
    print(f"[LEGACY] Перемещено: {count}")
    print(f"[LEGACY] Ошибок: {errors}")

if __name__ == "__main__":
    organize_reports()
