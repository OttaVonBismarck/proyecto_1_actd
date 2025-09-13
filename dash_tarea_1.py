
# Tablero de Incidentes (basado en cleaned_incident_event_log.csv)
# Ejecuta con:  python app.py



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
                            html.H3("KPIs"),
                            html.Div(className="kpi-grid", children=[
                                html.Div(className="kpi", children=[html.Div("Incidentes", className="kpi-title"),
                                                                    html.Div(id="kpi-incidentes", className="kpi-value")]),
                                html.Div(className="kpi", children=[html.Div("% SLA cumplido", className="kpi-title"),
                                                                    html.Div(id="kpi-sla", className="kpi-value")]),
                                html.Div(className="kpi", children=[html.Div("TTR medio (h)", className="kpi-title"),
                                                                    html.Div(id="kpi-ttr", className="kpi-value")]),
                            ])
                        ]),
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
    Output("kpi-incidentes", "children"),
    Output("kpi-sla", "children"),
    Output("kpi-ttr", "children"),
    Output("fig-series", "figure"),
    Output("fig-prioridad", "figure"),
    Output("fig-grupos", "figure"),
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
    prevent_initial_call=True,
)
def actualizar(_, data_records, month_range_idx, estados, prioridades, categorias, grupos, locations):
    df = pd.DataFrame(data_records)

    # --- Normaliza columnas de fecha (tras el roundtrip por dcc.Store) ---
    for col in ["opened_at", "resolved_at", "closed_at", "sys_updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # 1) Filtro por meses (RangeSlider)
    if isinstance(month_range_idx, (list, tuple)) and len(month_range_idx) == 2:
        i_start, i_end = int(month_range_idx[0]), int(month_range_idx[1])
        i_start = max(0, min(i_start, len(months) - 1))
        i_end   = max(0, min(i_end, len(months) - 1))
        start_dt = months[i_start].to_timestamp(how="start")
        end_dt   = months[i_end].to_timestamp(how="end")
        if "opened_at" in df.columns and df["opened_at"].notna().any():
            df = df[(df["opened_at"] >= start_dt) & (df["opened_at"] <= end_dt)]

    # >>> MODIFICADO: helper de filtro que ignora si está "Total (todas)"
    def apply_multi_filter(frame, col, values):
        if col in frame.columns and values:
            # Si incluye la opción total, no filtramos esa dimensión
            if "__TOTAL__" in (v if isinstance(values, (list, tuple, set)) else [values]):
                return frame
            return frame[frame[col].astype("string").isin(pd.Series(values, dtype="string"))]
        return frame

    df = apply_multi_filter(df, "incident_state", estados)
    df = apply_multi_filter(df, "priority", prioridades)
    df = apply_multi_filter(df, "category", categorias)
    df = apply_multi_filter(df, "assignment_group", grupos)
    df = apply_multi_filter(df, "location", locations)

    # 2) KPIs
    n_inc = int(len(df))
    sla = 0.0
    if "made_sla" in df.columns and n_inc > 0:
        sla = 100.0 * (df["made_sla"] == True).mean()
    ttr = 0.0
    if "ttr_hours" in df.columns and df["ttr_hours"].notna().any():
        ttr = float(df["ttr_hours"].mean())

    # 3) Gráficos
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
        topn = (df["assignment_group"].value_counts()
                .head(10)
                .rename_axis("assignment_group")
                .reset_index(name="count"))
        fig_grp = px.bar(topn, y="assignment_group", x="count", orientation="h", title="Top 10 grupos por volumen")
        fig_grp.update_traces(text=topn["count"], textposition="outside")
        fig_grp.update_layout(yaxis_title="", xaxis_title="Incidentes", margin=dict(l=20, r=20, t=50, b=20))
    else:
        fig_grp = go.Figure().update_layout(title="Top grupos (sin datos)", margin=dict(l=20, r=20, t=50, b=20))

    # 4) Tabla
    show_cols = [c for c in [
        "number","opened_at","incident_state","priority","category","subcategory",
        "assignment_group","location","contact_type","made_sla","reassignment_count",
        "reopen_count","ttr_hours"
    ] if c in df.columns]
    tabla = df[show_cols].head(400) if show_cols else df.head(400)
    columns = [{"name": c, "id": c} for c in tabla.columns]

    # KPIs como strings nice
    kpi_inc = f"{n_inc:,}"
    kpi_sla = f"{sla:,.1f}%"
    kpi_ttr = f"{ttr:,.1f}"

    return kpi_inc, kpi_sla, kpi_ttr, fig_series, fig_prio, fig_grp, tabla.to_dict("records"), columns


# ----------------------------
# 5) Entry point
# ----------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 8050)), debug=True)
