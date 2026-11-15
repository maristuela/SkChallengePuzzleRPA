import streamlit as st
import pandas as pd
import os
import time
import datetime
from sqlalchemy import func
from app.database import SessionLocal
from app.models import Sale, Region
from app.llm_client import llm_client
from app.db_utils import execute_select
from app.charts import calculate_kpi_from_config, build_dashboard_from_config
from app.storage import list_dashboards, load_dashboard, delete_dashboard, save_dashboard
from app.calculations import detect_intent, apply_calculation
import hashlib
import json

# --- Настройка страницы ---
st.set_page_config(page_title="Puzzle BI", page_icon="📊", layout="wide")
st.title("📊 Puzzle BI: Аналитика на естественном языке")

# --- Красивый дизайн (CSS) ---
st.markdown("""
<style>
    .stMetric { 
        background-color: #f8f9fa; 
        padding: 15px; 
        border-radius: 10px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); 
        border-left: 5px solid #4C78A8;
    }
    h1 { color: #1E3A8A; }
</style>
""", unsafe_allow_html=True)

# --- Инициализация сессий ---
if "sidebar_refresh" not in st.session_state:
    st.session_state.sidebar_refresh = 0
if "active_dashboard" not in st.session_state:
    st.session_state.active_dashboard = None
if "messages" not in st.session_state:
    st.session_state.messages = []


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
                df[col] = df[col].dt.strftime('%Y-%m-%d')
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

if not st.session_state.messages:
    st.session_state.messages = [{
        "role": "assistant",
        "content": f"Здравствуйте! Я Puzzle BI.\n\n{db_message}\n\nСпросите что-нибудь, например: «Покажи план-факт по регионам за последний год»."
    }]

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("📂 Мои дашборды")
    _ = st.session_state.sidebar_refresh

    items = list_dashboards()
    if not items:
        st.write("Пока нет сохранённых дашбордов.")
    else:
        for it in items:
            uniq = hashlib.md5(it["name"].encode()).hexdigest()[:6]
            col_a, col_b = st.columns([4, 1])
            if col_a.button(f"📄 {it['name']}", key=f"sb_open_{uniq}", use_container_width=True):
                meta, df_restored = load_dashboard(it["name"])
                df_restored = clean_dataframe(df_restored)
                st.session_state.active_dashboard = {
                    "prompt": meta["query"],
                    "df": df_restored,
                    "viz_config": meta["config"],
                    "filters": meta.get("filters", {}),
                    "history": []
                }
                st.rerun()
            if col_b.button("🗑", key=f"sb_del_{uniq}"):
                delete_dashboard(it["name"])
                st.session_state.sidebar_refresh += 1
                st.rerun()

