import re
import pandas as pd
from sqlalchemy import text
from app.database import engine

FORBIDDEN = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"]

def sanitize_union(sql: str) -> str:
    if re.search(r"\bUNION\b", sql, re.IGNORECASE):
        return sql
    return sql

def clean_sql(sql: str) -> str:
    """Убирает markdown, BOM, лишние пробелы."""
    sql = re.sub(r"```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", "", sql)
    sql = sql.replace("\ufeff", "").replace("\u200b", "")
    return sql.strip()


def execute_select(sql: str) -> pd.DataFrame:
    sql_clean = clean_sql(sql)

    # 1. Проверка: только SELECT. WITH (CTE) запрещен.
    if re.match(r"^WITH\b", sql_clean, re.IGNORECASE):
        return pd.DataFrame(
            {"Ошибка": ["Использование WITH (CTE) запрещено правилами. Перепиши запрос в один простой SELECT."]})

    if not re.match(r"^SELECT\b", sql_clean, re.IGNORECASE):
        return pd.DataFrame({"Ошибка": [f"Разрешены только SELECT-запросы. Получено: {sql_clean[:100]}..."]})

    # 2. Проверка UNION (запрещен для план-факта)
    if re.search(r"\bUNION\b", sql_clean, re.IGNORECASE):
        return pd.DataFrame({"Ошибка": [
            "SQL содержит UNION. Это запрещено для план-факта. Нужно переписать через LEFT JOIN sales_plan."]})

    # 3. НОВОЕ: Жесткая блокировка агрегации в SQL (SUM, COUNT, GROUP BY и т.д.)
    AGG_WORDS = [r"\bSUM\(", r"\bAVG\(", r"\bCOUNT\(", r"\bMIN\(", r"\bMAX\(", r"\bGROUP\s+BY\b"]
    for pattern in AGG_WORDS:
        if re.search(pattern, sql_clean, re.IGNORECASE):
            return pd.DataFrame({
                "Ошибка": [
                    "Агрегация (SUM/COUNT/AVG/GROUP BY) в SQL запрещена! "
                    "Выгружай сырые детализированные данные (колонки s.amount, p.product_name, o.outlet_name), "
                    "Python (pandas) сам посчитает все итоги."
                ]
            })

    # 4. Проверка запрещённых слов (по границам слов)
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", sql_clean, re.IGNORECASE):
            return pd.DataFrame({"Ошибка": [f"Запрещённое слово в запросе: {word}"]})

    # 5. Выполнение (подключение к БД)
    try:
        with engine.connect() as conn:
            conn.execute(text("SET LOCAL statement_timeout = '15s'"))
            df = pd.read_sql(text(sql_clean), conn)
            return df
    except Exception as e:
        return pd.DataFrame({"Ошибка": [f"Ошибка БД: {e}"]})