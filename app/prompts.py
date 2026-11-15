# # app/prompts.py
#
# from sqlalchemy import inspect
# from app.database import engine
#
# # 1. Функция автосбора схемы
# def build_schema_from_db() -> str:
#     inspector = inspect(engine)
#     lines = ["Таблицы (PostgreSQL):"]
#     for table_name in inspector.get_table_names():
#         cols = [c["name"] for c in inspector.get_columns(table_name)]
#         lines.append(f"{table_name}({', '.join(cols)})")
#     return "\n".join(lines)
#
# # 2. Переменные
# DYNAMIC_SCHEMA = build_schema_from_db()
#
# RULES_SHORT = """
# ПРАВИЛА:
# 1. Только SELECT. Никаких INSERT/UPDATE/DELETE/DROP.
# 2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать WITH (CTE). Пиши всё в одном SELECT.
# 3. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать UNION / UNION ALL. План и факт должны быть колонками в одной строке.
# 4. Без SUM/AVG/COUNT/MIN/MAX и без GROUP BY — агрегация будет в pandas.
# 5. В WHERE — только фильтр по дате (например, s.sale_date::date >= '2023-01-01').
# 6. ВАЖНО: колонки sale_date и plan_month могут храниться как текст. Всегда используй явное приведение: DATE_TRUNC('month', s.sale_date::date) и pl.plan_month::date.
# 7. Выгружай нужные разрезы (r.region_name AS "Регион", o.outlet_name AS "Точка", p.product_name AS "Продукт", c.segment AS "Сегмент", DATE_TRUNC('month', s.sale_date::date) AS "Месяц") и метрики (s.amount AS "Факт", s.quantity AS "Количество", pl.plan_amount AS "План", pl.plan_qty AS "План_шт").
# 8. Связи таблиц (ОЧЕНЬ ВАЖНО):
#    sales (s)
#    JOIN outlets (o) ON s.outlet_id = o.outlet_id
#    JOIN products (p) ON s.product_id = p.product_id
#    JOIN clients (c) ON s.client_id = c.client_id
#    JOIN regions (r) ON o.region_id = r.region_id
#    LEFT JOIN sales_plan (pl) ON s.outlet_id = pl.outlet_id AND s.product_id = pl.product_id AND DATE_TRUNC('month', s.sale_date::date) = pl.plan_month::date
# 9. Русские алиасы в двойных кавычках: AS "Регион", AS "Факт", AS "План".
# 10. Верни только SQL. Без markdown, без ```sql, без пояснений.
# """
#
# EXAMPLES_SHORT = """
# ПРИМЕР 1. «План-факт по регионам и точкам за год»
# SELECT
#     r.region_name AS "Регион",
#     o.outlet_name AS "Торговая точка",
#     DATE_TRUNC('month', s.sale_date::date) AS "Месяц",
#     s.amount AS "Факт",
#     s.quantity AS "Количество",
#     pl.plan_amount AS "План",
#     pl.plan_qty AS "План_шт"
# FROM sales s
# JOIN outlets o ON s.outlet_id = o.outlet_id
# JOIN products p ON s.product_id = p.product_id
# JOIN clients c ON s.client_id = c.client_id
# JOIN regions r ON o.region_id = r.region_id
# LEFT JOIN sales_plan pl
#     ON s.outlet_id = pl.outlet_id
#     AND s.product_id = pl.product_id
#     AND DATE_TRUNC('month', s.sale_date::date) = pl.plan_month::date
# WHERE s.sale_date::date >= DATE_TRUNC('year', CURRENT_DATE);
# """
#
# # 3. Сборка SYSTEM_PROMPT (ПОСЛЕ всех переменных!)
# SYSTEM_PROMPT = f"Ты — Text-to-SQL ассистент для PostgreSQL.\n\n{DYNAMIC_SCHEMA}\n\n{RULES_SHORT}\n\n{EXAMPLES_SHORT}"
#
#
# def get_sql_prompt(user_query: str) -> str:
#     return user_query
#
# def get_calc_prompt(user_query: str, columns: list[str]) -> str:
#     cols_list = ", ".join(columns)
#     return (
#         f"Есть pandas DataFrame `df` с колонками: {cols_list}.\n"
#         f"Пользователь просит: «{user_query}».\n\n"
#         f"Напиши ТОЛЬКО Python-код (pandas), который добавляет новую колонку или изменяет существующие.\n"
#         f"Правила:\n"
#         f"- Верни только код, без markdown, без пояснений, без комментариев.\n"
#         f"- Названия новых колонок — на русском, в кавычках.\n"
#         f"- Защита от деления на ноль: используй .replace(0, pd.NA).\n"
#         f"- Пример: df['Отклонение'] = df['Факт'] - df['План']\n"
#         f"- Пример: df['Выполнение, %'] = (df['Факт'] / df['План'].replace(0, pd.NA)) * 100\n\n"
#         f"Код:"
#     )
#
# # --- ПРОМПТЫ ДЛЯ ВИЗУАЛИЗАЦИИ ---
#
# VIZ_SYSTEM_PROMPT = """
# Ты — экспертный модуль визуализации данных BI-системы.
# Твоя задача — анализировать структуру таблицы данных и запрос пользователя,
# а затем возвращать конфигурацию для дашборда в формате JSON.
#
# ПРАВИЛА:
# 1. Верни ТОЛЬКО валидный JSON. Никакого текста до или после. Без markdown-оберток (никаких ```json).
# 2. Используй СТРОГО те названия колонок, которые переданы в user-сообщении.
# 3. Типы графиков:
#    - "bar" (столбцы): для сравнения категорий или план-факт по периодам.
#    - "line" (линия): для динамики во времени (если есть дата/месяц).
#    - "pie" (круговая): для структуры/долей (обязательно нужны names и values).
# 4. В поле "x" ставь колонку с датами (если есть), иначе — категориальную колонку.
# 5. В поле "y" ставь числовые метрики.
#    - Если нужно показать ОДНУ метрику, пиши строку: "y": "Факт".
#    - Если нужно показать ПЛАН и ФАКТ вместе на одном графике, пиши список: "y": ["План", "Факт"].
# 6. Если для какого-то типа графика не хватает колонок — просто не добавляй его в список "charts".
# 7. "group_by" — это колонка, по которой РАСКРАШИВАЮТСЯ серии (marker_color в Plotly).
#    Значения этой колонки должны быть КАТЕГОРИЯМИ (Регион, Продукт, Категория, Сегмент),
#    а НЕ датами и НЕ числовыми метриками. Plotly не умеет раскрашивать по дате.
#    Если в запросе план-факт по месяцам — оставь group_by = null и передай
#    "y": ["План", "Факт"] — Plotly сам раскрасит серии по именам.
#    Если нужен третий разрез (например, регион поверх план-факт) — тогда
#    "group_by": "Регион", а "y": ["План", "Факт"].
#
# ФОРМАТ ОТВЕТА:
# {
#   "kpi": {
#     "main_metric": "Колонка_с_фактом",
#     "plan_metric": "Колонка_с_планом_или_null",
#     "is_fact": true
#   },
#   "charts": [
#     {
#       "type": "bar",
#       "title": "Русское название",
#       "x": "Колонка_оси_X",
#       "y": "Колонка_оси_Y",
#       "group_by": "Колонка_цвета_или_null"
#     },
#     {
#       "type": "pie",
#       "title": "Структура",
#       "names": "Колонка_категорий",
#       "values": "Колонка_чисел"
#     },
#     {
#       "type": "line",
#       "title": "Динамика",
#       "x": "Колонка_дат",
#       "y": "Колонка_чисел",
#       "group_by": null
#     }
#   ]
# }
# """
#
# def get_viz_user_prompt(columns_info: str, user_query: str) -> str:
#     """Легкий user-промпт: только данные и запрос."""
#     return f"""
# Запрос пользователя: «{user_query}»
#
# Доступные колонки в таблице данных (название и тип):
# {columns_info}
#
# Сгенерируй JSON-конфигурацию дашборда.
# """
#
# INSIGHTS_SYSTEM_PROMPT = """
# Ты — бизнес-аналитик. По данным таблицы напиши 3-5 коротких инсайтов на русском.
# Формат: маркированный список. Без воды. Указывай конкретные цифры и регионы/точки.
# Пример: "• План выполнен на 87% (−162.5 млн ₽).
# • Лидер — Центральный регион (105%).
# • Отставание — Урал (62%), скидки выше среднего."
# """
#
# CLARIFY_SYSTEM_PROMPT = """
# Ты — BI-ассистент. Пользователь задал аналитический вопрос.
# Если в вопросе НЕ хватает периода, разреза или метрики — задай ОДИН уточняющий вопрос.
# Если всё понятно — верни слово "OK" (без пояснений).
# Отвечай кратко, по-русски.
# """


