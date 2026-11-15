import json
import os
from datetime import datetime
import pandas as pd
import numpy as np

STORAGE_DIR = "saved_dashboards"
os.makedirs(STORAGE_DIR, exist_ok=True)


def save_dashboard(name: str, query: str, df: pd.DataFrame, config: dict, kpi: dict):
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip().replace(" ", "_")
    if not safe_name:
        safe_name = f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # --- ЛОГИКА ЗАЩИТЫ ОТ ПЕРЕЗАПИСИ ---
    base = os.path.join(STORAGE_DIR, safe_name)
    counter = 1
    # Пока существует файл с таким именем, добавляем цифру в конец
    while os.path.exists(f"{base}.json"):
        safe_name_with_idx = f"{safe_name}_{counter}"
        base = os.path.join(STORAGE_DIR, safe_name_with_idx)
        counter += 1

    # Обновляем safe_name для возврата в app.py
    if counter > 1:
        safe_name = safe_name_with_idx
    # -----------------------------------

    tmp_base = base + "_tmp"  # Временное имя

    # 1. Сохраняем CSV
    df.to_csv(f"{tmp_base}.csv", index=False, encoding="utf-8-sig")

    meta = {
        "name": safe_name,
        "query": query,
        "config": config,
        "kpi": kpi,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    def clean_for_json(obj):
        if isinstance(obj, dict):
            return {k: clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_for_json(v) for v in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, float):
            if pd.isna(obj) or np.isinf(obj):
                return None
            return obj
        elif isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        return obj

    clean_meta = clean_for_json(meta)

    # 2. Сохраняем JSON во временный файл
    with open(f"{tmp_base}.json", "w", encoding="utf-8") as f:
        json.dump(clean_meta, f, ensure_ascii=False, indent=2)

    # 3. Атомарно переименовываем (только если запись прошла успешно)
    os.replace(f"{tmp_base}.json", f"{base}.json")
    os.replace(f"{tmp_base}.csv", f"{base}.csv")

    return safe_name


def list_dashboards() -> list[dict]:
    items = []
    print(f"🔍 Ищу дашборды в: {os.path.abspath(STORAGE_DIR)}")

    if not os.path.exists(STORAGE_DIR):
        return items

    for fname in os.listdir(STORAGE_DIR):
        if fname.endswith(".json") and "_tmp" not in fname:
            try:
                with open(os.path.join(STORAGE_DIR, fname), encoding="utf-8") as f:
                    meta = json.load(f)
                items.append(meta)
                print(f"  ✅ Найден: {fname}")
            except Exception as e:
                print(f"  ❌ Ошибка чтения {fname}: {e}")

    return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)


def load_dashboard(name: str):
    base = os.path.join(STORAGE_DIR, name)
    with open(f"{base}.json", encoding="utf-8") as f:
        meta = json.load(f)
    df = pd.read_csv(f"{base}.csv")
    return meta, df


def delete_dashboard(name: str) -> bool:
    base = os.path.join(STORAGE_DIR, name)
    ok = True
    for ext in (".json", ".csv"):
        p = f"{base}{ext}"
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                ok = False
    return ok