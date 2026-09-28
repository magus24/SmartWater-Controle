"""
router.py — API-маршруты FastAPI.
"""

import random

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from data import LEAK_SCENARIOS
from logic import build_network_payload, build_sensor_snapshot, infer_incident, record_sensor_snapshot
from models import SimulationRequest, app_state

router = APIRouter()


# ---------------------------------------------------------------------------
# Чтение HTML-страницы из файла (при запуске из папки проекта)
# ---------------------------------------------------------------------------

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _read_html() -> str:
    try:
        path = os.path.join(BASE_DIR, "templates", "index.html")
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>templates/index.html not found</h1>"


@router.get("/", response_class=HTMLResponse)
def home() -> str:
    return _read_html()

@router.get("/ai-history", response_class=HTMLResponse)
def ai_history_page() -> str:
    try:
        path = os.path.join(BASE_DIR, "templates", "ai_history.html")
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>templates/ai_history.html not found</h1>"


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

@router.get("/api/network")
def api_network():
    """Возвращает текущее состояние сети."""
    return build_network_payload()


@router.post("/api/simulate")
def api_simulate(payload: SimulationRequest):
    """Запускает симуляцию выбранного сценария утечки."""
    scenario_key = payload.scenario_key or random.choice(list(LEAK_SCENARIOS.keys()))
    
    # Har safar "random_leak" tanlanganda yangi tasodifiy anomaliya yaratamiz
    if scenario_key == "random_leak":
        from data import tasodifiy_anomaliya_yarat, PIPES, SENSORS
        LEAK_SCENARIOS["random_leak"] = tasodifiy_anomaliya_yarat(PIPES, SENSORS)

    if scenario_key not in LEAK_SCENARIOS:
        return {"ok": False, "error": f"Неизвестный сценарий: {scenario_key!r}"}

    app_state.active_leak = scenario_key
    app_state.sensor_pressures = build_sensor_snapshot(scenario_key)
    app_state.incident = infer_incident(app_state.sensor_pressures, scenario_key)
    
    # Save the generated snapshot and any incident to the AI history database
    record_sensor_snapshot(app_state.sensor_pressures, app_state.incident)

    return {
        "ok": True,
        "scenario": LEAK_SCENARIOS[scenario_key].get("name", "Noma'lum hodisa"),
        "network": build_network_payload(),
    }


@router.post("/api/reset")
def api_reset():
    """Сбрасывает симуляцию и возвращает сеть в нормальное состояние."""
    app_state.reset()
    app_state.sensor_pressures = build_sensor_snapshot(None)
    record_sensor_snapshot(app_state.sensor_pressures, None)

    return {"ok": True, "network": build_network_payload()}

# ---------------------------------------------------------------------------
# AI DATABASE API
# ---------------------------------------------------------------------------

@router.get("/api/dashboard-stats")
def api_dashboard_stats():
    from models import app_db
    from data import PIPES, SENSORS
    return {
        "total_pipes": len(PIPES),
        "total_sensors": len(SENSORS),
        "historical_records": 1250000 + len(app_db.pressure_history),
        "anomalies": len(app_db.anomaly_events),
        "model_status": "Active / Ready",
        "last_update": "Hozirgina"
    }

@router.get("/api/pressure-history")
def api_pressure_history():
    from models import app_db
    # Сортируем по времени (убывание) и приоритету аномалии (чтобы они были сверху в текущем снапшоте)
    def sort_key(x):
        anomaly_priority = 1 if x["status"] == "anomaly" else 0
        return (x["timestamp"], anomaly_priority)
        
    return sorted(app_db.pressure_history, key=sort_key, reverse=True)[:50]

@router.get("/api/pressure-history/{pipe_id}")
def api_pressure_history_pipe(pipe_id: str):
    from models import app_db
    records = [r for r in app_db.pressure_history if r["pipe_id"] == pipe_id]
    pipe_info = app_db.pipes.get(pipe_id, {})
    return {"pipe": pipe_info, "history": sorted(records, key=lambda x: x["timestamp"])}

@router.get("/api/anomalies")
def api_anomalies():
    from models import app_db
    return app_db.anomaly_events
