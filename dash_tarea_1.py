

from dash import Dash, dcc, html, Input, Output, State, callback, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import os


# ----------------------------
# 1) Carga y preparación de datos
# ----------------------------

DATA_PATH = "cleaned_incident_event_log.csv"

def load_data(path=DATA_PATH):
    # Carga con fallback si el archivo no está
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        df = pd.DataFrame()
    
    
    
    
    
    # Limpieza básica
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    # Parseo de fechas (CSV viene tipo DD/MM/YYYY HH:MM, p.ej. 29/2/2016 01:16)
    for col in ["opened_at", "resolved_at", "closed_at", "sys_updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # Derivadas
    if {"opened_at", "resolved_at"}.issubset(df.columns):
        df["ttr_hours"] = (df["resolved_at"] - df["opened_at"]).dt.total_seconds() / 3600
    else:
        df["ttr_hours"] = np.nan

    # Normalización simple de texto
    for c in ["incident_state", "priority", "category", "assignment_group", "location", "contact_type"]:
        if c in df.columns:
            df[c] = df[c].astype("string")

    # Fallback para made_sla -> booleano consistente
    if "made_sla" in df.columns:
        df["made_sla"] = df["made_sla"].map({
            True: True, False: False, "True": True, "False": False, 1: True, 0: False
        }).fillna(False)

    # Mantener solo registros con active == False (según CSV)
    if "active" in df.columns:
        df = df[df["active"] == False]

    return df

df_base = load_data()

def safe_unique(series, max_items=2000):
    if series is None:
        return []
    vals = series.dropna().unique()
    vals = vals[:max_items]
    # cast a str por seguridad (tipos mixtos)
    return [{"label": str(v), "value": str(v)} for v in sorted(vals)]

def with_total(options, label="Total (todas)"):
    return [{"label": label, "value": "__TOTAL__"}] + (options or [])

# ----------------------------
# 1.1) Rango de meses para el slider
# ----------------------------
if "opened_at" in df_base.columns and df_base["opened_at"].notna().any():
    min_month = df_base["opened_at"].min().to_period("M")
    max_month = df_base["opened_at"].max().to_period("M")
    # Línea temporal mes a mes (incluye meses sin datos; si prefieres solo meses con datos, usa unique())
    months = pd.period_range(min_month, max_month, freq="M")
else:
    # Fallback genérico (2016-01 a 2017-12) si no hay fechas
    months = pd.period_range("2016-01", "2017-12", freq="M")

month_labels = {i: m.strftime("%Y-%m") for i, m in enumerate(months)}
month_default_value = [0, len(months) - 1]

# ----------------------------
# 2) App y estilos externos
# ----------------------------
external_stylesheets = [
    "https://cdnjs.cloudflare.com/ajax/libs/normalize/8.0.1/normalize.min.css",
    "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap",
]
app = Dash(__name__, external_stylesheets=external_stylesheets, suppress_callback_exceptions=True)
server = app.server  # útil si despliegas con gunicorn
app.title = "Tablero de Incidentes"

# ----------------------------
# 3) Layout
# ----------------------------
app.layout = html.Div(
    id="root",
    children=[
        dcc.Location(id="url"),
        dcc.Store(id="store-data", data=df_base.to_dict("records")),
        html.Header(
            className="header",
            children=[
                html.Div("Tablero de Incidentes", className="header-title"),
                html.Div("Versión base conectada a CSV", className="header-subtitle"),
            ],
        ),
        html.Div(
            className="main",
            children=[
                # Nota: dash.html no tiene Aside/Main, usamos Div con className
                html.Div(
                    className="sidebar",
                    children=[
                        html.H3("Filtros"),
                        html.Label("Rango temporal (mes a mes)"),
                        dcc.RangeSlider(
                            id="month-range",
                            min=0,
                            max=len(months) - 1,
                            step=1,
                            value=month_default_value,
                            marks=month_labels,
                            allowCross=False,
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                        html.Label("Estado (incident_state)"),
                        dcc.Dropdown(
                            id="dd-estado",
                            options=with_total(safe_unique(df_base["incident_state"]) if "incident_state" in df_base.columns else []),
                            multi=True,
                            placeholder="Selecciona estado(s)",
                            clearable=True,
                        ),
                        html.Label("Prioridad"),
                        dcc.Dropdown(
                            id="dd-prioridad",
                            options=with_total(safe_unique(df_base["priority"]) if "priority" in df_base.columns else []),
                            multi=True,
                            placeholder="Selecciona prioridad(es)",
                            clearable=True,
                        ),
                        html.Label("Categoría"),
                        dcc.Dropdown(
                            id="dd-categoria",
                            options=with_total(safe_unique(df_base["category"]) if "category" in df_base.columns else []),
                            multi=True,
                            placeholder="Selecciona categoría(s)",
                            clearable=True,
                        ),
                        html.Label("Grupo asignado (assignment_group)"),
                        dcc.Dropdown(
                            id="dd-grupo",
                            options=with_total(safe_unique(df_base["assignment_group"]) if "assignment_group" in df_base.columns else []),
                            multi=True,
                            placeholder="Selecciona grupo(s)",
                            clearable=True,
                        ),
                        html.Label("Ubicación"),
                        dcc.Dropdown(
                            id="dd-location",
                            options=with_total(safe_unique(df_base["location"]) if "location" in df_base.columns else []),
                            multi=True,
                            placeholder="Selecciona ubicación(es)",
                            clearable=True,
                        ),
                        html.Hr(),
                        html.Button("Aplicar", id="btn-aplicar", className="btn-primary"),
                        html.Button("Reset", id="btn-reset", className="btn-secondary", n_clicks=0),
                        html.Hr(),
                        html.Div("Navegación"),
                        dcc.RadioItems(
                            id="nav",
                            options=[
                                {"label": "Resumen", "value": "resumen"},
                                {"label": "Detalle", "value": "detalle"},
                                {"label": "Datos", "value": "datos"},
                            ],
                            value="resumen",
                        ),
                    ],
                ),
                html.Div(
                    className="content",
                    children=[
                        html.Div(className="card", children=[
                            html.H3("Evolución semanal de incidentes"),
                            dcc.Graph(id="fig-series"),
                        ]),
                        html.Div(className="grid-2", children=[
                            html.Div(className="card", children=[
                                html.H3("Distribución por prioridad"),
                                dcc.Graph(id="fig-prioridad"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Top grupos por volumen"),
                                dcc.Graph(id="fig-grupos"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Cumplimiento SLA"),
                                dcc.Graph(id="fig-sla"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Nivel de servicio por tipo de contacto"),
                                dcc.Graph(id="fig-contacto"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Nivel de servicio por tipo de urgencia"),
                                dcc.Graph(id="fig-urgencia"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Distribución del tiempo de resolución (horas)"),
                                html.Label("Número de bins"),
                                dcc.Slider(
                                    id="bins-slider",
                                    min=10, max=1000, step=10, value=500,  # valores iniciales
                                    marks={i: str(i) for i in [10, 100, 500, 1000]}
                                ),
                                html.Label("Límite máximo en el eje X:  "),
                                dcc.Input(
                                    id="xmax-input",
                                    type="number",
                                    value=200,  # valor inicial
                                    min=1, step=10
                                ),
                                dcc.Graph(id="fig-resolution-time"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Tiempo de resolución promedio por categoría"),
                                html.Label("Número de categorías a mostrar"),
                                dcc.Input(
                                    id="topn-input",
                                    type="number",
                                    value=10,   # valor inicial (Top 10)
                                    min=1, step=1
                                ),
                                dcc.Graph(id="fig-top-categorias"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Scatter: Categoría vs Tiempo de Resolución"),
                                dcc.Graph(id="fig-scatter-categoria"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Reassignment Count promedio por Prioridad"),
                                dcc.Graph(id="fig-reassign-prioridad"),
                            ]),
                            html.Div(className="card", children=[
                                html.H3("Distribución de Reassignment Count por Prioridad"),
                                dcc.Graph(id="fig-violin-reassign"),
                            ]),
                        ]),
                        html.Div(className="card", children=[
                            html.H3("Tabla (vista previa)"),
                            dash_table.DataTable(
                                id="tabla",
                                page_size=12,
                                filter_action="native",
                                sort_action="native",
                                style_table={"overflowX": "auto"},
                                style_cell={"fontFamily": "Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial", "fontSize": 13},
                            ),
                        ]),
                    ],
                ),
            ],
        ),
        html.Footer(className="footer", children="© 2025 · Equipo Analítica"),
    ],
)

# ----------------------------
# 4) Callbacks
# ----------------------------

@callback(
    Output("store-data", "data"),
    Output("month-range", "value"),
    Output("dd-estado", "value"),
    Output("dd-prioridad", "value"),
    Output("dd-categoria", "value"),
    Output("dd-grupo", "value"),
    Output("dd-location", "value"),
    Input("btn-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_store(n):
    # Reset: recarga base y limpia filtros al rango completo
    df = load_data()

    # Recalcula months por si cambió el CSV (opcional: podrías omitir y usar los globales)
    if "opened_at" in df.columns and df["opened_at"].notna().any():
        min_m = df["opened_at"].min().to_period("M")
        max_m = df["opened_at"].max().to_period("M")
        rng = pd.period_range(min_m, max_m, freq="M")
        new_value = [0, len(rng) - 1]
    else:
        new_value = [0, len(months) - 1]  # fallback al global

    return df.to_dict("records"), new_value, None, None, None, None, None


@callback(
    Output("fig-series", "figure"),
    Output("fig-prioridad", "figure"),
    Output("fig-grupos", "figure"),
    Output("fig-sla", "figure"),
    Output("fig-contacto", "figure"),
    Output("fig-urgencia", "figure"),
    Output("fig-resolution-time", "figure"),
    Output("fig-top-categorias", "figure"),   # <<< NUEVO
    Output("fig-scatter-categoria", "figure"),
    Output("fig-reassign-prioridad", "figure"),
    Output("fig-violin-reassign", "figure"),
    Output("tabla", "data"),
    Output("tabla", "columns"),
    Input("btn-aplicar", "n_clicks"),
    State("store-data", "data"),
    State("month-range", "value"),
    State("dd-estado", "value"),
    State("dd-prioridad", "value"),
    State("dd-categoria", "value"),
    State("dd-grupo", "value"),
    State("dd-location", "value"),
    State("bins-slider", "value"),
    State("xmax-input", "value"),
    State("topn-input", "value"),              # <<< NUEVO
    prevent_initial_call=True,
)
def actualizar(_, data_records, month_range_idx, estados, prioridades, categorias, grupos, locations,
               bins, xmax, topn):

    df = pd.DataFrame(data_records)

    # --- Normaliza columnas de fecha (tras el roundtrip por dcc.Store) ---
    for col in ["opened_at", "resolved_at", "closed_at", "sys_updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # Asegura el filtro active==False (por si llegara a entrar algo serializado extraño)
    if "active" in df.columns:
        df = df[df["active"] == False]


    # 1) Filtro por meses (RangeSlider)
    # month_range_idx == [i_start, i_end] (índices de 'months' global)
    start_dt = end_dt = None
    if isinstance(month_range_idx, (list, tuple)) and len(month_range_idx) == 2:
        i_start, i_end = int(month_range_idx[0]), int(month_range_idx[1])
        i_start = max(0, min(i_start, len(months) - 1))
        i_end   = max(0, min(i_end, len(months) - 1))
        start_dt = months[i_start].to_timestamp(how="start")
        end_dt   = months[i_end].to_timestamp(how="end")
        if "opened_at" in df.columns and df["opened_at"].notna().any():
            df = df[(df["opened_at"] >= start_dt) & (df["opened_at"] <= end_dt)]

    # Helper de filtro múltiple con opción "Total (todas)"
    def apply_multi_filter(frame, col, values):
        if col in frame.columns and values:
            if "__TOTAL__" in (values if isinstance(values, (list, tuple, set)) else [values]):
                return frame
            return frame[frame[col].astype("string").isin(pd.Series(values, dtype="string"))]
        return frame

    # Aplica filtros de dimensión al df actual
    df = apply_multi_filter(df, "incident_state", estados)
    df = apply_multi_filter(df, "priority", prioridades)
    df = apply_multi_filter(df, "category", categorias)
    df = apply_multi_filter(df, "assignment_group", grupos)
    df = apply_multi_filter(df, "location", locations)

    
    # 2) Gráficos
    # Serie semanal
    if "opened_at" in df.columns and df["opened_at"].notna().any() and len(df) > 0:
        tmp = (df.set_index("opened_at")
                 .assign(cnt=1)
                 .resample("W")["cnt"].sum()
                 .reset_index())
        fig_series = px.line(tmp, x="opened_at", y="cnt", markers=True, title="Incidentes por semana")
        fig_series.update_layout(margin=dict(l=20, r=20, t=50, b=20), xaxis_title="Fecha", yaxis_title="Incidentes")
    else:
        fig_series = go.Figure().update_layout(title="Incidentes por semana (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

    # Prioridad
    if "priority" in df.columns and df["priority"].notna().any() and len(df) > 0:
        pr = (df["priority"].value_counts()
              .rename_axis("priority")
              .reset_index(name="count"))
        priority_order = [p for p in ["1 - Critical","2 - High","3 - Moderate","4 - Low","5 - Planning"] if p in pr["priority"].values]
        if priority_order:
            pr["priority"] = pd.Categorical(pr["priority"], categories=priority_order, ordered=True)
            pr = pr.sort_values("priority")
        fig_prio = px.bar(pr, x="priority", y="count", title="Distribución por prioridad")
        fig_prio.update_traces(text=pr["count"], textposition="outside")
        fig_prio.update_layout(xaxis_title="Prioridad", yaxis_title="Incidentes", margin=dict(l=20, r=20, t=50, b=20))
    else:
        fig_prio = go.Figure().update_layout(title="Distribución por prioridad (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

    # Top grupos
    if "assignment_group" in df.columns and df["assignment_group"].notna().any() and len(df) > 0:
        top_grupos = (df["assignment_group"].value_counts()
              .head(10)
              .rename_axis("assignment_group")
              .reset_index(name="count"))
        fig_grp = px.bar(top_grupos, y="assignment_group", x="count", orientation="h", title="Top 10 grupos por volumen")
        fig_grp.update_traces(text=top_grupos["count"], textposition="outside")

    else:
        fig_grp = go.Figure().update_layout(title="Top grupos (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

    # Cumplimiento SLA
    if "made_sla" in df.columns and df["made_sla"].notna().any() and len(df) > 0:
        valores = df["made_sla"].value_counts()
        labels = ["True", "False"]
        fig_sla = go.Figure(data=[go.Pie(
            labels=labels,
            values=[valores.get(True, 0), valores.get(False, 0)],
            hole=0.3,
            marker=dict(colors=["#4CAF50", "#F44336"])
        )])
        fig_sla.update_layout(title="Porcentaje de cumplimiento de SLA", margin=dict(l=20, r=20, t=50, b=20))
    else:
        fig_sla = go.Figure().update_layout(title="Cumplimiento SLA (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

    
        # Nivel de servicio por tipo de contacto
    if {"contact_type", "made_sla"}.issubset(df.columns) and df["contact_type"].notna().any():
        conteo = df.groupby(["contact_type", "made_sla"]).size().unstack(fill_value=0)
        if True in conteo.columns:  # asegura que exista la columna True
            conteo["nivel_servicio"] = conteo[True] / conteo.sum(axis=1) * 100
            fig_contacto = px.bar(
                conteo,
                x=conteo.index,
                y="nivel_servicio",
                labels={"x": "Tipo de Contacto", "nivel_servicio": "Nivel de Servicio (%)"},
                text="nivel_servicio",
                title="Porcentaje de servicio cumplido por tipo de contacto"
            )
            fig_contacto.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_contacto.update_layout(margin=dict(l=20, r=20, t=50, b=20), yaxis_range=[0, 100])
        else:
            fig_contacto = go.Figure().update_layout(title="Nivel de servicio por tipo de contacto (sin datos)", margin=dict(l=20, r=20, t=50, b=20))
    else:
        fig_contacto = go.Figure().update_layout(title="Nivel de servicio por tipo de contacto (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

        # Nivel de servicio por tipo de urgencia
    if {"urgency", "made_sla"}.issubset(df.columns) and df["urgency"].notna().any():
        conteo2 = df.groupby(["urgency", "made_sla"]).size().unstack(fill_value=0)
        if True in conteo2.columns:
            conteo2["nivel_servicio"] = conteo2[True] / conteo2.sum(axis=1) * 100
            fig_urgencia = px.bar(
                conteo2,
                x=conteo2.index,
                y="nivel_servicio",
                labels={"x": "Urgencia", "nivel_servicio": "Nivel de Servicio (%)"},
                text="nivel_servicio",
                title="Porcentaje de servicio cumplido por tipo de urgencia"
            )
            fig_urgencia.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_urgencia.update_layout(margin=dict(l=20, r=20, t=50, b=20), yaxis_range=[0, 100])
        else:
            fig_urgencia = go.Figure().update_layout(title="Nivel de servicio por urgencia (sin datos)", margin=dict(l=20, r=20, t=50, b=20))
    else:
        fig_urgencia = go.Figure().update_layout(title="Nivel de servicio por urgencia (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

        # Histograma de tiempo de resolución
    if {"opened_at", "resolved_at"}.issubset(df.columns):
        df2 = df.loc[df["active"] == False].copy()
        df2["resolution_time"] = (
            pd.to_datetime(df2["resolved_at"]) - pd.to_datetime(df2["opened_at"])
        ).dt.total_seconds() / 3600
        df2 = df2.dropna(subset=["resolution_time"])

        if len(df2) > 0:
            fig_res = px.histogram(
                df2,
                x="resolution_time",
                nbins=bins or 500,
                title="Distribución del tiempo de resolución (horas)"
            )
            if xmax:
                fig_res.update_xaxes(range=[0, xmax])
            fig_res.update_layout(
                margin=dict(l=20, r=20, t=50, b=20),
                xaxis_title="Horas de resolución",
                yaxis_title="Número de incidentes"
            )
        else:
            fig_res = go.Figure().update_layout(
                title="Distribución del tiempo de resolución (sin datos)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
    else:
        fig_res = go.Figure().update_layout(
            title="Distribución del tiempo de resolución (sin datos)",
            margin=dict(l=20, r=20, t=50, b=20)
        )
        
    
        # Top categorías por tiempo de resolución promedio
    if {"category", "opened_at", "resolved_at"}.issubset(df.columns):
        df2 = df.loc[df["active"] == False].copy()
        df2["resolution_time"] = (
            pd.to_datetime(df2["resolved_at"]) - pd.to_datetime(df2["opened_at"])
        ).dt.total_seconds() / 3600
        df2 = df2.dropna(subset=["resolution_time"])

        if len(df2) > 0:
            promedio_por_categoria = (
                df2.groupby("category")["resolution_time"]
                   .mean()
                   .sort_values(ascending=False)
            )
            try:
                topn_val = int(topn)
            except (TypeError, ValueError):
                topn_val = 10  # valor por defecto si viene vacío o inválido
            topn_val = max(1, topn_val)

            top_cats = promedio_por_categoria.tail(topn_val)  # menor tiempo promedio
            fig_top_cat = px.bar(
                x=top_cats.index,
                y=top_cats.values,
                labels={"x": "Categoría", "y": "Tiempo de resolución promedio (h)"},
                title=f"Top {topn_val} categorías con menor tiempo de resolución promedio"

            )
            fig_top_cat.update_layout(
                margin=dict(l=20, r=20, t=50, b=20),
                xaxis_tickangle=-45
            )
        else:
            fig_top_cat = go.Figure().update_layout(
                title="Top categorías por tiempo de resolución (sin datos)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
    else:
        fig_top_cat = go.Figure().update_layout(
            title="Top categorías por tiempo de resolución (sin datos)",
            margin=dict(l=20, r=20, t=50, b=20)
        )

        # Scatter: número extraído de 'category' vs tiempo de resolución
    if {"category", "opened_at", "resolved_at"}.issubset(df.columns):
        df2 = df.loc[df["active"] == False].copy()
        df2["resolution_time"] = (
            pd.to_datetime(df2["resolved_at"]) - pd.to_datetime(df2["opened_at"])
        ).dt.total_seconds() / 3600

        # Extraer número al final de 'category'
        df2["categoria_num"] = df2["category"].str.extract(r"(\d+)$").astype(float)

        df2_filtrado = df2.dropna(subset=["categoria_num", "resolution_time"])

        if len(df2_filtrado) > 0:
            fig_scatter = px.scatter(
                df2_filtrado,
                x="categoria_num",
                y="resolution_time",
                opacity=0.5,
                labels={"categoria_num": "Número de Categoría", "resolution_time": "Tiempo de Resolución (h)"},
                title="Scatterplot: Categoría vs Tiempo de Resolución"
            )
            fig_scatter.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        else:
            fig_scatter = go.Figure().update_layout(
                title="Scatterplot Categoría vs Tiempo (sin datos)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
    else:
        fig_scatter = go.Figure().update_layout(
            title="Scatterplot Categoría vs Tiempo (sin datos)",
            margin=dict(l=20, r=20, t=50, b=20)
        )
        # Reassignment Count promedio por prioridad
    if {"priority", "reassignment_count"}.issubset(df.columns) and df["priority"].notna().any():
        promedio_por_prioridad = (
            df.groupby("priority")["reassignment_count"]
            .mean()
            .sort_values(ascending=False)
        )
        if len(promedio_por_prioridad) > 0:
            fig_reassign = px.bar(
                x=promedio_por_prioridad.index,
                y=promedio_por_prioridad.values,
                labels={"x": "Prioridad", "y": "Reassignment Count Promedio"},
                title="Reassignment Count Promedio por Prioridad"
            )
            fig_reassign.update_traces(marker_color="#FF5733", text=promedio_por_prioridad.values, textposition="outside")
            fig_reassign.update_layout(margin=dict(l=20, r=20, t=50, b=20))
        else:
            fig_reassign = go.Figure().update_layout(
                title="Reassignment Count por Prioridad (sin datos)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
    else:
        fig_reassign = go.Figure().update_layout(
            title="Reassignment Count por Prioridad (sin datos)",
            margin=dict(l=20, r=20, t=50, b=20)
        )
        # Violinplot de reassignment_count por prioridad (sin puntos individuales)
    if {"priority", "reassignment_count"}.issubset(df.columns) and df["priority"].notna().any():
        df_violin = df.dropna(subset=["priority", "reassignment_count"])
        if len(df_violin) > 0:
            fig_violin = px.violin(
                df_violin,
                x="priority",
                y="reassignment_count",
                box=True,   # muestra boxplot dentro del violín
                title="Distribución de Reassignment Count por Prioridad"
            )
            fig_violin.update_layout(
                xaxis_title="Prioridad",
                yaxis_title="Reassignment Count",
                margin=dict(l=20, r=20, t=50, b=20)
            )
        else:
            fig_violin = go.Figure().update_layout(
                title="Distribución de Reassignment Count (sin datos)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
    else:
        fig_violin = go.Figure().update_layout(
            title="Distribución de Reassignment Count (sin datos)",
            margin=dict(l=20, r=20, t=50, b=20)
        )



        

        
        


        
    
    
    
    # 4) Tabla
    show_cols = [c for c in [
        "number","opened_at","incident_state","priority","category","subcategory",
        "assignment_group","location","contact_type","made_sla","reassignment_count",
        "reopen_count","ttr_hours"
    ] if c in df.columns]
    tabla = df[show_cols].head(400) if show_cols else df.head(400)
    columns = [{"name": c, "id": c} for c in tabla.columns]

    

    return (
    fig_series, fig_prio, fig_grp,
    fig_sla, fig_contacto, fig_urgencia,
    fig_res, fig_top_cat, fig_scatter,fig_reassign, fig_violin,
    tabla.to_dict("records"), columns)






# ----------------------------
# 5) Entry point
# ----------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 8050)), debug=True)