# =====================================================================
# РЕЖИМ 1: РЕДАКТИРОВАНИЕ ДАШБОРДА (Открывается из левой панели)
# =====================================================================
if st.session_state.active_dashboard is not None:
    dash = st.session_state.active_dashboard

    col_head1, col_head2, col_head3 = st.columns([3, 1, 1])
    col_head1.markdown(f"### 🛠 Рабочая область")
    st.caption(f"Исходный запрос: *{dash['prompt']}*")

    if col_head2.button("🔙 Новый запрос", use_container_width=True):
        st.session_state.active_dashboard = None
        st.rerun()

    if col_head3.button("⏪ Отменить", use_container_width=True, disabled=not dash.get("history")):
        if dash.get("history"):
            last_state = dash["history"].pop()
            dash["df"] = last_state["df"]
            dash["viz_config"] = last_state["viz_config"]
            st.rerun()

    st.info("💡 БД не нагружается. Пишите в чат, чтобы изменить таблицу или графики.")

    df_active = dash["df"]

    # --- ПЕРЕКЛЮЧАТЕЛИ (Метрика и Разрез) ---
    num_cols = [c for c in df_active.columns if pd.api.types.is_numeric_dtype(df_active[c])]
    cat_cols_for_switch = [c for c in df_active.columns if
                           not pd.api.types.is_numeric_dtype(df_active[c]) and df_active[c].nunique() < 50]

    if num_cols and cat_cols_for_switch:
        st.write("**⚙️ Быстрая перестройка главного графика:**")
        sc1, sc2, sc3 = st.columns([2, 2, 1])

        with sc1:
            sel_metric = st.selectbox("Метрика (ось Y):", num_cols, key="sw_metric")
        with sc2:
            sel_x = st.selectbox("Разрез (ось X):", cat_cols_for_switch, key="sw_x")
        with sc3:
            st.write("")
            st.write("")
            if st.button("🔄 Перестроить", use_container_width=True):
                dash["history"].append({"df": dash["df"].copy(), "viz_config": dict(dash["viz_config"])})

                new_viz = dict(dash["viz_config"])
                new_viz["charts"] = list(new_viz.get("charts", []))
                if new_viz["charts"]:
                    new_viz["charts"][0] = {
                        "type": "bar",
                        "title": f"{sel_metric} по {sel_x}",
                        "x": sel_x,
                        "y": sel_metric,
                        "group_by": None
                    }
                st.session_state.active_dashboard["viz_config"] = new_viz
                st.rerun()

    # --- УМНЫЕ ФИЛЬТРЫ ---
    if "filters" not in dash:
        dash["filters"] = {}

    st.write("**🎛 Панель фильтров:**")
    all_cols = list(df_active.columns)
    cat_cols = [c for c in all_cols if
                not pd.api.types.is_numeric_dtype(df_active[c]) and not pd.api.types.is_datetime64_any_dtype(
                    df_active[c])]
    date_cols = [c for c in all_cols if pd.api.types.is_datetime64_any_dtype(df_active[c]) or 'месяц' in str(c).lower()]

    tab1, tab2 = st.tabs(["📅 Период", "🏷 Категории"])
    filtered_df = df_active.copy()

    with tab1:
        if date_cols:
            date_col = date_cols[0]
            unique_dates = sorted(df_active[date_col].dropna().unique().tolist())
            if len(unique_dates) > 1:
                selected_range = st.select_slider(
                    f"Выберите диапазон:",
                    options=unique_dates,
                    value=(unique_dates[0], unique_dates[-1]),
                    format_func=lambda x: str(x)[:10]
                )
                start_date, end_date = selected_range
                filtered_df = filtered_df[(filtered_df[date_col] >= start_date) & (filtered_df[date_col] <= end_date)]
                st.caption(f"Выбрано: с {str(start_date)[:10]} по {str(end_date)[:10]}")
            else:
                st.info("В данных только один период.")
        else:
            st.info("Нет колонок с датами.")

    with tab2:
        if cat_cols:
            for col in cat_cols[:4]:
                unique_vals = sorted(df_active[col].dropna().astype(str).unique().tolist())
                saved_sel = dash["filters"].get(col, [])
                default_sel = [v for v in saved_sel if v in unique_vals]

                selected = st.multiselect(
                    f"{col}",
                    options=unique_vals,
                    default=default_sel,
                    key=f"filter_{col}_{hash(dash['prompt']) % 10000}",
                    placeholder="Поиск..."
                )
                dash["filters"][col] = selected
                if selected:
                    filtered_df = filtered_df[filtered_df[col].astype(str).isin(selected)]
        else:
            st.info("Нет текстовых колонок (Регион, Продукт и т.д.).")

    if len(filtered_df) != len(df_active):
        st.success(f"🔍 Отфильтровано: **{len(filtered_df)}** из {len(df_active)} строк")
        df_active = filtered_df

    st.divider()

    # --- ОТРИСОВКА ---
    if df_active.empty:
        st.warning("⚠️ Под текущие фильтры не подходит ни одна строка.")
    else:
        kpi_active = calculate_kpi_from_config(df_active, dash["viz_config"].get("kpi", {}))
        if kpi_active:
            n = len([k for k in kpi_active if k != "is_positive"])
            kpi_cols = st.columns(n)
            idx = 0
            for k, v in kpi_active.items():
                if k == "is_positive": continue
                kpi_cols[idx].metric(label=k, value=v)
                idx += 1

        st.dataframe(df_active, use_container_width=True)

        fig_active = build_dashboard_from_config(df_active, dash["viz_config"], title="Текущий дашборд")
        if not isinstance(fig_active, str):
            st.plotly_chart(fig_active, use_container_width=True, key="active_chart")

            # СКАЧИВАНИЕ (с учетом фильтров)
            st.write("**⬇️ Экспорт текущего вида:**")
            dl1, dl2, dl3 = st.columns(3)
            try:
                dl1.download_button(
                    "Скачать PNG",
                    fig_active.to_image(format="png"),
                    file_name="dashboard.png",
                    mime="image/png",
                    key="dl_active_png",
                    use_container_width=True
                )
            except Exception:
                dl1.caption("Для PNG нужен pip install kaleido")

            dl2.download_button(
                "Скачать HTML",
                fig_active.to_html(include_plotlyjs="cdn", full_html=True),
                file_name="dashboard.html",
                mime="text/html",
                key="dl_active_html",
                use_container_width=True
            )
            dl3.download_button(
                "Скачать CSV",
                df_active.to_csv(index=False).encode("utf-8-sig"),
                file_name="data.csv",
                mime="text/csv",
                key="dl_active_csv",
                use_container_width=True
            )

    # --- СОХРАНЕНИЕ ОБНОВЛЕНИЙ В ЛЕВУЮ ПАНЕЛЬ ---
    st.divider()
    dc1, dc2 = st.columns([2, 1])
    now_str = datetime.datetime.now().strftime("%H-%M-%S")
    default_name = f"Дашборд_{now_str}"
    dash_name = dc1.text_input("Название для сохранения:", value=default_name, key="save_active_name")


    def handle_save_active():
        try:
            saved_name = save_dashboard(dash_name, dash["prompt"], df_active, dash["viz_config"], kpi_active)
            meta_path = os.path.join("saved_dashboards", f"{saved_name}.json")
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            meta["filters"] = dash.get("filters", {})
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            st.session_state.save_msg = f"✅ Дашборд '{saved_name}' сохранён!"
            st.session_state.sidebar_refresh += 1
        except Exception as e:
            st.session_state.save_msg = f"❌ Ошибка: {e}"


    dc2.button("💾 Сохранить дашборд", key="save_active_btn", on_click=handle_save_active)

    if "save_msg" in st.session_state:
        msg_text = st.session_state.save_msg
        if "✅" in msg_text:
            st.toast(msg_text, icon="✅")
        else:
            st.error(msg_text)
        del st.session_state.save_msg

    # --- ЧАТ ДЛЯ МОДИФИКАЦИИ ---
    if prompt_mod := st.chat_input("Напишите: 'Добавь отклонение', 'Убери Регион', 'Перестрой график'..."):
        with st.spinner("Обрабатываю запрос..."):
            p_lower = prompt_mod.lower()
            is_chart_request = any(w in p_lower for w in ["график", "графики", "перестрой", "нарисуй", "построй"])

            if is_chart_request:
                dash["history"].append({"df": dash["df"].copy(), "viz_config": dict(dash["viz_config"])})

                columns_info = "\n".join([f"- {c} (тип: {df_active[c].dtype})" for c in df_active.columns])
                new_viz = llm_client.get_chart_config(prompt_mod, columns_info)
                if new_viz:
                    st.session_state.active_dashboard["viz_config"] = new_viz
                    st.success("✅ Графики перестроены!")
                    st.rerun()
                else:
                    st.error("❌ Не удалось перестроить графики.")
            else:
                new_df, err = apply_calculation(df_active, prompt_mod, llm_client)
                if err:
                    st.error(f"Ошибка обработки: {err}")
                else:
                    if new_df.empty or new_df.shape[1] == 0:
                        st.warning("⚠️ В таблице не осталось колонок.")
                    else:
                        dash["history"].append({"df": dash["df"].copy(), "viz_config": dict(dash["viz_config"])})

                        columns_info = "\n".join([f"- {c} (тип: {new_df[c].dtype})" for c in new_df.columns])
                        new_viz = llm_client.get_chart_config(dash["prompt"], columns_info)
                        st.session_state.active_dashboard["df"] = new_df
                        if new_viz: st.session_state.active_dashboard["viz_config"] = new_viz
                        st.success("✅ Таблица пересчитана!")
                        st.rerun()

