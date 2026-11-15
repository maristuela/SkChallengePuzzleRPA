# app/calculations.py
import re
import pandas as pd

ALLOWED_NAMES = {"pd", "df", "abs", "min", "max", "round"}

def apply_calculation(df: pd.DataFrame, user_query: str, llm_client) -> tuple[pd.DataFrame, str | None]:
    """
    Просит LLM написать pandas-код, потом безопасно применяет.
    Возвращает (new_df, error_msg).
    """
    from app.prompts import get_calc_prompt

    code = llm_client.generate_calc_code(user_query, list(df.columns))
    if not code or code.startswith("ERROR"):
        return df, f"Не смог сгенерировать код: {code}"

    # Убираем markdown
    code = re.sub(r"```python\s*", "", code, flags=re.IGNORECASE)
    code = re.sub(r"```", "", code).strip()

    # Простейшая защита
    forbidden = ["import ", "open(", "os.", "sys.", "eval(", "exec(", "__", "subprocess"]
    for f in forbidden:
        if f in code:
            return df, f"Запрещённая конструкция: {f}"

    # Ограниченный exec с доступом только к df и pd
    local_vars = {"df": df.copy(), "pd": pd}
    try:
        exec(compile(code, "<calc>", "exec"), {"__builtins__": {}}, local_vars)
        new_df = local_vars["df"]
        if not isinstance(new_df, pd.DataFrame):
            return df, "Код не вернул DataFrame"
        # Ограничение: не более 50 колонок
        if new_df.shape[1] - df.shape[1] > 5:
            return df, "Слишком много новых колонок"
        return new_df, None
    except Exception as e:
        return df, f"Ошибка выполнения: {e}"


def detect_intent(user_query: str) -> str:
    """Быстрая эвристика: это вычисление, сохранение или запрос данных?"""
    q = user_query.lower()
    if any(w in q for w in ["сохрани", "сохранить", "save"]):
        return "save"
    if any(w in q for w in ["покажи мои", "список дашбордов", "мои дашборды"]):
        return "list_dashboards"
    if any(w in q for w in ["добавь", "посчитай", "пересчитай", "вычисли", "рассчитай"]):
        return "calc"
    if any(w in q for w in ["перестрой", "измени график", "отсортируй"]):
        return "rebuild_chart"
    return "query"