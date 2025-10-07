from __future__ import annotations
from datetime import datetime
import plotly.graph_objects as go
import plotly.io as pio
import dash
from dash import Dash, dcc, html, Output, Input

# ===== безопасный импорт данных: сначала пробуем "реалистичный", иначе штатный =====
try:
    from software import data_source_ext as ds  # type: ignore
except Exception:
    from software import data_source as ds  # fallback

# === Глобальная тема Plotly ===
pio.templates.default = "plotly_dark"

ASSETS_DIR = "/opt/smart-vent/assets"
GRAPH_CFG = {"displayModeBar": False, "responsive": True}

app = Dash(__name__, title="Smart Vent Dashboard",
           suppress_callback_exceptions=False,
           assets_folder=ASSETS_DIR)
server = app.server

# гарантируем запуск симуляции
try:
    ds.start_simulation()
except Exception:
    pass

def fig_line(x, y, name, ytitle, sec_y=False):
    tr = go.Scatter(x=x, y=y, name=name, mode="lines", line=dict(width=2))
    fig = go.Figure(tr)
    fig.update_layout(
        height=340, margin=dict(l=10,r=10,t=40,b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=12)),
        xaxis=dict(title="Время", tickformat="%H:%M:%S<br>%b %e"),
        yaxis=dict(title=ytitle),
    )
    if sec_y:
        fig.update_layout(yaxis2=dict(title=ytitle, overlaying="y", side="right", showgrid=False))
    return fig

def header():
    return html.Div(className="header", children=[
        html.Div(className="gears", children=[html.Div(className="gear")]),
        html.Div(className="brand", children=[html.H1("Smart Vent Dashboard")]),
    ])

def kpi(label, value, unit=""):
    return html.Div(className="card", children=[
        html.Div(label, className="label"),
        html.Div(f"{value}{unit}", className="value"),
    ])

def kpi_grid(df):
    last = df.iloc[-1]
    return html.Div(className="kpi-grid", children=[
        kpi("CO₂",        f"{int(last.co2)}", " ppm"),
        kpi("Температура",f"{last.temp:.1f}", " °C"),
        kpi("Влажность",  f"{int(last.rh)}", " %"),
        kpi("PM2.5",      f"{last.pm25:.1f}", " μг/м³"),
        kpi("Люди",       f"{int(last.people)}", ""),
        kpi("Вентилятор", f"{int(last.fan)}", " %"),
        kpi("Клапан",     f"{int(last.valve)}", " %"),
        kpi("Режим",      "auto"),
    ])

def charts(df):
    xs = df.index
    f_co2 = fig_line(xs, df.co2, "CO₂, ppm", "CO₂, ppm")
    f_t   = fig_line(xs, df.temp, "T, °C", "T, °C", sec_y=True)
    f_rh  = fig_line(xs, df.rh, "RH, %", "RH, %")
    f_pm  = fig_line(xs, df.pm25, "PM2.5", "μг/м³")
    f_act = go.Figure()
    f_act.add_scatter(x=xs, y=df.fan,   name="Fan %", mode="lines")
    f_act.add_scatter(x=xs, y=df.valve, name="Valve %", mode="lines")
    for f in (f_t, f_rh, f_pm, f_act):
        f.update_layout(height=340, margin=dict(l=10,r=10,t=45,b=40))
    return html.Div(children=[
        html.Div("Онлайн-показатели (последние 10 минут)", className="section-title"),
        html.Div(className="plot-card", children=[dcc.Graph(figure=f_co2, config=GRAPH_CFG)]),
        html.Div(className="plot-card", children=[dcc.Graph(figure=f_t,   config=GRAPH_CFG)]),
        html.Div(className="plot-card", children=[dcc.Graph(figure=f_rh,  config=GRAPH_CFG)]),
        html.Div(className="plot-card", children=[dcc.Graph(figure=f_pm,  config=GRAPH_CFG)]),
        html.Div(className="plot-card", children=[dcc.Graph(figure=f_act, config=GRAPH_CFG)]),
    ])

app.layout = html.Div(children=[
    header(),
    dcc.Interval(id="tick", interval=2_000, n_intervals=0),
    html.Div(id="kpis"),
    html.Div(id="plots")
])

@app.callback(Output("kpis","children"), Input("tick","n_intervals"))
def _upd_kpi(_):
    df = ds.get_last_df(600)
    return kpi_grid(df)

@app.callback(Output("plots","children"), Input("tick","n_intervals"))
def _upd_plots(_):
    df = ds.get_last_df(600)
    return charts(df)

if __name__ == "__main__":
    app.run_server("0.0.0.0", 8050, debug=False)
