import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def calculate_kpi_from_config(df: pd.DataFrame, kpi_config: dict) -> dict:
    kpi = {}
    if df.empty or not kpi_config:
        return kpi

    main_metric = kpi_config.get("main_metric")
    plan_metric = kpi_config.get("plan_metric")

    if main_metric and main_metric in df.columns:
        df[main_metric] = pd.to_numeric(df[main_metric], errors='coerce').fillna(0)
        fact_sum = df[main_metric].sum()
        kpi["Факт"] = f"{fact_sum:,.0f} ₽"

        if plan_metric and plan_metric in df.columns:
            df[plan_metric] = pd.to_numeric(df[plan_metric], errors='coerce').fillna(0)
            plan_sum = df[plan_metric].sum()
            completion = (fact_sum / plan_sum * 100) if plan_sum else 0
            deviation = fact_sum - plan_sum

            kpi["План"] = f"{plan_sum:,.0f} ₽"
            kpi["Выполнение"] = f"{completion:.1f}%"
            kpi["Отклонение"] = f"{deviation:,.0f} ₽"
            kpi["is_positive"] = deviation >= 0

    return kpi


def build_dashboard_from_config(df: pd.DataFrame, config: dict, title: str = "Дашборд"):
    if df is None or df.empty:
        return "По вашему запросу не найдено данных для построения графиков."
    if not config or not config.get("charts"):
        return "ИИ не смог спроектировать графики для этих данных."

    charts = config["charts"][:4]
    n_charts = len(charts)

    # Определяем размер сетки
    rows = 2 if n_charts > 2 else 1
    cols = 2 if n_charts > 1 else 1

    # --- ИСПРАВЛЕНИЕ: Plotly не понимает 'line' в make_subplots, нужен 'xy' ---
    specs = []
    for i in range(rows):
        row_specs = []
        for j in range(cols):
            idx = i * cols + j
            if idx < n_charts:
                c_type = charts[idx].get("type", "bar")
                if c_type in ["line", "scatter"]:
                    c_type = "xy"  # ← Конвертация для сетки Plotly
                row_specs.append({"type": c_type})
            else:
                row_specs.append({"type": "xy"})  # Пустая ячейка
        specs.append(row_specs)

    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=[c.get("title", f"График {i + 1}") for i, c in enumerate(charts)],
        specs=specs
    )

    row_idx, col_idx = 1, 1
    for chart in charts:
        c_type = chart.get("type")
        title_text = chart.get("title", "")

        # ==========================================
        # ОТРИСОВКА СТОЛБЦОВ (BAR)
        # ==========================================
        if c_type == "bar":
            x_col = chart.get("x")
            y_cols = chart.get("y")
            color_col = chart.get("group_by")

            if isinstance(y_cols, str):
                y_cols = [y_cols]
            elif not isinstance(y_cols, list):
                y_cols = []

            if isinstance(x_col, str) and x_col in df.columns:
                valid_y_cols = [y for y in y_cols if y in df.columns]

                if valid_y_cols:
                    # Если есть колонка для раскраски (например, Регион)
                    if color_col and isinstance(color_col, str) and color_col in df.columns:
                        df_agg = df.groupby([x_col, color_col], as_index=False)[valid_y_cols].sum()

                        # Получаем уникальные цвета из палитры Plotly
                        import plotly.colors as pc
                        unique_colors = df_agg[color_col].unique()
                        color_map = {val: pc.qualitative.Plotly[i % len(pc.qualitative.Plotly)] for i, val in
                                     enumerate(unique_colors)}

                        # Рисуем отдельные серии для каждого цвета (региона) и каждой метрики
                        for y_col in valid_y_cols:
                            for color_val in unique_colors:
                                df_subset = df_agg[df_agg[color_col] == color_val]
                                fig.add_trace(go.Bar(
                                    x=df_subset[x_col],
                                    y=df_subset[y_col],
                                    name=f"{y_col} ({color_val})",  # Название в легенде
                                    marker_color=color_map[color_val]  # Передаем HEX-цвет
                                ), row=row_idx, col=col_idx)
                    else:
                        # Простая отрисовка без раскраски
                        df_agg = df.groupby(x_col, as_index=False)[valid_y_cols].sum()
                        for y_col in valid_y_cols:
                            fig.add_trace(go.Bar(
                                x=df_agg[x_col],
                                y=df_agg[y_col],
                                name=str(y_col),
                            ), row=row_idx, col=col_idx)

        # ==========================================
        # ОТРИСОВКА ПИРОГА (PIE)
        # ==========================================
        elif c_type == "pie":
            names, values = chart.get("names"), chart.get("values")
            if names in df.columns and values in df.columns:
                df_agg = df.groupby(names)[values].sum().reset_index()
                fig.add_trace(go.Pie(labels=df_agg[names], values=df_agg[values], name=title_text),
                              row=row_idx, col=col_idx)

        # ==========================================
        # ОТРИСОВКА ЛИНИИ (LINE / SCATTER)
        # ==========================================
        elif c_type in ["line", "scatter"]:
            x_col = chart.get("x")
            y_cols = chart.get("y")
            color_col = chart.get("group_by")

            if isinstance(y_cols, str):
                y_cols = [y_cols]
            elif not isinstance(y_cols, list):
                y_cols = []

            if x_col in df.columns:
                valid_y_cols = [y for y in y_cols if y in df.columns]

                if valid_y_cols:
                    group_cols = [x_col] + ([color_col] if color_col and color_col in df.columns else [])
                    df_agg = df.groupby(group_cols)[valid_y_cols].sum().reset_index().sort_values(x_col)

                    for y_col in valid_y_cols:
                        fig.add_trace(go.Scatter(
                            x=df_agg[x_col],
                            y=df_agg[y_col],
                            mode='lines+markers',
                            name=str(y_col)
                        ), row=row_idx, col=col_idx)

        # Двигаем курсор сетки
        col_idx += 1
        if col_idx > cols:
            col_idx = 1
            row_idx += 1

    # Настройка внешнего вида
    fig.update_layout(
        title_text=title,
        height=400 * rows,
        template="plotly_white",
        showlegend=True,
        barmode="group",
        font=dict(family="Arial, sans-serif", size=13, color="#222"),
        colorway=["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2"],
        margin=dict(l=60, r=30, t=80, b=60),
    )
    fig.update_xaxes(title_font=dict(size=12), tickfont=dict(size=11))
    fig.update_yaxes(title_font=dict(size=12), tickfont=dict(size=11))

    return fig