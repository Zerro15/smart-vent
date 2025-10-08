from __future__ import annotations
from dash import html, dcc, Input, Output, State, exceptions
from datetime import datetime
from zoneinfo import ZoneInfo

# используем реалистичный источник, но безопасно
try:
    from software import data_source_ext as ds
except Exception:
    from software import data_source as ds  # fallback

TZ = ZoneInfo("Asia/Yekaterinburg")

def _parse_groups(s: str | None) -> list[int]:
    if not s:
        return []
    res = []
    for part in s.split(","):
        part = part.strip()
        if part.isdigit():
            res.append(int(part))
    return res

def attach_controls(app):
    """Вставляет панель кнопок в layout и регистрирует коллбеки."""
    quick_actions = html.Div(className="btn-row", children=[
        html.Button("Применить", id="btn-apply", n_clicks=0, className="btn-primary"),
        html.Button("Сегодня (авто)", id="btn-auto-today", n_clicks=0, className="btn-ghost"),
    ])

    # Пытаемся вставить панель сразу после блока контролов (или в начало)
    try:
        kids = app.layout.children  # html.Div([...])
        # ищем первое место после «controls»-карточки; если нет — добавим в начало
        insert_pos = 1 if isinstance(kids, list) else 0
        if isinstance(kids, list):
            kids.insert(insert_pos, quick_actions)
        else:
            # если по какой-то причине children не список, оборачиваем
            app.layout.children = [quick_actions, app.layout.children]
    except Exception:
        # перестраховка: просто обернём текущий layout
        app.layout = html.Div([quick_actions, app.layout])

    # --- Кнопка «Сегодня (авто)» ---
    @app.callback(
        Output("pick-date", "date"),
        Output("auto-mode", "value"),
        Input("btn-auto-today", "n_clicks"),
        prevent_initial_call=True,
    )
    def on_auto_today(n_clicks):
        if not n_clicks:
            raise exceptions.PreventUpdate
        today = datetime.now(TZ).date().isoformat()
        try:
            if hasattr(ds, "set_auto"):
                ds.set_auto(True)
            if hasattr(ds, "set_date"):
                ds.set_date(today)
        except Exception:
            pass
        return today, ["on"]

    # --- Кнопка «Применить» ---
    @app.callback(
        Output("btn-apply", "n_clicks"),  # просто сбрасываем счётчик кликов
        Input("btn-apply", "n_clicks"),
        State("pick-date", "date"),
        State("pick-shift", "value"),
        State("class-size", "value"),
        State("group-lessons", "value"),
        State("auto-mode", "value"),
        prevent_initial_call=True,
    )
    def on_apply(n_clicks, date_iso, shift, size, groups_str, auto_value):
        if not n_clicks:
            raise exceptions.PreventUpdate

        auto = "on" in (auto_value or [])
        groups = _parse_groups(groups_str or "")

        try:
            if hasattr(ds, "set_scenario"):
                ds.set_scenario(
                    date=date_iso,
                    shift=int(shift or 1),
                    class_size=int(size or 30),
                    group_lessons=groups,
                    auto=auto,
                )
            else:
                if hasattr(ds, "set_date") and date_iso: ds.set_date(date_iso)
                if hasattr(ds, "set_shift") and shift is not None: ds.set_shift(int(shift))
                if hasattr(ds, "set_class_size") and size is not None: ds.set_class_size(int(size))
                if hasattr(ds, "set_group_lessons"): ds.set_group_lessons(groups)
                if hasattr(ds, "set_auto"): ds.set_auto(auto)
        except Exception:
            # не проваливаем сервис, пусть обновление графиков сделает Interval
            pass

        return 0  # сброс кликов