# app/prompts.py

from sqlalchemy import inspect
from app.database import engine

# 1. Функция автосбора схемы
def build_schema_from_db() -> str:
    inspector = inspect(engine)
    lines = ["Таблицы (PostgreSQL):"]
    for table_name in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        lines.append(f"{table_name}({', '.join(cols)})")
    return "\n".join(lines)

# 2. Переменные
DYNAMIC_SCHEMA = build_schema_from_db()

RULES_SHORT = """
КРИТИЧЕСКИЕ ПРАВИЛА (НАРУШАТЬ ЗАПРЕЩЕНО):
1. Только SELECT. Никаких INSERT/UPDATE/DELETE/DROP.
2. ЗАПРЕЩЕНО использовать WITH (CTE) и UNION / UNION ALL.
3. ЗАПРЕЩЕНО использовать SUM, AVG, COUNT, MAX, MIN, CASE WHEN и GROUP BY. 
   Вся агрегация и вычисления делаются на стороне Python (pandas).
4. ВСЕГДА выгружай МАКСИМАЛЬНО ДЕТАЛИЗИРОВАННУЮ (плоскую) ТАБЛИЦУ. 
   Даже если пользователь просит "ТОП точек" или "Структуру продуктов" — просто выгрузи ВСЕ строки с названиями точек, продуктов и суммами. Python сам посчитает ТОП и структуру.
5. ВСЕГДА выгружай следующие разрезы, если они есть в базе:
   DATE_TRUNC('month', s.sale_date::date) AS "Месяц"
   r.region_name AS "Регион"
   o.outlet_name AS "Точка"
   p.product_name AS "Продукт"
   p.category AS "Категория"
   c.segment AS "Сегмент"
6. ВСЕГДА выгружай следующие метрики:
   s.amount AS "Факт"
   s.quantity AS "Количество"
   pl.plan_amount AS "План"
   pl.plan_qty AS "План_шт"
7. Если в запросе есть условие по времени (например, "за последний квартал"), добавь его в WHERE. Если периода нет — выгружай данные за последний год (WHERE s.sale_date::date >= CURRENT_DATE - INTERVAL '1 year').
8. ВАЖНО: колонки sale_date и plan_month могут храниться как текст. Всегда используй явное приведение: s.sale_date::date и pl.plan_month::date.
9. Связи таблиц (ОБЯЗАТЕЛЬНО):
   FROM sales s
   JOIN outlets o ON s.outlet_id = o.outlet_id
   JOIN products p ON s.product_id = p.product_id
   JOIN clients c ON s.client_id = c.client_id
   JOIN regions r ON o.region_id = r.region_id
   LEFT JOIN sales_plan pl ON s.outlet_id = pl.outlet_id AND s.product_id = pl.product_id AND DATE_TRUNC('month', s.sale_date::date) = pl.plan_month::date
10. Русские алиасы в двойных кавычках: AS "Регион", AS "Факт", AS "План".
11. Верни только SQL. Без markdown, без ```sql, без пояснений.
"""

