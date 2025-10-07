# software/dash_app.py
from __future__ import annotations
import os
from datetime import datetime
from typing import List, Tuple

import dash
from dash import Dash, dcc, html, Input, Output, State, no_update
import plotly.graph_objects as go

from software.data_source import DataSource

# ----------------- Глобальный источник данных -----------------
DATA: DataSource = DataSource(max_points=600, step_sec=1.0)

# ----------------- Создаём Dash/WSGI -----------------
external_stylesheets = [
    "https://cdnjs.cloudflare.com/ajax/libs/modern-normalize/2.0.0/modern-normalize.min.css"
]
app: Dash = Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=False,
    title="Smart Vent Dashboard",
)
server = app.server  # для waitress: software.dash_app:app.server

# ----------------- Вспомогалки -----------------
def build_figure(series: List[Tuple[float, float]]) -> go.Figure:
    if not series:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=10),
            height=420,
            title="Ожидание данных… Нажмите «Пуск»",
        )
        return fig

    xs = [datetime.fromtimestamp(t) for t, _ in series]
    ys = [y for _, y in series]
    fig = go.Figure(
        data=[go.Scatter(x=xs, y=ys, mode="lines+markers", name="Поток")]
    )
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        height=420,
        title="Живой поток данных",
        xaxis_title="Время",
        yaxis_title="Значение",
    )
    return fig

def badge(text: str, color: str = "#10b981"):  # зелёный по умолчанию
    return html.Span(
        text,
        style={
            "display": "inline-block",
            "padding": "4px 10px",
            "borderRadius": "999px",
            "background": color,
            "color": "white",
            "fontWeight": 600,
            "fontSize": "12px",
            "letterSpacing": "0.3px",
        },
    )

# ----------------- UI -----------------
app.layout = html.Div(
    style={
        "maxWidth": "1024px",
        "margin": "20px auto",
        "padding": "16px",
        "fontFamily": "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Ubuntu,Arial",
    },
    children=[
        html.H1("Smart Vent — мониторинг", style={"marginBottom": "8px"}),
        html.Div(
            [
                html.Div("Состояние:", style={"marginRight": "8px"}),
                html.Div(id="state-badge"),
            ],
            style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "12px"},
        ),

        html.Div(
            [
                html.Button("Пуск", id="btn-start", n_clicks=0, className="btn"),
                html.Button("Стоп", id="btn-stop", n_clicks=0, className="btn", style={"marginLeft": "8px"}),
                html.Button("Сброс", id="btn-reset", n_clicks=0, className="btn", style={"marginLeft": "8px"}),
                html.Span(id="hint", style={"marginLeft": "16px", "color": "#6b7280"}),
            ],
            style={"marginBottom": "12px"},
        ),

        dcc.Graph(id="live-graph", figure=build_figure([])),
        dcc.Interval(id="tick", interval=1000, n_intervals=0, disabled=True),

        # Хранилище состояния «идёт ли поток»
        dcc.Store(id="is-running", data=False),
    ],
)

# ----------------- Callbacks -----------------

@app.callback(
    Output("is-running", "data"),
    Output("tick", "disabled"),
    Output("hint", "children"),
    Input("btn-start", "n_clicks"),
    Input("btn-stop", "n_clicks"),
    prevent_initial_call=False,
)
def start_stop(n_start: int, n_stop: int):
    """
    Управляем потоком и интервалом.
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        # первый рендер страницы: читаем текущее состояние генератора
        running_now = DATA.is_running()
        return running_now, (not running_now), ("Нажмите «Пуск» для старта." if not running_now else "Поток идёт…")

    trig = ctx.triggered[0]["prop_id"].split(".")[0]
    if trig == "btn-start":
        if not DATA.is_running():
            DATA.start()
        return True, False, "Поток идёт…"
    elif trig == "btn-stop":
        if DATA.is_running():
            DATA.stop()
        return False, True, "Остановлено."
    return no_update, no_update, no_update


@app.callback(
    Output("live-graph", "figure"),
    Output("state-badge", "children"),
    Input("tick", "n_intervals"),
    State("is-running", "data"),
    prevent_initial_call=False,
)
def on_tick(_n, is_running: bool):
    """
    Раз в секунду перерисовываем график, если «Пуск».
    """
    series = DATA.get_series()
    fig = build_figure(series)
    badge_node = badge("RUNNING", "#10b981") if is_running else badge("STOPPED", "#ef4444")
    return fig, badge_node


@app.callback(
    Output("live-graph", "figure"),
    Output("hint", "children"),
    Input("btn-reset", "n_clicks"),
    State("is-running", "data"),
    prevent_initial_call=True,
)
def on_reset(_n, is_running: bool):
    DATA.reset()
    text = "Сброшено. " + ("Поток идёт…" if is_running else "Нажмите «Пуск» для старта.")
    return build_figure([]), text


# ----------------- (Необязательно) Маршрут для быстрой проверки буфера -----------------
@server.route("/api/debug/bufsize")
def _bufsize():
    return {"running": DATA.is_running(), "size": len(DATA.get_series())}


# ----------------- локальный запуск (для разработки) -----------------
if __name__ == "__main__":
    # Локально можно тестировать без waitress:
    app.run_server(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=True)
