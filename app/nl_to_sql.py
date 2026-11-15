from app.llm_client import llm_client


def generate_sql(user_query: str) -> str:
    # session_id можно сделать динамическим (например, по ID пользователя),
    # но для одного чат-бота достаточно константы.
    raw = llm_client.generate_sql(user_query, session_id="bi-chatbot-v1")

    if raw.startswith("ERROR"):
        return raw

    # Очистка от markdown (на всякий случай)
    import re
    clean = re.sub(r"```sql\s*", "", raw)
    clean = re.sub(r"```", "", clean).strip()

    if not clean.upper().startswith("SELECT"):
        return "ERROR: Сгенерированный запрос не является SELECT."

    return clean