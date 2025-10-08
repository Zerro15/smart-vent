from __future__ import annotations
import threading, time, datetime as dt, math, random
import pandas as pd

# ====== Климат Челябинска по месяцам (упрощённые нормы) ======
CLIMATE = {
    1:  {"t": -16, "rh": 80},
    2:  {"t": -14, "rh": 78},
    3:  {"t":  -6, "rh": 72},
    4:  {"t":   3, "rh": 65},
    5:  {"t":  12, "rh": 58},
    6:  {"t":  18, "rh": 55},
    7:  {"t":  20, "rh": 55},
    8:  {"t":  18, "rh": 60},
    9:  {"t":  10, "rh": 65},
    10: {"t":   3, "rh": 75},
    11: {"t":  -6, "rh": 80},
    12: {"t": -12, "rh": 82},
}

# ====== Расписание (40 мин) ======
SHIFT1 = [("08:00","08:40",10),("08:50","09:30",15),("09:45","10:25",15),
          ("10:40","11:20",15),("11:35","12:15",10),("12:25","13:05",10),("13:15","13:55",0)]
SHIFT2 = [("14:00","14:40",15),("14:55","15:35",10),("15:45","16:25",10),
          ("16:35","17:15",10),("17:25","18:05",10),("18:15","18:55",0)]
SAT1   = [("08:00","08:40",5),("08:45","09:25",10),("09:35","10:15",10),
          ("10:25","11:05",10),("11:15","11:55",10),("12:05","12:45",10),("12:55","13:35",5),("13:40","14:20",0)]

# ====== Параметры модели ======
BUF_MIN = 8*60
K_CO2_PER_PERSON = 16          # ppm прирост за минуту на человека
VENT_CLEAR_PER_10 = 60         # ppm/мин выветривания на каждые 10% вентилятора
VALVE_GAIN_PER_10 = 25         # добавка естественной вентиляции на 10% клапана (эскиз)
ROOM_HEAT_PEOPLE = 0.015       # °C/мин на человека
TAU_TEMP = 25                  # инерция температуры (мин)
OUT_PM25 = 12.0                # фоновый PM2.5
CO2_TARGET = 800               # целевой CO₂
FAN_RAMP  = 0.12               # скорость авто изменения fan [%/тик]
VALVE_RAMP= 0.15               # скорость авто изменения valve [%/тик]

_lock = threading.Lock()
_df = pd.DataFrame(columns=["ts","co2","temp","rh","pm25","people","fan","valve"]).set_index("ts")

_state = {
    "auto": True,
    "class_size": 30,
    "group_lessons": set(),     # индексы уроков (1..N), где половина класса
    "shift": 1,                 # 1,2
    "date": None,               # dt.date или None (=сегодня)
    # внутренние
    "co2": 600.0, "temp": 21.0, "rh": 46.0, "pm25": OUT_PM25,
    "fan": 10.0, "valve": 5.0,
}

def _parse(hhmm: str) -> dt.time:
    h, m = hhmm.split(":")
    return dt.time(int(h), int(m))

def _in_interval(t: dt.time, a: dt.time, b: dt.time) -> bool:
    return a <= t < b

def _schedule_for_today(now: dt.datetime):
    wd = now.weekday()  # 0-пн..6-вс
    if wd == 5:   # суббота
        return SAT1
    if wd == 6:   # воскресенье
        return []
    return SHIFT1 if _state["shift"] == 1 else SHIFT2

def _people_now(now: dt.datetime) -> int:
    sched = _schedule_for_today(now)
    if not sched:
        return 0
    t = now.time()
    ppl = 0
    lesson_idx = 0
    for i,(a,b,br) in enumerate(sched, start=1):
        ta, tb = _parse(a), _parse(b)
        if _in_interval(t, ta, tb):           # идёт урок
            base = _state["class_size"]
            if i in _state["group_lessons"]:
                base = math.ceil(base/2)
            # шум добавим немного
            ppl = max(0, int(base + random.uniform(-1.5,1.5)))
            lesson_idx = i
            break
        # перемена после урока
        tb_dt = now.replace(hour=int(b[:2]), minute=int(b[3:]), second=0, microsecond=0)
        br_end = tb_dt + dt.timedelta(minutes=br)
        if tb_dt.time() <= t < br_end.time():
            base = int(_state["class_size"] * random.uniform(0.05, 0.25))
            ppl = base
            lesson_idx = i
            break
    return ppl

def set_scenario(date_iso: str|None, shift: int|None, class_size: int|None, groups_csv: str|None):
    with _lock:
        if date_iso:
            try: _state["date"] = dt.date.fromisoformat(date_iso)
            except: _state["date"] = None
        if shift in (1,2): _state["shift"] = int(shift)
        if class_size: _state["class_size"] = max(5, min(40, int(class_size)))
        if groups_csv is not None:
            try:
                _state["group_lessons"] = {int(x) for x in groups_csv.split(",") if x.strip().isdigit()}
            except:
                _state["group_lessons"] = set()