EXAMPLES_SHORT = """
ПРИМЕР 1. «Собери дашборд по продажам: динамика, структура, ТОП точек, выполнение плана»
ПРАВИЛЬНЫЙ ОТВЕТ (выгружаем максимум деталей, без SUM и GROUP BY):
SELECT 
    DATE_TRUNC('month', s.sale_date::date) AS "Месяц",
    r.region_name AS "Регион",
    o.outlet_name AS "Точка",
    p.product_name AS "Продукт",
    p.category AS "Категория",
    c.segment AS "Сегмент",
    s.amount AS "Факт",
    s.quantity AS "Количество",
    pl.plan_amount AS "План",
    pl.plan_qty AS "План_шт"
FROM sales s
JOIN outlets o ON s.outlet_id = o.outlet_id
JOIN products p ON s.product_id = p.product_id
JOIN clients c ON s.client_id = c.client_id
JOIN regions r ON o.region_id = r.region_id
LEFT JOIN sales_plan pl 
    ON s.outlet_id = pl.outlet_id 
    AND s.product_id = pl.product_id 
    AND DATE_TRUNC('month', s.sale_date::date) = pl.plan_month::date
WHERE s.sale_date::date >= CURRENT_DATE - INTERVAL '1 year'
ORDER BY s.sale_date::date, r.region_name;
"""

# 3. Сборка SYSTEM_PROMPT
SYSTEM_PROMPT = f"Ты — Text-to-SQL ассистент для PostgreSQL.\n\n{DYNAMIC_SCHEMA}\n\n{RULES_SHORT}\n\n{EXAMPLES_SHORT}"


def get_sql_prompt(user_query: str) -> str:
    return user_query