# =====================================================================
# РЕЖИМ 2: ОБЫЧНЫЙ ЧАТ (Запросы к БД)
# =====================================================================
else:
    # 1. Отрисовываем историю чата
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "table" in msg and msg["table"] is not None:
                st.dataframe(msg["table"], use_container_width=True)
            if "kpi" in msg and msg["kpi"]:
                kpi_cols = st.columns(len(msg["kpi"]) - (1 if "is_positive" in msg["kpi"] else 0))
                col_idx = 0
                for k, v in msg["kpi"].items():
                    if k == "is_positive": continue
                    kpi_cols[col_idx].metric(label=k, value=v)
                    col_idx += 1
            if "chart" in msg and msg["chart"] is not None:
                if not isinstance(msg["chart"], str):
                    st.plotly_chart(msg["chart"], use_container_width=True, key=f"history_chart_{i}")
                else:
                    st.info(f"ℹ️ {msg['chart']}")

    # 2. Если есть последний сгенерированный дашборд — показываем кнопки ПОД историей
    if "last_generated" in st.session_state:
        last = st.session_state.last_generated

        st.divider()
        st.subheader("📥 Экспорт и сохранение")

        # Кнопки скачивания на компьютер
        c1, c2, c3 = st.columns(3)
        fig_to_save = last["fig"]
        df_to_save = last["df"]

        if not isinstance(fig_to_save, str):
            try:
                c1.download_button(
                    "⬇️ Скачать PNG",
                    fig_to_save.to_image(format="png"),
                    file_name="dashboard.png",
                    mime="image/png",
                    key="dl_png_last",
                    use_container_width=True
                )
            except Exception:
                c1.caption("Для PNG нужен pip install kaleido")

            c2.download_button(
                "⬇️ Скачать HTML",
                fig_to_save.to_html(include_plotlyjs="cdn", full_html=True),
                file_name="dashboard.html",
                mime="text/html",
                key="dl_html_last",
                use_container_width=True
            )
        c3.download_button(
            "⬇️ Скачать CSV",
            df_to_save.to_csv(index=False).encode("utf-8-sig"),
            file_name="data.csv",
            mime="text/csv",
            key="dl_csv_last",
            use_container_width=True
        )

        # Сохранение в левую панель
        dc1, dc2 = st.columns([2, 1])
        now_str = datetime.datetime.now().strftime("%H-%M-%S")
        default_name = f"Дашборд_{now_str}"
        dash_name = dc1.text_input("Название для сохранения:", value=default_name, key="save_last_name")


        def handle_save_last():
            try:
                saved_name = save_dashboard(
                    dash_name, last["prompt"], last["df"], last["viz_config"], last["kpi"]
                )
                st.session_state.save_msg = f"✅ Дашборд '{saved_name}' сохранён в левую панель!"
                st.session_state.sidebar_refresh += 1
            except Exception as e:
                st.session_state.save_msg = f"❌ Ошибка сохранения: {e}"


        dc2.button("💾 Сохранить в мои дашборды", key="sv_last", on_click=handle_save_last)

        if "save_msg" in st.session_state:
            msg_text = st.session_state.save_msg
            if "✅" in msg_text:
                st.toast(msg_text, icon="✅")
            else:
                st.error(msg_text)
            del st.session_state.save_msg

        st.divider()

    # 3. Поле ввода в самом низу
    if prompt := st.chat_input("Введите запрос к базе данных..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            intent = detect_intent(prompt)

            # Уточняющий вопрос
            if len(prompt.split()) < 4 and not any(
                    w in prompt.lower() for w in ["месяц", "год", "квартал", "регион", "продукт", "точк"]):
                clarify = llm_client.clarify_query(prompt)
                if clarify and clarify.strip().upper() != "OK":
                    st.warning(f"❓ {clarify}")
                    st.session_state.messages.append({"role": "assistant", "content": f"❓ {clarify}"})
                    st.stop()

            if intent == "list_dashboards":
                items = list_dashboards()
                if not items:
                    st.info("Пока нет сохранённых дашбордов.")
                    st.session_state.messages.append(
                        {"role": "assistant", "content": "Пока нет сохранённых дашбордов."})
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
                            st.session_state.active_dashboard = {
                                "prompt": meta["query"],
                                "df": df_restored,
                                "viz_config": meta["config"],
                                "filters": meta.get("filters", {}),
                                "history": []
                            }
                            st.rerun()
                        if cols[3].button("🗑", key=f"del_{uniq}"):
                            delete_dashboard(it["name"])
                            st.session_state.sidebar_refresh += 1
                            st.rerun()
                    st.session_state.messages.append({"role": "assistant", "content": "Список дашбордов показан выше."})
                st.stop()

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

                    if kpi_data:
                        n = len([k for k in kpi_data if k != "is_positive"])
                        kpi_cols = st.columns(n)
                        idx = 0
                        for k, v in kpi_data.items():
                            if k == "is_positive": continue
                            kpi_cols[idx].metric(label=k, value=v)
                            idx += 1

                    st.dataframe(df, use_container_width=True)
                    if not isinstance(fig, str):
                        st.plotly_chart(fig, use_container_width=True,
                                        key=f"main_chart_{len(st.session_state.messages)}")

                    with st.spinner("Генерирую инсайты..."):
                        summary = df.head(50).to_csv(index=False)
                        insights = llm_client.get_insights(summary)
                    if insights:
                        st.markdown("### 💡 Ключевые инсайты")
                        st.markdown(insights)

                    # Сохраняем последний сгенерированный дашборд в сессию
                    st.session_state.last_generated = {
                        "prompt": prompt,
                        "df": df,
                        "viz_config": viz_config,
                        "kpi": kpi_data,
                        "fig": fig
                    }

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Готово! Строк: {len(df)}.",
                        "table": df,
                        "chart": fig,
                        "kpi": kpi_data,
                    })

                    # Перезапускаем, чтобы интерфейс отрисовал блок с кнопками
                    st.rerun()






















