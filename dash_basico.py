from dash import Dash, dcc, html, dash_table
import plotly.express as px
import pandas as pd

# -------------------------
# 1) Cargar datos
# -------------------------
DATA_PATH = "cleaned_incident_event_log.csv"

df = pd.read_csv(DATA_PATH, dayfirst=True)

# Parsear fechas
for col in ["opened_at", "resolved_at"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

# Calcular TTR
if {"opened_at", "resolved_at"}.issubset(df.columns):
    df["ttr_hours"] = (df["resolved_at"] - df["opened_at"]).dt.total_seconds() / 3600

# -------------------------
# 2) KPIs
# -------------------------
n_incidentes = len(df)
sla_pct = (df["made_sla"].mean() * 100) if "made_sla" in df.columns else 0
ttr_mean = df["ttr_hours"].mean() if "ttr_hours" in df.columns else 0

# -------------------------
# 3) Gráfico simple
# -------------------------
if "opened_at" in df.columns:
    tmp = df.set_index("opened_at").assign(cnt=1).resample("W")["cnt"].sum().reset_index()
    fig = px.line(tmp, x="opened_at", y="cnt", title="Incidentes por semana")
else:
    fig = px.line(title="No hay columna 'opened_at'")

# -------------------------
# 4) App básica
# -------------------------
app = Dash(__name__)
app.title = "Incidentes - Básico"

app.layout = html.Div([
    html.H1("Dashboard de Incidentes (Versión Básica)"),

    html.Div([
        html.Div(f"Incidentes: {n_incidentes}", style={"margin": "10px"}),
        html.Div(f"% SLA cumplido: {sla_pct:.1f}%", style={"margin": "10px"}),
        html.Div(f"TTR medio (h): {ttr_mean:.1f}", style={"margin": "10px"}),
    ], style={"display": "flex", "gap": "20px"}),

    dcc.Graph(figure=fig),

    html.H3("Vista previa de datos"),
    dash_table.DataTable(
        data=df.head(20).to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_size=10,
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Arial", "fontSize": 13}
    )
])

if __name__ == "__main__":
    app.run(debug=True)
# ----------------------------
# Fin del código    