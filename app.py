# import streamlit as st
# from sqlalchemy import func
# from app.database import SessionLocal
# from app.models import Sale, Region
# from app.llm_client import llm_client
# from app.db_utils import execute_select
# from app.charts import calculate_kpi_from_config, build_dashboard_from_config
# import hashlib
#
# # --- Настройка страницы ---
# st.set_page_config(page_title="BI Чат-бот", page_icon="🤖", layout="wide")
# st.title("🤖 BI Чат-бот с GigaChat")
#
#
# # --- Проверка БД ---
# @st.cache_resource
# def check_db_connection():
#     db = SessionLocal()
#     try:
#         count = db.query(func.count(Sale.sale_id)).scalar()
#         regions_count = db.query(func.count(Region.region_id)).scalar()
#         return True, f"✅ БД подключена. Продаж: {count}, Регионов: {regions_count}"
#     except Exception as e:
#         return False, f"❌ Ошибка БД: {e}"
#     finally:
#         db.close()
#
#
# db_status, db_message = check_db_connection()
#
# # --- БОКОВАЯ ПАНЕЛЬ (Сохраненные дашборды) ---
# with st.sidebar:
#     st.header("📂 Мои дашборды")
#     from app.storage import list_dashboards, load_dashboard, delete_dashboard
#
#     items = list_dashboards()
#     if not items:
#         st.write("Пока нет сохранённых дашбордов.")
#     else:
#         for it in items:
#             uniq = hashlib.md5(it["name"].encode()).hexdigest()[:6]   # ← НОВОЕ
#             col_a, col_b = st.columns([4, 1])
#             if col_a.button(
#                 f"📄 {it['name']}",
#                 key=f"sb_open_{uniq}",                                # ← было f"sb_open_{it['name']}"
#                 use_container_width=True,
#             ):
#                 meta, df_restored = load_dashboard(it["name"])
#                 from app.charts import build_dashboard_from_config
#                 fig_restored = build_dashboard_from_config(
#                     df_restored, meta["config"], title=meta["name"]
#                 )
#                 st.session_state.messages.append({
#                     "role": "assistant",
#                     "content": f"📂 Открыт дашборд **{meta['name']}**\n\n_Запрос: {meta['query']}_",
#                     "table": df_restored,
#                     "chart": fig_restored,
#                     "kpi": meta["kpi"],
#                 })
#                 st.rerun()
#             if col_b.button("🗑", key=f"sb_del_{uniq}"):               # ← было f"sb_del_{it['name']}"
#                 delete_dashboard(it["name"])
#                 st.rerun()
#
# # --- Инициализация истории ---
# if "messages" not in st.session_state:
#     st.session_state.messages = [{
#         "role": "assistant",
#         "content": f"Здравствуйте! Я BI-бот.\n\n{db_message}\n\nСпросите что-нибудь, например: «Покажи план-факт по регионам»."
#     }]
#
# # --- ОТРИСОВКА ИСТОРИИ ---
# for msg in st.session_state.messages:
#     with st.chat_message(msg["role"]):
#         st.markdown(msg["content"])
#
#         if "table" in msg and msg["table"] is not None:
#             st.dataframe(msg["table"], use_container_width=True)
#
#         if "kpi" in msg and msg["kpi"]:
#             kpi_cols = st.columns(len(msg["kpi"]) - (1 if "is_positive" in msg["kpi"] else 0))
#             col_idx = 0
#             for k, v in msg["kpi"].items():
#                 if k == "is_positive": continue
#                 kpi_cols[col_idx].metric(label=k, value=v)
#                 col_idx += 1
#
#         if "chart" in msg and msg["chart"] is not None:
#             if not isinstance(msg["chart"], str):
#                 st.plotly_chart(msg["chart"], use_container_width=True)
#             else:
#                 st.info(f"ℹ️ {msg['chart']}")
#
# # --- ПОЛЕ ВВОДА ---
# if prompt := st.chat_input("Введите запрос..."):
#     st.session_state.messages.append({"role": "user", "content": prompt})
#     with st.chat_message("user"):
#         st.markdown(prompt)
#
#     with st.chat_message("assistant"):
#         from app.calculations import detect_intent, apply_calculation
#         from app.storage import save_dashboard, list_dashboards, load_dashboard, delete_dashboard
#
#         intent = detect_intent(prompt)
#
#         # ============ 1. СПИСОК ДАШБОРДОВ ============
#         if intent == "list_dashboards":
#             items = list_dashboards()
#             if not items:
#                 st.info("Пока нет сохранённых дашбордов.")
#                 st.session_state.messages.append({"role": "assistant", "content": "Пока нет сохранённых дашбордов."})
#             else:
#                 st.write("### 📂 Мои дашборды")
#                 for it in items:
#                     cols = st.columns([3, 2, 1, 1])
#                     cols[0].markdown(f"**{it['name']}**\n\n_{it['query'][:80]}_")
#                     cols[1].caption(f"обновлён: {it['updated_at'][:16].replace('T', ' ')}")
#                     if cols[2].button("Открыть", key=f"open_{it['name']}"):
#                         meta, df_restored = load_dashboard(it["name"])
#                         from app.charts import build_dashboard_from_config, calculate_kpi_from_config
#                         fig_restored = build_dashboard_from_config(df_restored, meta["config"], title=meta["name"])
#                         st.session_state.messages.append({
#                             "role": "assistant",
#                             "content": f"📂 Открыт дашборд **{meta['name']}**\n\n_Запрос: {meta['query']}_",
#                             "table": df_restored,
#                             "chart": fig_restored,
#                             "kpi": meta["kpi"],
#                         })
#                         st.rerun()
#                     if cols[3].button("🗑", key=f"del_{it['name']}"):
#                         delete_dashboard(it["name"])
#                         st.rerun()
#                 st.session_state.messages.append({"role": "assistant", "content": "Список дашбордов показан выше."})
#             st.stop()
#
#         # ============ 2. ВЫЧИСЛЕНИЕ (диалог с данными) ============
#         if intent == "calc" and st.session_state.messages:
#             # Берём последнюю таблицу
#             last_table = None
#             last_idx = None
#             for i in range(len(st.session_state.messages) - 1, -1, -1):
#                 m = st.session_state.messages[i]
#                 if m.get("table") is not None:
#                     last_table = m["table"]
#                     last_idx = i
#                     break
#
#             if last_table is None:
#                 msg = "Сначала постройте дашборд, потом добавляйте вычисления."
#                 st.warning(msg)
#                 st.session_state.messages.append({"role": "assistant", "content": msg})
#             else:
#                 with st.spinner("Применяю вычисление..."):
#                     new_df, err = apply_calculation(last_table, prompt, llm_client)
#
#                 if err:
#                     st.error(err)
#                     st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {err}"})
#                 else:
#                     st.success(f"✅ Добавлено колонок: {new_df.shape[1] - last_table.shape[1]}")
#                     # Перестраиваем конфиг (KPI/графики) через LLM
#                     columns_info = "\n".join([f"- {c} (тип: {new_df[c].dtype})" for c in new_df.columns])
#                     last_query = st.session_state.messages[last_idx - 1]["content"] if last_idx > 0 else prompt
#                     with st.spinner("Обновляю визуализацию..."):
#                         viz_config = llm_client.get_chart_config(last_query, columns_info)
#
#                     from app.charts import build_dashboard_from_config, calculate_kpi_from_config
#                     kpi_data = calculate_kpi_from_config(new_df, viz_config.get("kpi", {}) if viz_config else {})
#                     fig = build_dashboard_from_config(new_df, viz_config or {}, title="Дашборд") if viz_config else "Не удалось перестроить."
#
#                     st.dataframe(new_df, use_container_width=True)
#                     if not isinstance(fig, str):
#                         st.plotly_chart(fig, use_container_width=True)
#
#                     st.session_state.messages.append({
#                         "role": "assistant",
#                         "content": f"✅ Выполнено: _{prompt}_\n\nВ таблице теперь {new_df.shape[1]} колонок.",
#                         "table": new_df,
#                         "chart": fig,
#                         "kpi": kpi_data,
#                     })
#             st.stop()
#
#         # ============ 3. ОБЫЧНЫЙ ЗАПРОС ДАННЫХ ============
#         with st.spinner("GigaChat генерирует SQL..."):
#             sql = llm_client.generate_sql(prompt)
#
#         if sql.startswith("ERROR"):
#             st.error(sql)
#             st.session_state.messages.append({"role": "assistant", "content": sql})
#         else:
#             from app.db_utils import execute_select
#             with st.expander("Показать SQL-запрос"):
#                 st.code(sql, language="sql")
#
#             df = execute_select(sql)
#             if "Ошибка" in df.columns:
#                 error_text = df["Ошибка"][0]
#                 st.warning(f"⚠️ Ошибка БД. Пробую исправить...")
#                 fixed_sql = llm_client.fix_sql(prompt, sql, error_text)
#                 df = execute_select(fixed_sql)
#                 if "Ошибка" in df.columns:
#                     st.error(f"❌ {df['Ошибка'][0]}")
#                     st.stop()
#
#             if df.empty:
#                 st.info("ℹ️ Данных не найдено.")
#                 st.session_state.messages.append({"role": "assistant", "content": "Данных не найдено."})
#             else:
#                 st.success(f"✅ Строк: {len(df)}")
#                 # LLM проектирует визуализацию
#                 columns_info = "\n".join([f"- {c} (тип: {df[c].dtype})" for c in df.columns])
#                 with st.spinner("ИИ проектирует дашборд..."):
#                     viz_config = llm_client.get_chart_config(prompt, columns_info)
#
#                 from app.charts import build_dashboard_from_config, calculate_kpi_from_config
#                 kpi_data = calculate_kpi_from_config(df, viz_config.get("kpi", {}) if viz_config else {})
#                 fig = build_dashboard_from_config(df, viz_config or {}, title=f"Дашборд: {prompt[:30]}...") if viz_config else "Не удалось."
#
#                 # KPI-карточки (цветные)
#                 if kpi_data:
#                     n = len([k for k in kpi_data if k != "is_positive"])
#                     kpi_cols = st.columns(n)
#                     idx = 0
#                     for k, v in kpi_data.items():
#                         if k == "is_positive": continue
#                         kpi_cols[idx].metric(label=k, value=v)
#                         idx += 1
#
#                 st.dataframe(df, use_container_width=True)
#                 if not isinstance(fig, str):
#                     st.plotly_chart(fig, use_container_width=True)
#
#                 # --- ИНСАЙТЫ ---
#                 with st.spinner("Генерирую инсайты..."):
#                     summary = df.head(50).to_csv(index=False)
#                     insights = llm_client.get_insights(summary)
#                 if insights:
#                     st.markdown("### 💡 Ключевые инсайты")
#                     st.markdown(insights)
#
#                 # --- СКАЧИВАНИЕ ---
#                 c1, c2 = st.columns(2)
#                 if not isinstance(fig, str):
#                     c1.download_button(
#                         "⬇️ Скачать дашборд (HTML)",
#                         fig.to_html(include_plotlyjs="cdn", full_html=True),
#                         file_name="dashboard.html",
#                         mime="text/html",
#                         key=f"dl_html_{len(st.session_state.messages)}",
#                     )
#                 c2.download_button(
#                     "⬇️ Скачать таблицу (CSV)",
#                     df.to_csv(index=False).encode("utf-8-sig"),
#                     file_name="data.csv",
#                     mime="text/csv",
#                     key=f"dl_csv_{len(st.session_state.messages)}",
#                 )
#
#                 # --- СОХРАНЕНИЕ (через storage) ---
#                 st.divider()
#                 dc1, dc2 = st.columns([2, 1])
#                 default_name = f"Дашборд_{len(st.session_state.messages)}"
#                 dash_name = dc1.text_input(
#                     "Название дашборда:",
#                     value=default_name,
#                     key=f"nm_{len(st.session_state.messages)}",
#                 )
#                 if dc2.button("💾 Сохранить", key=f"sv_{len(st.session_state.messages)}"):
#                     try:
#                         saved = save_dashboard(dash_name, prompt, df, viz_config or {}, kpi_data)
#                         st.success(f"✅ Дашборд сохранён: **{saved}**")
#                         st.caption("Открой боковую панель слева — он появится в списке.")
#                         st.rerun()  # ← принудительно обновим сайдбар
#                     except Exception as e:
#                         import traceback
#
#                         st.error(f"❌ Ошибка сохранения: {e}")
#                         st.code(traceback.format_exc())
#
#                 st.session_state.messages.append({
#                     "role": "assistant",
#                     "content": f"Готово! Строк: {len(df)}.",
#                     "table": df,
#                     "chart": fig,
#                     "kpi": kpi_data,
#                 })

