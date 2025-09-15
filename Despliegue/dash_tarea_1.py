

from dash import Dash, dcc, html, Input, Output, State, callback, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import os
import plotly.io as pio


# --- Helpers de estilo para que las figuras respeten el tema oscuro ---
def style_fig(fig, title=None):
    fig.update_layout(
        title=title or fig.layout.title.text,
        paper_bgcolor="#1E1E2F",   # mismo fondo de .card
        plot_bgcolor="#1E1E2F",
        font=dict(color="#E5E7EB"),  # texto claro
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(
        gridcolor="#374151", zerolinecolor="#374151", linecolor="#374151", ticks="outside"
    )
    fig.update_yaxes(
        gridcolor="#374151", zerolinecolor="#374151", linecolor="#374151", ticks="outside"
    )
    return fig




# ----------------------------
# 1) Carga y preparación de datos
# ----------------------------

DATA_PATH = "Tarea 5 - Desarrollo de tablero\cleaned_incident_event_log.csv"

def load_data(path=DATA_PATH):
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        df = pd.DataFrame()

    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    for col in ["opened_at", "resolved_at", "closed_at", "sys_updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    if {"opened_at", "resolved_at"}.issubset(df.columns):
        df["ttr_hours"] = (df["resolved_at"] - df["opened_at"]).dt.total_seconds() / 3600
    else:
        df["ttr_hours"] = np.nan

    for c in ["incident_state", "priority", "category", "assignment_group", "location", "contact_type"]:
        if c in df.columns:
            df[c] = df[c].astype("string")

    if "made_sla" in df.columns:
        df["made_sla"] = df["made_sla"].map({
            True: True, False: False, "True": True, "False": False, 1: True, 0: False
        }).fillna(False)

    if "active" in df.columns:
        df = df[df["active"] == False]

    return df

df_base = load_data()

# --- Modelo lineal para predecir tiempo de resolución (horas) ---
def predecir_tiempo(active, reassignment_count, reopen_count, sys_mod_count,
                    sys_updated_by, contact_type, category, priority,
                    assignment_group, assigned_to, u_priority_confirmation,
                    notify, resolved_by):
    intercept = 0  # modelo "uncentered"
    coef = {
        "active": 87.3659,
        "reassignment_count": -72.5064,
        "reopen_count": -194.6124,
        "sys_mod_count": 56.6763,
        "sys_updated_by": -0.0429,
        "contact_type": 14.7704,
        "category": 0.5128,
        "priority": 26.0830,
        "assignment_group": -0.2867,
        "assigned_to": 0.2307,
        "u_priority_confirmation": -121.7733,
        "notify": -107.3165,
        "resolved_by": -0.2494
    }
    tiempo = (
        intercept
        + coef["active"] * active
        + coef["reassignment_count"] * reassignment_count
        + coef["reopen_count"] * reopen_count
        + coef["sys_mod_count"] * sys_mod_count
        + coef["sys_updated_by"] * sys_updated_by
        + coef["contact_type"] * contact_type
        + coef["category"] * category
        + coef["priority"] * priority
        + coef["assignment_group"] * assignment_group
        + coef["assigned_to"] * assigned_to
        + coef["u_priority_confirmation"] * u_priority_confirmation
        + coef["notify"] * notify
        + coef["resolved_by"] * resolved_by
    )
    return max(tiempo, 0.0)


def _num_or_zero(val):
    """Convierte None/'' a 0 y castea a float."""
    try:
        if val in (None, ""): 
            return 0.0
        return float(val)
    except Exception:
        return 0.0



def safe_unique(series, max_items=2000):
    if series is None:
        return []
    vals = series.dropna().unique()
    vals = vals[:max_items]
    return [{"label": str(v), "value": str(v)} for v in sorted(vals)]

def with_total(options, label="Total (todas)"):
    return [{"label": label, "value": "__TOTAL__"}] + (options or [])

# ----------------------------
# 1.1) Rango de meses para el slider
# ----------------------------
if "opened_at" in df_base.columns and df_base["opened_at"].notna().any():
    min_month = df_base["opened_at"].min().to_period("M")
    max_month = df_base["opened_at"].max().to_period("M")
    months = pd.period_range(min_month, max_month, freq="M")
else:
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
pio.templates.default = "plotly_dark"
server = app.server
app.title = "Tablero de Incidentes"

# ----------------------------
# 3) Layout (parte inicial con filtros)
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
                        html.Button("Reset", id="btn-reset", className="btn-secondary", n_clicks=0),
                        html.Hr(),
                        html.Div("Navegación"),


                                            ],
                                        ),

                                html.Div(
                    className="content",
                    children=[
                        dcc.Tabs(id="tabs", value="tab-resumen", children=[
                            dcc.Tab(label="Resumen", value="tab-resumen", children=[
                                html.Div(className="card", children=[
                                    html.H3("Evolución semanal de incidentes"),
                                    dcc.Graph(id="fig-series",
                                        style={"height": "340px"},
                                        config={"displayModeBar": False, "responsive": True}),
                                ]),
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[
                                        html.H3("Distribución por prioridad"),
                                        dcc.Graph(id="fig-prioridad",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                    html.Div(className="card", children=[
                                        html.H3("Top grupos por volumen"),
                                        dcc.Graph(id="fig-grupos",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                ]),
                            ]),
                            dcc.Tab(label="SLA & Calidad", value="tab-sla", children=[
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[
                                        html.H3("Cumplimiento SLA"),
                                        dcc.Graph(id="fig-sla",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                    html.Div(className="card", children=[
                                        html.H3("Nivel de servicio por tipo de contacto"),
                                        dcc.Graph(id="fig-contacto",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                ]),
                                html.Div(className="card", children=[
                                    html.H3("Nivel de servicio por tipo de urgencia"),
                                    dcc.Graph(id="fig-urgencia",
                                              style={"height": "340px"},
                                              config={"displayModeBar": False, "responsive": True}),
                                ]),
                            ]),
                            dcc.Tab(label="Operación & Tiempos", value="tab-tiempo", children=[
                                html.Div(className="card", children=[
                                    html.H3("Distribución del tiempo de resolución (horas)"),
                                    html.Label("Número de bins"),
                                    dcc.Slider(
                                        id="bins-slider",
                                        min=10, max=1000, step=10, value=500,
                                        marks={i: str(i) for i in [10, 100, 500, 1000]}
                                    ),
                                    html.Label("Límite máximo en el eje X:"),
                                    dcc.Input(
                                        id="xmax-input",
                                        type="number",
                                        value=200,
                                        min=1, step=10, debounce=True
                                    ),
                                    dcc.Graph(id="fig-resolution-time"),
                                ]),
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[
                                        html.H3("Tiempo de resolución promedio por categoría"),
                                        html.Label("Número de categorías a mostrar"),
                                        dcc.Input(
                                            id="topn-input",
                                            type="number",
                                            value=10,
                                            min=1, step=1, debounce=True
                                        ),
                                        dcc.Graph(id="fig-top-categorias",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                    html.Div(className="card", children=[
                                        html.H3("Scatter: Categoría vs Tiempo de Resolución"),
                                        dcc.Graph(id="fig-scatter-categoria",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                ]),
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[
                                        html.H3("Reassignment Count promedio por Prioridad"),
                                        dcc.Graph(id="fig-reassign-prioridad",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                    html.Div(className="card", children=[
                                        html.H3("Distribución de Reassignment Count por Prioridad"),
                                        dcc.Graph(id="fig-violin-reassign",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                    ]),
                                ]),
                            ]),
                            dcc.Tab(label="Datos", value="tab-datos", children=[
                                html.Div(className="card", children=[
                                    html.H3("Tabla (vista previa)"),
                                    dash_table.DataTable(
                                        id="tabla",
                                        page_size=12,
                                        filter_action="native",
                                        sort_action="native",
                                        style_table={"overflowX": "auto"},
                                        style_cell={
                                            "backgroundColor": "#111827",   # fondo oscuro
                                            "color": "#F9FAFB",             # texto claro
                                            "border": "1px solid #374151",  # bordes gris oscuro
                                            "fontFamily": "Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial",
                                            "fontSize": 13,
                                        },
                                        style_header={
                                            "backgroundColor": "#1F2937",
                                            "color": "#F9FAFB",
                                            "fontWeight": "bold",
                                            "border": "1px solid #4B5563",
                                        },
                                        style_data_conditional=[
                                            {"if": {"row_index": "odd"}, "backgroundColor": "#1E293B"}
                                        ]
                                    )

                                ]),
                            ]),
                            dcc.Tab(label="Modelo de predicción", value="tab-modelo", children=[
                                html.Div(className="card", children=[
                                    html.Div(className="card-header", children=[
                                        html.H3("Inputs del modelo"),
                                        html.P("Ingresa valores numéricos (las variables categóricas deben estar codificadas numéricamente).", className="note")
                                    ]),
                                    html.Div(className="form-grid form-grid-3", children=[
                                        # Columna 1
                                        html.Div(className="form-card", children=[
                                            html.Div(className="input-group", children=[
                                                html.Label("active"),
                                                dcc.RadioItems(
                                                    id="in-active",
                                                    options=[{"label":"0","value":0},{"label":"1","value":1}],
                                                    value=1,
                                                    inline=True,
                                                    className="radio-segment"
                                                ),
                                                html.Small("0 = inactivo, 1 = activo", className="help")
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("reassignment_count"),
                                                dcc.Input(id="in-reassignment", type="number", value=2, min=0, step=1,
                                                        className="input", placeholder="p. ej. 2", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("reopen_count"),
                                                dcc.Input(id="in-reopen", type="number", value=0, min=0, step=1,
                                                        className="input", placeholder="p. ej. 1", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("sys_mod_count"),
                                                dcc.Input(id="in-sysmod", type="number", value=12, min=0, step=1,
                                                        className="input", placeholder="p. ej. 5", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("sys_updated_by (cod.)"),
                                                dcc.Input(id="in-sysupdatedby", type="number", value=100, step=1,
                                                        className="input", placeholder="ID codificado", debounce=True)
                                            ]),
                                        ]),

                                        # Columna 2
                                        html.Div(className="form-card", children=[
                                            html.Div(className="input-group", children=[
                                                html.Label("contact_type (cod.)"),
                                                dcc.Input(id="in-contacttype", type="number", value=3, step=1,
                                                        className="input", placeholder="p. ej. 3", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("category (cod.)"),
                                                dcc.Input(id="in-category", type="number", value=5, step=1,
                                                        className="input", placeholder="p. ej. 12", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("priority (cod.)"),
                                                dcc.Input(id="in-priority", type="number", value=2, step=1,
                                                        className="input", placeholder="p. ej. 2", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("assignment_group (cod.)"),
                                                dcc.Input(id="in-assignmentgroup", type="number", value=20, step=1,
                                                        className="input", placeholder="ID codificado", debounce=True)
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("assigned_to (cod.)"),
                                                dcc.Input(id="in-assignedto", type="number", value=50, step=1,
                                                        className="input", placeholder="ID codificado", debounce=True)
                                            ]),
                                        ]),

                                        # Columna 3
                                        html.Div(className="form-card", children=[
                                            html.Div(className="input-group", children=[
                                                html.Label("u_priority_confirmation"),
                                                dcc.RadioItems(
                                                    id="in-uconfirm",
                                                    options=[{"label":"0","value":0},{"label":"1","value":1}],
                                                    value=1,
                                                    inline=True,
                                                    className="radio-segment"
                                                ),
                                                html.Small("0 = no confirmado, 1 = confirmado", className="help")
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("notify"),
                                                dcc.RadioItems(
                                                    id="in-notify",
                                                    options=[{"label":"0","value":0},{"label":"1","value":1}],
                                                    value=0,
                                                    inline=True,
                                                    className="radio-segment"
                                                ),
                                                html.Small("0 = sin notificar, 1 = notificado", className="help")
                                            ]),
                                            html.Div(className="input-group", children=[
                                                html.Label("resolved_by (cod.)"),
                                                dcc.Input(id="in-resolvedby", type="number", value=77, step=1,
                                                        className="input", placeholder="ID codificado", debounce=True)
                                            ]),
                                        ]),
                                    ]),
                                ]),
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[
                                        html.H3("Tiempo de resolución predicho (horas)"),
                                        html.Div(id="pred-valor", className="big-number"),
                                        html.P("Salida del modelo lineal (no negativa).", className="note"),
                                    ]),
                                    html.Div(className="card", children=[
                                        html.H3("Indicador"),
                                        dcc.Graph(id="pred-gauge",
                                                  style={"height": "340px"},
                                                  config={"displayModeBar": False, "responsive": True}),
                                        html.P("Escala automática según el valor predicho.", className="note"),
                                    ]),
                                ]),
                            ]),
                            dcc.Tab(label="Simulación", value="tab-simulacion", children=[
                                html.Div(className="card", children=[
                                    html.Div(className="card-header", children=[
                                        html.H3("Simulación de incidentes"),
                                        html.P("Genera datos sintéticos con la misma estética del tablero.", className="note")
                                    ]),
                                    html.Div(className="form-grid form-grid-3", children=[
                                        html.Div(className="input-group", children=[
                                            html.Label("Número de incidentes a simular"),
                                            dcc.Input(
                                                id="in-n-simul", type="number", value=500, min=100, step=100,
                                                className="input", debounce=True, placeholder="p. ej. 500"
                                            ),
                                            html.Small("Cambia el valor para regenerar las gráficas.", className="help")
                                        ]),
                                    ]),
                                ]),
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[dcc.Graph(id="simul-hist")]),
                                    html.Div(className="card", children=[dcc.Graph(id="simul-cat")]),
                                ]),
                                html.Div(className="grid-2", children=[
                                    html.Div(className="card", children=[dcc.Graph(id="simul-scatter")]),
                                    html.Div(className="card", children=[dcc.Graph(id="simul-contact")]),
                                ]),
                                html.Div(className="card", children=[dcc.Graph(id="simul-prioridad")]),
                            ])

                        ])
                    ]

                ),
            ],
        ),
        html.Footer(className="footer", children="2025 · Equipo Analítica"),
    ],
)

# ----------------------------
# 4) Callbacks
# ----------------------------

@callback(
    Output("store-data", "data"),
    Output("month-range", "value"),
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

    # Recalcula months por si cambió el CSV
    if "opened_at" in df.columns and df["opened_at"].notna().any():
        min_m = df["opened_at"].min().to_period("M")
        max_m = df["opened_at"].max().to_period("M")
        rng = pd.period_range(min_m, max_m, freq="M")
        new_value = [0, len(rng) - 1]
    else:
        new_value = [0, len(months) - 1]

    return df.to_dict("records"), new_value, None, None, None, None


@callback(
    Output("fig-series", "figure"),
    Output("fig-prioridad", "figure"),
    Output("fig-grupos", "figure"),
    Output("fig-sla", "figure"),
    Output("fig-contacto", "figure"),
    Output("fig-urgencia", "figure"),
    Output("fig-resolution-time", "figure"),
    Output("fig-top-categorias", "figure"),
    Output("fig-scatter-categoria", "figure"),
    Output("fig-reassign-prioridad", "figure"),
    Output("fig-violin-reassign", "figure"),
    Output("tabla", "data"),
    Output("tabla", "columns"),
    Input("store-data", "data"),        
    Input("month-range", "value"),         
    Input("dd-prioridad", "value"),     
    Input("dd-categoria", "value"),     
    Input("dd-grupo", "value"),         
    Input("dd-location", "value"),    
    Input("bins-slider", "value"),      
    Input("xmax-input", "value"),     
    Input("topn-input", "value"),     
)




def actualizar(data_records, month_range_idx, prioridades, categorias, grupos, locations,
               bins, xmax, topn):

    df = pd.DataFrame(data_records)

    # Normaliza fechas
    for col in ["opened_at", "resolved_at", "closed_at", "sys_updated_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # Filtro active == False
    if "active" in df.columns:
        df = df[df["active"] == False]

    # --- Filtro por meses ---
    if isinstance(month_range_idx, (list, tuple)) and len(month_range_idx) == 2:
        i_start, i_end = int(month_range_idx[0]), int(month_range_idx[1])
        i_start = max(0, min(i_start, len(months) - 1))
        i_end   = max(0, min(i_end, len(months) - 1))
        start_dt = months[i_start].to_timestamp(how="start")
        end_dt   = months[i_end].to_timestamp(how="end")
        if "opened_at" in df.columns and df["opened_at"].notna().any():
            df = df[(df["opened_at"] >= start_dt) & (df["opened_at"] <= end_dt)]

    # Helper para filtros múltiples
    def apply_multi_filter(frame, col, values):
        if col in frame.columns and values:
            if "__TOTAL__" in (values if isinstance(values, (list, tuple, set)) else [values]):
                return frame
            return frame[frame[col].astype("string").isin(pd.Series(values, dtype="string"))]
        return frame

    # Aplica filtros
    df = apply_multi_filter(df, "priority", prioridades)
    df = apply_multi_filter(df, "category", categorias)
    df = apply_multi_filter(df, "assignment_group", grupos)
    df = apply_multi_filter(df, "location", locations)

    # =====================
    # 2) GRÁFICOS
    # =====================

    # Serie semanal
    if "opened_at" in df.columns and df["opened_at"].notna().any() and len(df) > 0:
        tmp = (df.set_index("opened_at").assign(cnt=1).resample("W")["cnt"].sum().reset_index())
        fig_series = px.line(tmp, x="opened_at", y="cnt", markers=True, title="Incidentes por semana")
    else:
        fig_series = go.Figure().update_layout(title="Incidentes por semana (sin datos)")

    # Distribución por prioridad
    if "priority" in df.columns and df["priority"].notna().any():
        pr = df["priority"].value_counts().rename_axis("priority").reset_index(name="count")
        fig_prio = px.bar(pr, x="priority", y="count", title="Distribución por prioridad")
    else:
        fig_prio = go.Figure().update_layout(title="Distribución por prioridad (sin datos)")

    # Top grupos
    if "assignment_group" in df.columns and df["assignment_group"].notna().any():
        top_grupos = df["assignment_group"].value_counts().head(10).rename_axis("assignment_group").reset_index(name="count")
        fig_grp = px.bar(top_grupos, y="assignment_group", x="count", orientation="h", title="Top 10 grupos por volumen")
    else:
        fig_grp = go.Figure().update_layout(title="Top grupos (sin datos)")

    # Cumplimiento SLA
    if "made_sla" in df.columns and df["made_sla"].notna().any():
        valores = df["made_sla"].value_counts()
        fig_sla = go.Figure(data=[go.Pie(labels=["True", "False"], values=[valores.get(True, 0), valores.get(False, 0)])])
    else:
        fig_sla = go.Figure().update_layout(title="Cumplimiento SLA (sin datos)")

    # Nivel de servicio por contacto
    if {"contact_type", "made_sla"}.issubset(df.columns):
        conteo = df.groupby(["contact_type", "made_sla"]).size().unstack(fill_value=0)
        if True in conteo.columns:
            conteo["nivel_servicio"] = conteo[True] / conteo.sum(axis=1) * 100
            fig_contacto = px.bar(conteo, x=conteo.index, y="nivel_servicio", title="Servicio por tipo de contacto")
        else:
            fig_contacto = go.Figure().update_layout(title="Servicio por contacto (sin datos)")
    else:
        fig_contacto = go.Figure().update_layout(title="Servicio por contacto (sin datos)")

    # Nivel de servicio por urgencia
    if {"urgency", "made_sla"}.issubset(df.columns):
        conteo2 = df.groupby(["urgency", "made_sla"]).size().unstack(fill_value=0)
        if True in conteo2.columns:
            conteo2["nivel_servicio"] = conteo2[True] / conteo2.sum(axis=1) * 100
            fig_urgencia = px.bar(conteo2, x=conteo2.index, y="nivel_servicio", title="Servicio por urgencia")
        else:
            fig_urgencia = go.Figure().update_layout(title="Servicio por urgencia (sin datos)")
    else:
        fig_urgencia = go.Figure().update_layout(title="Servicio por urgencia (sin datos)")

    # Histograma de tiempos de resolución
    if {"opened_at", "resolved_at"}.issubset(df.columns):
        df2 = df.copy()
        df2["resolution_time"] = (pd.to_datetime(df2["resolved_at"]) - pd.to_datetime(df2["opened_at"])).dt.total_seconds() / 3600
        df2 = df2.dropna(subset=["resolution_time"])
        if len(df2) > 0:
            fig_res = px.histogram(df2, x="resolution_time", nbins=bins or 500, title="Distribución del tiempo de resolución (h)")
            if xmax: fig_res.update_xaxes(range=[0, xmax])
        else:
            fig_res = go.Figure().update_layout(title="Distribución resolución (sin datos)")
    else:
        fig_res = go.Figure().update_layout(title="Distribución resolución (sin datos)")

    # Top categorías (define df2 local aquí también)
    if {"category", "opened_at", "resolved_at"}.issubset(df.columns):
        df2 = df.copy()
        df2["resolution_time"] = (pd.to_datetime(df2["resolved_at"]) - pd.to_datetime(df2["opened_at"])).dt.total_seconds() / 3600
        promedio_por_categoria = df2.groupby("category")["resolution_time"].mean().sort_values(ascending=False)
        try:
            topn_val = int(topn)
        except (TypeError, ValueError):
            topn_val = 10
        top_cats = promedio_por_categoria.tail(topn_val)
        fig_top_cat = px.bar(x=top_cats.index, y=top_cats.values, title=f"Top {topn_val} categorías con menor TTR")
    else:
        fig_top_cat = go.Figure().update_layout(title="Top categorías (sin datos)")

    # Scatter categoría numérica vs tiempo (df2 local)
    if {"category", "opened_at", "resolved_at"}.issubset(df.columns):
        df2 = df.copy()
        df2["resolution_time"] = (pd.to_datetime(df2["resolved_at"]) - pd.to_datetime(df2["opened_at"])).dt.total_seconds() / 3600
        df2["categoria_num"] = df2["category"].str.extract(r"(\d+)$").astype(float)
        df2_filtrado = df2.dropna(subset=["categoria_num", "resolution_time"])
        if len(df2_filtrado) > 0:
            fig_scatter = px.scatter(df2_filtrado, x="categoria_num", y="resolution_time", opacity=0.5, title="Scatter Categoría vs Tiempo")
        else:
            fig_scatter = go.Figure().update_layout(title="Scatter Categoría vs Tiempo (sin datos)")
    else:
        fig_scatter = go.Figure().update_layout(title="Scatter Categoría vs Tiempo (sin datos)")

    # Reassignment promedio por prioridad
    if {"priority", "reassignment_count"}.issubset(df.columns):
        promedio_por_prioridad = df.groupby("priority")["reassignment_count"].mean().sort_values(ascending=False)
        fig_reassign = px.bar(x=promedio_por_prioridad.index, y=promedio_por_prioridad.values, title="Reassignment promedio por prioridad")
    else:
        fig_reassign = go.Figure().update_layout(title="Reassignment (sin datos)")

    # Violinplot
    if {"priority", "reassignment_count"}.issubset(df.columns):
        df_violin = df.dropna(subset=["priority", "reassignment_count"])
        if len(df_violin) > 0:
            fig_violin = px.violin(df_violin, x="priority", y="reassignment_count", box=True, title="Distribución Reassignment por prioridad")
        else:
            fig_violin = go.Figure().update_layout(title="Distribución Reassignment (sin datos)")
    else:
        fig_violin = go.Figure().update_layout(title="Distribución Reassignment (sin datos)")

    # =====================
    # Tabla
    # =====================
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
        fig_res, fig_top_cat, fig_scatter,
        fig_reassign, fig_violin,
        tabla.to_dict("records"), columns
    )



@callback(
    Output("simul-hist", "figure"),
    Output("simul-cat", "figure"),
    Output("simul-scatter", "figure"),
    Output("simul-contact", "figure"),
    Output("simul-prioridad", "figure"),
    Input("in-n-simul", "value")
)
def actualizar_simulacion(n):
    try:
        n = int(n) if n and int(n) > 0 else 500
    except Exception:
        n = 500
    return simular_incidentes(n)



@callback(
    Output("pred-valor", "children"),
    Output("pred-gauge", "figure"),
    Input("in-active", "value"),
    Input("in-reassignment", "value"),
    Input("in-reopen", "value"),
    Input("in-sysmod", "value"),
    Input("in-sysupdatedby", "value"),
    Input("in-contacttype", "value"),
    Input("in-category", "value"),
    Input("in-priority", "value"),
    Input("in-assignmentgroup", "value"),
    Input("in-assignedto", "value"),
    Input("in-uconfirm", "value"),
    Input("in-notify", "value"),
    Input("in-resolvedby", "value"),
)
def actualizar_pred(active, reassignment_count, reopen_count, sys_mod_count,
                    sys_updated_by, contact_type, category, priority,
                    assignment_group, assigned_to, u_priority_confirmation,
                    notify, resolved_by):
    # Sanitiza/convierte
    active = int(_num_or_zero(active))
    u_priority_confirmation = int(_num_or_zero(u_priority_confirmation))
    notify = int(_num_or_zero(notify))

    reassignment_count = _num_or_zero(reassignment_count)
    reopen_count = _num_or_zero(reopen_count)
    sys_mod_count = _num_or_zero(sys_mod_count)
    sys_updated_by = _num_or_zero(sys_updated_by)
    contact_type = _num_or_zero(contact_type)
    category = _num_or_zero(category)
    priority = _num_or_zero(priority)
    assignment_group = _num_or_zero(assignment_group)
    assigned_to = _num_or_zero(assigned_to)
    resolved_by = _num_or_zero(resolved_by)

    yhat = predecir_tiempo(
        active, reassignment_count, reopen_count, sys_mod_count,
        sys_updated_by, contact_type, category, priority,
        assignment_group, assigned_to, u_priority_confirmation,
        notify, resolved_by
    )

    # Texto grande
    texto = f"{yhat:,.2f} h"

    # Indicador (gauge-like con indicador numérico)
    max_scale = max(10.0, yhat * 1.2)  # escala simple
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=yhat,
        number={"suffix":" h"},
        gauge={
            "axis":{"range":[0, max_scale]},
            "bar":{"color":"#2563EB"},
            "steps":[
                {"range":[0, max_scale*0.33], "color":"#DBEAFE"},
                {"range":[max_scale*0.33, max_scale*0.66], "color":"#BFDBFE"},
                {"range":[max_scale*0.66, max_scale], "color":"#93C5FD"},
            ]
        }
    ))
    return texto, fig


import plotly.express as px
import plotly.graph_objects as go

def simular_incidentes(n=500):
    np.random.seed(42)

    data = pd.DataFrame({
        "active": np.random.randint(0, 2, n),
        "reassignment_count": np.random.poisson(2, n),
        "reopen_count": np.random.poisson(1, n),
        "sys_mod_count": np.random.poisson(10, n),
        "sys_updated_by": np.random.randint(1, 500, n),
        "contact_type": np.random.randint(1, 6, n),   # 1..5
        "category": np.random.randint(1, 64, n),      # 1..63
        "priority": np.random.randint(1, 5, n),       # 1..4
        "assignment_group": np.random.randint(1, 50, n),
        "assigned_to": np.random.randint(1, 100, n),
        "u_priority_confirmation": np.random.randint(0, 2, n),
        "notify": np.random.randint(0, 2, n),
        "resolved_by": np.random.randint(1, 100, n)
    })

    # Predicción con tu modelo lineal
    data["resolved_time"] = data.apply(lambda row: predecir_tiempo(
        row.active, row.reassignment_count, row.reopen_count, row.sys_mod_count,
        row.sys_updated_by, row.contact_type, row.category, row.priority,
        row.assignment_group, row.assigned_to, row.u_priority_confirmation,
        row.notify, row.resolved_by
    ), axis=1)

    # KPI simple de cumplimiento (comparado contra la media)
    media = data["resolved_time"].mean()
    data["cumple_SLA"] = data["resolved_time"] < media

    # 1) Histograma resolved_time con línea de media
    fig_hist = px.histogram(
        data, x="resolved_time", nbins=30, title="Distribución de tiempos de resolución (h)", opacity=0.9
    )
    fig_hist.add_vline(
        x=media, line_dash="dash", line_color="#F87171",
        annotation_text=f"Media {media:.1f} h", annotation_position="top right"
    )
    style_fig(fig_hist)

    # 2) Strip por categoría
    fig_cat = px.strip(
        data, x="category", y="resolved_time",
        title="Tiempo de resolución por categoría"
    )
    fig_cat.update_traces(jitter=0.3)
    fig_cat.update_xaxes(dtick=10)
    style_fig(fig_cat)

    # 3) Reasignaciones vs prioridad (tamaño por tiempo resuelto)
    fig_scatter = px.scatter(
        data, x="reassignment_count", y="priority", size="resolved_time",
        opacity=0.6, title="Reasignaciones vs prioridad (tamaño = tiempo resolución)"
    )
    style_fig(fig_scatter)

    # 4) Cumplimiento por tipo de contacto
    contact_labels = {1:"Phone", 2:"Email", 3:"Self service", 4:"Direct opening", 5:"IVR"}
    tmp_c = (data.groupby("contact_type")["cumple_SLA"].mean() * 100).rename(index=contact_labels).reset_index()
    tmp_c.columns = ["contact_type", "cumple_SLA"]
    fig_contact = px.bar(
        tmp_c, x="contact_type", y="cumple_SLA", text="cumple_SLA",
        title="Cumplimiento SLA por tipo de contacto (%)"
    )
    fig_contact.update_traces(texttemplate="%{text:.1f}%")
    fig_contact.update_yaxes(range=[0, 100])
    style_fig(fig_contact)

    # 5) Cumplimiento por prioridad
    priority_labels = {1:"1 - Critical", 2:"2 - High", 3:"3 - Moderate", 4:"4 - Low"}
    tmp_p = (data.groupby("priority")["cumple_SLA"].mean() * 100).rename(index=priority_labels).reset_index()
    tmp_p.columns = ["priority", "cumple_SLA"]
    fig_prio = px.bar(
        tmp_p, x="priority", y="cumple_SLA", text="cumple_SLA",
        title="Cumplimiento SLA por prioridad (%)"
    )
    fig_prio.update_traces(texttemplate="%{text:.1f}%")
    fig_prio.update_yaxes(range=[0, 100])
    style_fig(fig_prio)

    return fig_hist, fig_cat, fig_scatter, fig_contact, fig_prio












# ----------------------------
# 5) Entry point
# ----------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 8050)), debug=True)
