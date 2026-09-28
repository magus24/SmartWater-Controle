"""
models.py — Pydantic-схемы запросов и глобальное состояние приложения.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Запросы API
# ---------------------------------------------------------------------------

class SimulationRequest(BaseModel):
    scenario_key: Optional[str] = None


# ---------------------------------------------------------------------------
# Глобальное состояние (in-memory для MVP)
# В продакшене заменить на Redis / базу данных.
# ---------------------------------------------------------------------------

class AppState:
    """Потокобезопасное (для однопроцессного uvicorn) хранилище состояния."""

    def __init__(self) -> None:
        self.active_leak: Optional[str] = None
        self.sensor_pressures: List[Dict] = []
        self.incident: Optional[Dict] = None

    def reset(self) -> None:
        self.active_leak = None
        self.sensor_pressures = []
        self.incident = None


# ---------------------------------------------------------------------------
# База данных истории (in-memory для MVP)
# ---------------------------------------------------------------------------

class AppDatabase:
    def __init__(self) -> None:
        # Словари и списки для имитации БД
        self.pipes: Dict[str, Dict] = {}               # pipe_id -> pipe detailed config
        self.pressure_history: List[Dict] = []         # List of telemetry records
        self.anomaly_events: List[Dict] = []           # List of incidents
        
    def reset(self) -> None:
        # Для демо можно очищать историю, или оставлять
        pass

app_state = AppState()
app_db = AppDatabase()