def set_auto(on: bool):
    with _lock: _state["auto"] = bool(on)

def _outside(now: dt.datetime):
    d = _state["date"] or now.date()
    m = d.month
    clim = CLIMATE.get(m, {"t":0,"rh":60})
    # чуть шуманём погоду, чтобы не была идеально ровной
    return clim["t"] + random.uniform(-1.5,1.5), max(35, min(95, clim["rh"] + random.uniform(-4,4)))

def _tick():
    while True:
        now = dt.datetime.now()
        t_out, rh_out = _outside(now)
        with _lock:
            # люди
            people = _people_now(now)

            # автоматика по CO2
            if _state["auto"]:
                if _state["co2"] > CO2_TARGET + 80:
                    _state["fan"]   = min(100.0, _state["fan"]   + FAN_RAMP*100/60)
                    _state["valve"] = min(100.0, _state["valve"] + VALVE_RAMP*100/60)
                elif _state["co2"] < CO2_TARGET - 120:
                    _state["fan"]   = max( 5.0, _state["fan"]   - FAN_RAMP*100/60)
                    _state["valve"] = max( 5.0, _state["valve"] - VALVE_RAMP*100/60)

            # CO₂ динамика
            add = people * K_CO2_PER_PERSON / 60.0
            clear = (_state["fan"]/10.0)*VENT_CLEAR_PER_10/60.0 + (_state["valve"]/10.0)*VALVE_GAIN_PER_10/60.0
            _state["co2"] = max(400.0, _state["co2"] + add - clear + random.uniform(-1.5,1.5))

            # Температура: вклад людей + стремление к t_out
            dT_people = people * ROOM_HEAT_PEOPLE / 60.0
            _state["temp"] += (t_out - _state["temp"])/TAU_TEMP/60.0 + dT_people

            # Влажность чуть «тянется» к наружной
            _state["rh"] += (rh_out - _state["rh"])/60.0 + random.uniform(-0.02, 0.02)
            _state["rh"] = max(20.0, min(90.0, _state["rh"]))

            # PM2.5 слегка дышит + небольшая фильтрация вентилятором
            _state["pm25"] += random.uniform(-0.05,0.05) - 0.002*_state["fan"]
            _state["pm25"] = max(2.0, min(25.0, _state["pm25"]))

            # запись
            row = dict(co2=_state["co2"], temp=_state["temp"], rh=_state["rh"],
                       pm25=_state["pm25"], people=people, fan=_state["fan"], valve=_state["valve"])
            ts = now
            global _df
            _df.loc[ts] = row
            # не раздуваем буфер
            if len(_df) > BUF_MIN:
                _df = _df.iloc[-BUF_MIN:].copy()

        time.sleep(1)

def start_simulation():
    if not getattr(start_simulation, "_started", False):
        thr = threading.Thread(target=_tick, daemon=True)
        thr.start()
        start_simulation._started = True  # type: ignore

def get_last_df(n: int) -> pd.DataFrame:
    with _lock:
        return _df.tail(n).copy()
# [SV_SCENARIO_API] start
try:
    _state
except NameError:
    _state = {}

def set_auto(on: bool):
    """Вкл/выкл автоматическую вентиляцию (переключатель режима)."""
    try:
        _state["force_auto"] = bool(on)
    except Exception:
        pass

def apply_scenario(date_iso, shift, class_size, groups_csv, auto_value):
    """
    Принять параметры из UI и сохранить в _state.
    Важно: потоковые таймштампы НЕ трогаем — графики остаются в реальном времени.
    """
    try:
        auto_on = False
        if isinstance(auto_value, (list, tuple, set)):
            auto_on = "on" in auto_value
        elif isinstance(auto_value, bool):
            auto_on = auto_value
        elif isinstance(auto_value, str):
            auto_on = auto_value.lower() in ("on", "true", "1", "yes")
        _state["force_auto"] = bool(auto_on)

        if date_iso:
            _state["date_override"] = str(date_iso)
        if isinstance(shift, (int,)) and shift in (1, 2):
            _state["shift"] = int(shift)
        elif isinstance(shift, str):
            _state["shift"] = 1 if shift.startswith("1") else (2 if shift.startswith("2") else _state.get("shift", 1))
        if class_size is not None:
            try:
                _state["class_size"] = max(1, int(class_size))
            except Exception:
                pass
        if groups_csv is not None:
            try:
                _state["group_lessons"] = [int(x) for x in str(groups_csv).split(",") if x.strip().isdigit()]
            except Exception:
                _state["group_lessons"] = []
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "err": str(e)}
# [SV_SCENARIO_API] end
