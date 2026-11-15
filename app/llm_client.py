import json
import re

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from gigachat.context import session_id_cvar
from app.config import GIGACHAT_CREDENTIALS
from app.prompts import SYSTEM_PROMPT, get_viz_user_prompt, VIZ_SYSTEM_PROMPT, CLARIFY_SYSTEM_PROMPT, \
    INSIGHTS_SYSTEM_PROMPT


class LLMClient:
    def __init__(self):
        self.client = GigaChat(
            credentials=GIGACHAT_CREDENTIALS,
            model="GigaChat-2",
            scope="GIGACHAT_API_B2B",
            verify_ssl_certs=False,
            timeout=30,
        )

    def generate_sql(self, user_query: str, session_id: str = "bi-chatbot-session") -> str:
        """
        Отправляет system-промпт (тяжелый, кэшируется) и user-вопрос (легкий).
        Session ID обеспечивает попадание в кэш GigaChat.
        """
        # Устанавливаем ID сессии для кэширования
        token = session_id_cvar.set(session_id)

        try:
            payload = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                    Messages(role=MessagesRole.USER, content=user_query),
                ],
                temperature=0.0,
                max_tokens=500,
            )
            response = self.client.chat(payload)
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"ERROR: {e}"
        finally:
            # Сбрасываем контекст сессии
            session_id_cvar.reset(token)

    def fix_sql(self, user_query: str, bad_sql: str, error_msg: str) -> str:
        """Просит LLM исправить SQL с учётом ошибки БД."""
        fix_prompt = (
            f"Пользователь спросил: «{user_query}»\n\n"
            f"Ты сгенерировал SQL:\n{bad_sql}\n\n"
            f"База данных вернула ошибку:\n{error_msg}\n\n"
            f"=== ЖЕСТКИЕ ПРАВИЛА ИСПРАВЛЕНИЯ ===\n"
            f"1. ПОЛНОСТЬЮ УДАЛИ конструкцию WITH (CTE) из запроса! Пиши только один простой SELECT.\n"
            f"2. ПОЛНОСТЬЮ УДАЛИ UNION, если он есть!\n"
            f"3. Проверь связи (JOIN):\n"
            f"   - Точки (outlets) НЕ ИМЕЮТ client_id. Клиенты (clients) присоединяются ТОЛЬКО через таблицу sales: JOIN clients c ON s.client_id = c.client_id\n"
            f"   - Регионы присоединяются через точки: JOIN regions r ON o.region_id = r.region_id\n"
            f"   - План присоединяется через LEFT JOIN sales_plan pl ON s.outlet_id = pl.outlet_id AND s.product_id = pl.product_id\n"
            f"4. Без GROUP BY, без SUM/AVG. Агрегация будет в pandas.\n"
            f"5. Если ошибка в датах, используй ::date (например, DATE_TRUNC('month', s.sale_date::date)).\n"
            f"6. Верни ТОЛЬКО исправленный SQL, без пояснений и без markdown."
        )
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                Messages(role=MessagesRole.USER, content=fix_prompt),
            ],
            temperature=0.0,
            max_tokens=500,
        )
        response = self.client.chat(payload)
        return response.choices[0].message.content.strip()

    def get_chart_config(self, user_query: str, columns_info: str) -> dict:
        import json
        import re  # Убедись, что re импортирован

        user_prompt = get_viz_user_prompt(columns_info, user_query)
        token = session_id_cvar.set("viz-session-v1")

        try:
            payload = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=VIZ_SYSTEM_PROMPT),
                    Messages(role=MessagesRole.USER, content=user_prompt),
                ],
                temperature=0.1,
                max_tokens=1000,
            )
            response = self.client.chat(payload)
            raw = response.choices[0].message.content.strip()

            # --- ОЧИСТКА ОТ МУСОРА ---
            # 1. Убираем markdown-обертки
            raw = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"```", "", raw).strip()

            # 2. Если LLM добавила текст, ищем только от первой { до последней }
            start_idx = raw.find("{")
            end_idx = raw.rfind("}")
            if start_idx != -1 and end_idx != -1:
                raw = raw[start_idx:end_idx + 1]

            return json.loads(raw)

        except json.JSONDecodeError as e:
            # ОБЯЗАТЕЛЬНО выведи raw в консоль, чтобы мы увидели, что именно вернула LLM
            print(f"❌ Ошибка парсинга JSON: {e}\nСырой ответ LLM: {raw}")
            return None
        except Exception as e:
            print(f"❌ Ошибка LLM: {e}")
            return None
        finally:
            session_id_cvar.reset(token)

    def generate_calc_code(self, user_query: str, columns: list[str]) -> str:
        """Просит LLM написать pandas-код для нового вычисления."""
        from app.prompts import get_calc_prompt
        user_prompt = get_calc_prompt(user_query, columns)

        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content="Ты — pandas-программист. Возвращай только код."),
                Messages(role=MessagesRole.USER, content=user_prompt),
            ],
            temperature=0.0,
            max_tokens=300,
        )
        try:
            response = self.client.chat(payload)
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"ERROR: {e}"

    def get_insights(self, df_summary: str) -> str:
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=INSIGHTS_SYSTEM_PROMPT),
                Messages(role=MessagesRole.USER, content=df_summary),
            ],
            temperature=0.3,
            max_tokens=400,
        )
        try:
            return self.client.chat(payload).choices[0].message.content.strip()
        except Exception:
            return ""

    def clarify_query(self, user_query: str) -> str:
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=CLARIFY_SYSTEM_PROMPT),

                Messages(role=MessagesRole.USER, content=user_query),
            ],
            temperature=0.0,
            max_tokens=100,
        )
        try:
            return self.client.chat(payload).choices[0].message.content.strip()
        except Exception:
            return "OK"

llm_client = LLMClient()