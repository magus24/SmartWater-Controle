"""
main.py — Точка входа. Создаёт приложение FastAPI, подключает middleware и роутер.

Запуск:
    uvicorn main:app --reload --host 127.0.0.1 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logic import build_sensor_snapshot, init_db
from models import app_state
from router import router
# Инициализация приложения
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SMART WATER CONTROL",
    description="Карта водоснабжения с ИИ-анализом протечек — г. Фергана",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ---------------------------------------------------------------------------
# Стартовая инициализация состояния
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    """Заполняем начальный снапшот давлений при старте сервера."""
    init_db()
    app_state.sensor_pressures = build_sensor_snapshot(None)


# ---------------------------------------------------------------------------
# Прямой запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
