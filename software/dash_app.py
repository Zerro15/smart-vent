# software/dash_app.py
from __future__ import annotations
import os, time
from datetime import datetime

import dash
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd

from software import data_source as ds

# Стартуем симуляцию при импорте (безопасно к повторам)
ds.start_simulation()

external_stylesheets = [
    "https://cdnjs.cloudflare.com/ajax/libs/modern-normalize/2.0.0/modern-normalize.min.css"
]
app: Dash = Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    title="Smart Vent Dashboard",
)
server = app.server  # для waitress: software.dash_app:app.server

def make_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(
            template="plotly_white",
            height=460,
            margin=dict(l=10, r=10, t=40, b=10),
            title="Ожидание данных…",
        )
        return fig
    xs = [datetime.fromtimestamp(t) for t in df["ts"]]
    fig.add_trace(go.Scatter(x=xs, y=df["co2"], name="CO₂, ppm", mode="lines"))
    fig.add_trace(go.Scatter(x=xs, y=df["temp"], name="T, °C", mode="lines", yaxis="y2"))
    fig.add_trace(go.Scatter(x=xs, y=df["rh"],   name="RH, %", mode="lines", yaxis="y3"))
    fig.update_layout(
        template="plotly_white",
        height=460,
        margin=dict(l=10, r=10, t=40, b=10),
        title="Онлайн-показатели (последние 10 минут)",
        xaxis_title="Время",
        yaxis=dict(title="CO₂, ppm"),
        yaxis2=dict(title="T, °C", overlaying="y", side="right"),
        yaxis3=dict(title="RH, %", overlaying="y", side="right", position=0.97),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig

app.layout = html.Div(
    style={"maxWidth":"1100px","margin":"0 auto","padding":"12px"},
    children=[
        html.H1("Smart Vent Dashboard", style={"fontSize":"22px"}),
        html.Div(id="kpi"),
        dcc.Graph(id="chart"),
        dcc.Interval(id="tick", interval=1000, n_intervals=0),
    ]
)

@app.callback(
    Output("chart", "figure"),
    Output("kpi", "children"),
    Input("tick", "n_intervals"),
)
def update(_n):
    df = ds.get_last_df(600)
    fig = make_figure(df)
    if df.empty:
        kpi = "Нет данных…"
    else:
        last = df.iloc[-1]
        kpi = f"CO₂: {last.co2:.0f} ppm | T: {last.temp:.1f} °C | RH: {last.rh:.0f} % | PM2.5: {last.pm25:.1f} | Люди: {int(last.people)} | Вентилятор: {last.fan:.0f}% | Клапан: {last.valve:.0f}%"
    return fig, kpi

# Локальный запуск (на проде используется waitress с server)
if __name__ == "__main__":
    app.run_server(host="127.0.0.1", port=8050, debug=False)
