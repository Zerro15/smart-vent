# software/data_source.py
from collections import deque
from dataclasses import dataclass
import threading, time, random, math
import pandas as pd
from typing import Deque, Dict, Any, List, Tuple

_MAX_POINTS = 12 * 60 * 60  # 12h @ 1s

@dataclass
class Sample:
    ts: float
    co2: float
    temp: float
    rh: float
    pm25: float
    people: int
    fan: float
    valve: float
    mode: str

_buf: Deque[Sample] = deque(maxlen=_MAX_POINTS)
_thread = None
_stop = threading.Event()
_lock = threading.Lock()

def _seed_initial():
    now = time.time()
    for i in range(60):
        _buf.append(Sample(
            ts=now - (60 - i),
            co2=600 + i * 1.0,
            temp=21.0,
            rh=45.0,
            pm25=8.0,
            people=2,
            fan=0.0,
            valve=0.0,
            mode="stop",
        ))

def _simulate_loop(step_sec: float):
    random.seed(7)
    co2, t, rh, pm = 650.0, 21.0, 45.0, 10.0
    fan, valve, mode = 0.0, 0.0, "auto"
    k = 0
    while not _stop.is_set():
        people = 2 + int(3 + 15 * abs(math.sin(k/180.0)) + random.uniform(-1, 1))
        people = max(0, min(30, people))

        gen = 0.7 * people
        ach = (fan/100.0) * 4.0 / 60.0
        co2 = max(420.0, co2 + gen - (co2 - 420.0) * ach)

        if co2 > 1100:
            fan = min(100.0, fan + 20); valve = min(100.0, valve + 15)
        elif co2 < 750:
            fan = max(10.0,  fan - 10);  valve = max(5.0,  valve - 10)

        t  += (0.03 * math.sin(k/50.0)) + 0.01*(people-10)/10.0 - 0.02*(fan/100.0)
        rh += (0.05 * math.cos(k/70.0)) + 0.03*(people-10)/10.0
        rh  = max(25.0, min(70.0, rh))
        pm += 0.1 * math.sin(k/33.0) - 0.08*(fan/100.0)
        pm  = max(3.0, pm)

        with _lock:
            _buf.append(Sample(time.time(), co2, t, rh, pm, people, fan, valve, mode))

        k += 1
        time.sleep(step_sec)

def _get_last_df(n_seconds: int = 600) -> pd.DataFrame:
    with _lock:
        items = list(_buf)[-n_seconds:]
    if not items:
        return pd.DataFrame(columns=["ts","co2","temp","rh","pm25","people","fan","valve","mode"])
    d: Dict[str, Any] = {
        "ts":[s.ts for s in items],"co2":[s.co2 for s in items],"temp":[s.temp for s in items],
        "rh":[s.rh for s in items],"pm25":[s.pm25 for s in items],"people":[s.people for s in items],
        "fan":[s.fan for s in items],"valve":[s.valve for s in items],"mode":[s.mode for s in items],
    }
    return pd.DataFrame(d)

class DataSource:
    """Тонкая обёртка, которую ждёт dash_app.DataSource."""
    def __init__(self, max_points: int = 600, step_sec: float = 1.0):
        global _buf
        _buf = deque(maxlen=max_points)  # уважим параметр
        self.step_sec = step_sec

    def start(self):
        global _thread
        if self.is_running():
            return
        _stop.clear()
        if not _buf:
            _seed_initial()
        _thread = threading.Thread(target=_simulate_loop, args=(self.step_sec,), daemon=True)
        _thread.start()

    def stop(self):
        global _thread
        _stop.set()
        if _thread:
            _thread.join(timeout=0.2)
        _thread = None

    def reset(self):
        with _lock:
            _buf.clear()

    def is_running(self) -> bool:
        return bool(_thread and _thread.is_alive())

    def get_series(self, n_seconds: int = 600) -> List[Tuple[float, float]]:
        df = _get_last_df(n_seconds)
        if df.empty:
            return []
        # На графике в примере одна серия — пусть будет CO2
        return list(zip(df["ts"].tolist(), df["co2"].tolist()))