import streamlit as st
import pandas as pd
import os
import time
from sqlalchemy import func
from app.database import SessionLocal
from app.models import Sale, Region
from app.llm_client import llm_client
from app.db_utils import execute_select
from app.charts import calculate_kpi_from_config, build_dashboard_from_config
from app.storage import list_dashboards, load_dashboard, delete_dashboard, save_dashboard
import hashlib

# --- Настройка страницы ---
st.set_page_config(page_title="BI Чат-бот", page_icon="🤖", layout="wide")
st.title("🤖 BI Чат-бот с GigaChat")

# Инициализация счетчика для обновления сайдбара
if "sidebar_refresh" not in st.session_state:
    st.session_state.sidebar_refresh = 0


# --- Функция очистки данных ---
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                df[col] = pd.to_numeric(df[col].str.replace(' ', '').str.replace(',', '.'))
            except Exception:
                pass
        if 'месяц' in str(col).lower() or 'дата' in str(col).lower() or 'период' in str(col).lower():
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].dt.strftime('%Y-%m')
            except Exception:
                pass
    return df


# --- Проверка БД ---
@st.cache_resource
def check_db_connection():
    db = SessionLocal()
    try:
        count = db.query(func.count(Sale.sale_id)).scalar()
        regions_count = db.query(func.count(Region.region_id)).scalar()
        return True, f"✅ БД подключена. Продаж: {count}, Регионов: {regions_count}"
    except Exception as e:
        return False, f"❌ Ошибка БД: {e}"
    finally:
        db.close()