def get_calc_prompt(user_query: str, columns: list[str]) -> str:
    cols_list = ", ".join(columns)
    return (
        f"Есть pandas DataFrame `df` с колонками: {cols_list}.\n"
        f"Пользователь просит: «{user_query}».\n\n"
        f"Напиши ТОЛЬКО Python-код (pandas), который добавляет новую колонку или изменяет существующие.\n"
        f"Правила:\n"
        f"- Верни только код, без markdown, без пояснений, без комментариев.\n"
        f"- Названия новых колонок — на русском, в кавычках.\n"
        f"- Защита от деления на ноль: используй .replace(0, pd.NA).\n"
        f"- Пример: df['Отклонение'] = df['Факт'] - df['План']\n"
        f"- Пример: df['Выполнение, %'] = (df['Факт'] / df['План'].replace(0, pd.NA)) * 100\n\n"
        f"Код:"
    )

# --- ПРОМПТЫ ДЛЯ ВИЗУАЛИЗАЦИИ ---

VIZ_SYSTEM_PROMPT = """
Ты — экспертный модуль визуализации данных BI-системы.
Твоя задача — анализировать структуру таблицы данных и запрос пользователя, 
а затем возвращать конфигурацию для дашборда в формате JSON.

ПРАВИЛА:
1. Верни ТОЛЬКО валидный JSON. Никакого текста до или после. Без markdown-оберток.
2. Используй СТРОГО те названия колонок, которые переданы в user-сообщении. Не придумывай новые!
3. Типы графиков:
   - "bar" (столбцы): для сравнения категорий или план-факт по периодам.
   - "line" (линия): для динамики во времени (если есть дата/месяц).
   - "pie" (круговая): для структуры/долей (обязательно нужны names и values).
4. В поле "x" ставь колонку с датами (если есть), иначе — категориальную колонку.
5. В поле "y" ставь числовые метрики.
   - Если нужно показать ОДНУ метрику, пиши строку: "y": "Факт".
   - Если нужно показать ПЛАН и ФАКТ вместе на одном графике, пиши список строк: "y": ["План", "Факт"].
6. Если для какого-то типа графика не хватает колонок — просто не добавляй его в список "charts".
7. "group_by" — это колонка, по которой РАСКРАШИВАЮТСЯ серии (marker_color в Plotly). 
   Значения этой колонки должны быть КАТЕГОРИЯМИ (Регион, Продукт, Категория, Сегмент), 
   а НЕ датами и НЕ числовыми метриками.
8. КРИТИЧЕСКИ ВАЖНО (ТИПЫ ДАННЫХ):
   - Поля "x", "group_by", "names", "values" должны быть СТРОКАМИ (например, "Регион"). 
   - Если строишь круговую диаграмму (pie), "names" — это колонка категорий (строка), "values" — колонка чисел (строка).
9. Если данных для графика нет, лучше верни меньше графиков, чем сломай дашборд.

ФОРМАТ ОТВЕТА:
{
  "kpi": {
    "main_metric": "Колонка_с_фактом",
    "plan_metric": "Колонка_с_планом_или_null",
    "is_fact": true
  },
  "charts": [
    {
      "type": "bar",
      "title": "Русское название",
      "x": "Колонка_оси_X",
      "y": "Колонка_оси_Y",
      "group_by": "Колонка_цвета_или_null"
    },
    {
      "type": "pie",
      "title": "Структура",
      "names": "Колонка_категорий",
      "values": "Колонка_чисел"
    },
    {
      "type": "line",
      "title": "Динамика",
      "x": "Колонка_дат",
      "y": "Колонка_чисел",
      "group_by": null
    }
  ]
}
"""

def get_viz_user_prompt(columns_info: str, user_query: str) -> str:
    """Легкий user-промпт: только данные и запрос."""
    return f"""
Запрос пользователя: «{user_query}»

Доступные колонки в таблице данных (название и тип):
{columns_info}

Сгенерируй JSON-конфигурацию дашборда.
"""

INSIGHTS_SYSTEM_PROMPT = """
Ты — бизнес-аналитик. По данным таблицы напиши 3-5 коротких инсайтов на русском.
Формат: маркированный список. Без воды. Указывай конкретные цифры и регионы/точки.
Пример: "• План выполнен на 87% (−162.5 млн ₽).
• Лидер — Центральный регион (105%).
• Отставание — Урал (62%), скидки выше среднего."
"""

CLARIFY_SYSTEM_PROMPT = """
Ты — BI-ассистент. Пользователь задал аналитический вопрос.
Если в вопросе НЕ хватает периода, разреза или метрики — задай ОДИН уточняющий вопрос.
Если всё понятно — верни слово "OK" (без пояснений).
Отвечай кратко, по-русски.
"""