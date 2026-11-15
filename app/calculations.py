import re
import pandas as pd

ALLOWED_NAMES = {"pd", "df", "abs", "min", "max", "round"}


def sanitize_code(code: str) -> str:
    if not code:
        return ""

    # 1. Убираем ЛЮБЫЕ обратные кавычки (одинарные и тройные)
    code = code.replace("```python", "").replace("```", "").replace("`", "")

    # 2. Убираем markdown-обёртки (если остались)
    code = re.sub(r"```[a-zA-Z]*\s*", "", code)

    # 3. Убираем русские кавычки
    code = code.replace("«", "'").replace("»", "'")
    code = code.replace("“", "'").replace("”", "'")
    code = code.replace("„", "'")
    code = code.replace("‘", "'").replace("’", "'")

    # 4. Убираем BOM и невидимые символы
    code = code.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    code = code.replace("\xa0", " ")

    # 5. Заменяем pd.NA на None
    code = code.replace("pd.NA", "None")

    # 6. Убираем пустые строки и комментарии в начале
    code = code.strip()
    if code.startswith("'") and code.endswith("'"):
        code = code[1:-1]
    if code.startswith('"') and code.endswith('"'):
        code = code[1:-1]

    lines = [line for line in code.split("\n") if line.strip() and not line.strip().startswith("#")]

    return "\n".join(lines).strip()


def apply_calculation(df: pd.DataFrame, user_query: str, llm_client) -> tuple[pd.DataFrame, str | None]:
    """
    Просит LLM написать pandas-код, потом безопасно применяет.
    Возвращает (new_df, error_msg).
    """
    code = llm_client.generate_calc_code(user_query, list(df.columns))
    if not code or code.startswith("ERROR"):
        return df, f"Не смог сгенерировать код: {code}"

    # Очищаем код от мусора
    code = sanitize_code(code)

    # Если ИИ вернул pass — значит не понял
    if code.strip() == "pass" or not code.strip():
        return df, "Не удалось понять запрос. Попробуйте сформулировать иначе (например: 'Убери колонку Регион' или 'Добавь отклонение')."

    # Защита от опасных конструкций
    forbidden = ["import ", "open(", "os.", "sys.", "eval(", "__", "subprocess", "shutil"]
    for f in forbidden:
        if f in code:
            return df, f"Запрещённая конструкция в коде: {f}"

    # Ограниченный exec с доступом только к df и pd
    local_vars = {"df": df.copy(), "pd": pd}
    try:
        exec(compile(code, "<calc>", "exec"), {"__builtins__": {}}, local_vars)
        new_df = local_vars.get("df", df)

        if not isinstance(new_df, pd.DataFrame):
            return df, "Код не вернул DataFrame"

        # Ограничение: не более 50 колонок
        if new_df.shape[1] - df.shape[1] > 5:
            return df, "Слишком много новых колонок"

        return new_df, None
    except SyntaxError as e:
        return df, f"Синтаксическая ошибка в коде от ИИ: {e}\nКод был:\n{code[:200]}"
    except Exception as e:
        return df, f"Ошибка выполнения: {e}\nКод был:\n{code[:200]}"


def detect_intent(user_query: str) -> str:
    """Быстрая эвристика: это вычисление, сохранение или запрос данных?"""
    q = user_query.lower()
    if any(w in q for w in ["сохрани", "сохранить", "save"]):
        return "save"
    if any(w in q for w in ["покажи мои", "список дашбордов", "мои дашборды"]):
        return "list_dashboards"
    if any(w in q for w in
           ["добавь", "посчитай", "пересчитай", "вычисли", "рассчитай", "убери", "удали", "отфильтруй", "отсортируй"]):
        return "calc"
    if any(w in q for w in ["перестрой", "измени график", "отсортируй"]):
        return "rebuild_chart"
    return "query"