db_status, db_message = check_db_connection()

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("📂 Мои дашборды")
    # Считываем счетчик, чтобы Streamlit перечитал папку при изменении
    _ = st.session_state.sidebar_refresh

    items = list_dashboards()
    if not items:
        st.write("Пока нет сохранённых дашбордов.")
    else:
        for it in items:
            uniq = hashlib.md5(it["name"].encode()).hexdigest()[:6]
            col_a, col_b = st.columns([4, 1])
            if col_a.button(f"📄 {it['name']}", key=f"sb_open_{uniq}", width="stretch"):
                meta, df_restored = load_dashboard(it["name"])
                df_restored = clean_dataframe(df_restored)
                fig_restored = build_dashboard_from_config(df_restored, meta["config"], title=meta["name"])
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"📂 Открыт дашборд **{meta['name']}**\n\n_Запрос: {meta['query']}_",
                    "table": df_restored,
                    "chart": fig_restored,
                    "kpi": meta["kpi"],
                })
                st.rerun()
            if col_b.button("🗑", key=f"sb_del_{uniq}"):
                delete_dashboard(it["name"])
                st.session_state.sidebar_refresh += 1
                st.rerun()

# --- Инициализация истории ---
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": f"Здравствуйте! Я BI-бот.\n\n{db_message}\n\nСпросите что-нибудь, например: «Покажи план-факт по регионам»."
    }]

# --- ОТРИСОВКА ИСТОРИИ ---
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if "table" in msg and msg["table"] is not None:
            st.dataframe(msg["table"], width="stretch")

        if "kpi" in msg and msg["kpi"]:
            kpi_cols = st.columns(len(msg["kpi"]) - (1 if "is_positive" in msg["kpi"] else 0))
            col_idx = 0
            for k, v in msg["kpi"].items():
                if k == "is_positive": continue
                kpi_cols[col_idx].metric(label=k, value=v)
                col_idx += 1

        if "chart" in msg and msg["chart"] is not None:
            if not isinstance(msg["chart"], str):
                # ДОБАВЛЕН key=f"history_chart_{i}" ДЛЯ УНИКАЛЬНОСТИ
                st.plotly_chart(msg["chart"], width="stretch", key=f"history_chart_{i}")
            else:
                st.info(f"ℹ️ {msg['chart']}")

# --- ПОЛЕ ВВОДА ---
if prompt := st.chat_input("Введите запрос..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        from app.calculations import detect_intent, apply_calculation

        intent = detect_intent(prompt)

        # ============ 1. СПИСОК ДАШБОРДОВ ============
        if intent == "list_dashboards":
            items = list_dashboards()
            if not items:
                st.info("Пока нет сохранённых дашбордов.")
                st.session_state.messages.append({"role": "assistant", "content": "Пока нет сохранённых дашбордов."})
            else:
                st.write("### 📂 Мои дашборды")
                for it in items:
                    cols = st.columns([3, 2, 1, 1])
                    cols[0].markdown(f"**{it['name']}**\n\n_{it['query'][:80]}_")
                    cols[1].caption(f"обновлён: {it['updated_at'][:16].replace('T', ' ')}")
                    uniq = hashlib.md5(it["name"].encode()).hexdigest()[:6]
                    if cols[2].button("Открыть", key=f"open_{uniq}"):
                        meta, df_restored = load_dashboard(it["name"])
                        df_restored = clean_dataframe(df_restored)
                        fig_restored = build_dashboard_from_config(df_restored, meta["config"], title=meta["name"])
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"📂 Открыт дашборд **{meta['name']}**\n\n_Запрос: {meta['query']}_",
                            "table": df_restored,
                            "chart": fig_restored,
                            "kpi": meta["kpi"],
                        })
                        st.rerun()
                    if cols[3].button("🗑", key=f"del_{uniq}"):
                        delete_dashboard(it["name"])
                        st.session_state.sidebar_refresh += 1
                        st.rerun()
                st.session_state.messages.append({"role": "assistant", "content": "Список дашбордов показан выше."})
            st.stop()

        # ============ 2. ВЫЧИСЛЕНИЕ ============
        if intent == "calc" and st.session_state.messages:
            last_table = None
            last_idx = None
            for i in range(len(st.session_state.messages) - 1, -1, -1):
                m = st.session_state.messages[i]
                if m.get("table") is not None:
                    last_table = m["table"]
                    last_idx = i
                    break

            if last_table is None:
                msg = "Сначала постройте дашборд, потом добавляйте вычисления."
                st.warning(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            else:
                with st.spinner("Применяю вычисление..."):
                    new_df, err = apply_calculation(last_table, prompt, llm_client)

                if err:
                    st.error(err)
                    st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {err}"})
                else:
                    st.success(f"✅ Добавлено колонок: {new_df.shape[1] - last_table.shape[1]}")
                    new_df = clean_dataframe(new_df)
                    columns_info = "\n".join([f"- {c} (тип: {new_df[c].dtype})" for c in new_df.columns])
                    last_query = st.session_state.messages[last_idx - 1]["content"] if last_idx > 0 else prompt

                    with st.spinner("Обновляю визуализацию..."):
                        viz_config = llm_client.get_chart_config(last_query, columns_info)

                    kpi_data = calculate_kpi_from_config(new_df, viz_config.get("kpi", {}) if viz_config else {})
                    fig = build_dashboard_from_config(new_df, viz_config or {},
                                                      title="Дашборд") if viz_config else "Не удалось перестроить."

                    st.dataframe(new_df, width="stretch")
                    if not isinstance(fig, str):
                        # ДОБАВЛЕН key
                        st.plotly_chart(fig, width="stretch", key=f"calc_chart_{len(st.session_state.messages)}")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"✅ Выполнено: _{prompt}_\n\nВ таблице теперь {new_df.shape[1]} колонок.",
                        "table": new_df,
                        "chart": fig,
                        "kpi": kpi_data,
                    })
            st.stop()

        # ============ 3. ОБЫЧНЫЙ ЗАПРОС ДАННЫХ ============
        with st.spinner("GigaChat генерирует SQL..."):
            sql = llm_client.generate_sql(prompt)

        if sql.startswith("ERROR"):
            st.error(sql)
            st.session_state.messages.append({"role": "assistant", "content": sql})
        else:
            with st.expander("Показать SQL-запрос"):
                st.code(sql, language="sql")

            df = execute_select(sql)
            if "Ошибка" in df.columns:
                error_text = df["Ошибка"][0]
                st.warning("⚠️ Ошибка БД. Пробую исправить...")
                fixed_sql = llm_client.fix_sql(prompt, sql, error_text)
                df = execute_select(fixed_sql)
                if "Ошибка" in df.columns:
                    st.error(f"❌ {df['Ошибка'][0]}")
                    st.stop()

            if df.empty:
                st.info("ℹ️ Данных не найдено.")
                st.session_state.messages.append({"role": "assistant", "content": "Данных не найдено."})
            else:
                df = clean_dataframe(df)
                st.success(f"✅ Строк: {len(df)}")

                columns_info = "\n".join([f"- {c} (тип: {df[c].dtype})" for c in df.columns])
                with st.spinner("ИИ проектирует дашборд..."):
                    viz_config = llm_client.get_chart_config(prompt, columns_info)

                kpi_data = calculate_kpi_from_config(df, viz_config.get("kpi", {}) if viz_config else {})
                fig = build_dashboard_from_config(df, viz_config or {},
                                                  title=f"Дашборд: {prompt[:30]}...") if viz_config else "Не удалось."

                # KPI-карточки
                if kpi_data:
                    n = len([k for k in kpi_data if k != "is_positive"])
                    kpi_cols = st.columns(n)
                    idx = 0
                    for k, v in kpi_data.items():
                        if k == "is_positive": continue
                        kpi_cols[idx].metric(label=k, value=v)
                        idx += 1

                st.dataframe(df, width="stretch")
                if not isinstance(fig, str):
                    # ДОБАВЛЕН key
                    st.plotly_chart(fig, width="stretch", key=f"main_chart_{len(st.session_state.messages)}")

                # ИНСАЙТЫ
                with st.spinner("Генерирую инсайты..."):
                    summary = df.head(50).to_csv(index=False)
                    insights = llm_client.get_insights(summary)
                if insights:
                    st.markdown("### 💡 Ключевые инсайты")
                    st.markdown(insights)

                # СКАЧИВАНИЕ
                c1, c2 = st.columns(2)
                if not isinstance(fig, str):
                    c1.download_button(
                        "⬇️ Скачать HTML",
                        fig.to_html(include_plotlyjs="cdn", full_html=True),
                        file_name="dashboard.html",
                        mime="text/html",
                        key=f"dl_html_{len(st.session_state.messages)}",
                    )
                c2.download_button(
                    "⬇️ Скачать CSV",
                    df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="data.csv",
                    mime="text/csv",
                    key=f"dl_csv_{len(st.session_state.messages)}",
                )

                # --- СОХРАНЕНИЕ ---
                st.divider()
                dc1, dc2 = st.columns([2, 1])
                default_name = f"Дашборд_{len(st.session_state.messages)}"
                dash_name = dc1.text_input(
                    "Название дашборда:",
                    value=default_name,
                    key=f"nm_{len(st.session_state.messages)}",
                )


                # Колбэк для кнопки сохранения
                def handle_save():
                    try:
                        saved_name = save_dashboard(dash_name, prompt, df, viz_config or {}, kpi_data)
                        st.session_state.save_msg = f"✅ Дашборд '{saved_name}' сохранён!"
                        st.session_state.sidebar_refresh += 1
                    except Exception as e:
                        import traceback
                        print("\n" + "=" * 50)
                        print("❌ ОШИБКА СОХРАНЕНИЯ ДАШБОРДА:")
                        traceback.print_exc()
                        print("=" * 50 + "\n")
                        st.session_state.save_msg = f"❌ Ошибка сохранения: {e}"


                dc2.button("💾 Сохранить", key=f"sv_{len(st.session_state.messages)}", on_click=handle_save)

                # Вывод результата сохранения
                if "save_msg" in st.session_state:
                    msg_text = st.session_state.save_msg
                    if "✅" in msg_text:
                        st.toast(msg_text, icon="✅")
                    else:
                        st.error(msg_text)
                    del st.session_state.save_msg

                # ВАЖНО: Добавляем в историю, чтобы дашборд остался на экране
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Готово! Строк: {len(df)}.",
                    "table": df,
                    "chart": fig,
                    "kpi": kpi_data,
                })