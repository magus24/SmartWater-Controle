"""
export_static.py — генерация статической версии сайта для GitHub Pages.

Запуск:
    pip install -r requirements.txt
    python export_static.py

Результат: папка docs/ (index.html, ai_history.html, static/, data/*.json),
которую GitHub Pages публикует как обычный сайт.
"""

import json
import os
import random
from datetime import datetime, timedelta

from data import PIPES, SENSORS
from logic import (
    build_network_payload,
    build_sensor_snapshot,
    init_db,
    infer_incident,
    record_sensor_snapshot,
)
from models import app_db, app_state

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DOCS_DATA_DIR = os.path.join(DOCS_DIR, "data")

SHIM_TAG = '<script src="static/app-shim.js"></script>'


def write_json(path: str, payload) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def inject_shim(html: str) -> str:
    """Вставляет shim в <head> и чинит навигацию под префикс /<repo>/."""
    if SHIM_TAG in html:
        return html
    if "</head>" in html:
        return html.replace("</head>", f"    {SHIM_TAG}\n</head>", 1)
    return SHIM_TAG + html


def fix_links(html: str) -> str:
    """Абсолютные ссылки не работают на Pages — делаем их относительными."""
    html = html.replace('href="/ai-history"', 'href="ai_history.html"')
    html = html.replace('href="/"', 'href="index.html"')
    return html


def export_pages() -> None:
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "static"), exist_ok=True)

    for name in ("index.html", "ai_history.html"):
        src = os.path.join(TEMPLATES_DIR, name)
        with open(src, encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(DOCS_DIR, name), "w", encoding="utf-8") as f:
            f.write(fix_links(inject_shim(html)))

    with open(os.path.join(STATIC_DIR, "app-shim.js"), encoding="utf-8") as f:
        shim = f.read()
    with open(os.path.join(DOCS_DIR, "static", "app-shim.js"), "w", encoding="utf-8") as f:
        f.write(shim)

    with open(os.path.join(DOCS_DIR, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    print(f"[+] HTML + shim -> {DOCS_DIR}")


def export_data(seed: int = 7) -> None:
    """Генерирует демо-данные: нормальное состояние + несколько аварий."""
    random.seed(seed)

    init_db()
    app_state.sensor_pressures = build_sensor_snapshot(None)
    record_sensor_snapshot(app_state.sensor_pressures, None)
    base_network = build_network_payload()
    write_json(os.path.join(DOCS_DATA_DIR, "network.json"), base_network)

    # История аварий: 4 инцидента, чтобы журнал ИИ не был пустым
    scenarios = list(LEAK_SCENARIO_KEYS())
    for i in range(4):
        key = scenarios[i % len(scenarios)]
        app_state.active_leak = key
        snapshot = build_sensor_snapshot(key)
        app_state.sensor_pressures = snapshot
        incident = infer_incident(snapshot, key)
        if incident:
            record_sensor_snapshot(snapshot, incident)
        # откатываем состояние сети в норму
        app_state.active_leak = None
        app_state.sensor_pressures = build_sensor_snapshot(None)
        app_state.incident = None
        _ = i

    history = sorted(
        app_db.pressure_history,
        key=lambda x: (x["timestamp"], 1 if x["status"] == "anomaly" else 0),
        reverse=True,
    )
    write_json(os.path.join(DOCS_DATA_DIR, "pressure-history.json"), history[:50])

    history_all = app_db.pressure_history
    write_json(os.path.join(DOCS_DATA_DIR, "anomalies.json"), app_db.anomaly_events)

    write_json(
        os.path.join(DOCS_DATA_DIR, "dashboard-stats.json"),
        {
            "total_pipes": len(PIPES),
            "total_sensors": len(SENSORS),
            "historical_records": 1250000 + len(app_db.pressure_history),
            "anomalies": len(app_db.anomaly_events),
            "model_status": "Active / Ready",
            "last_update": datetime.now().strftime("%H:%M:%S"),
        },
    )

    pipes_meta = {}
    for pipe_id, meta in app_db.pipes.items():
        pipes_meta[pipe_id] = {
            "name": meta.get("name"),
            "road_hint": meta.get("road_hint"),
            "baseline": meta.get("baseline"),
        }
    write_json(os.path.join(DOCS_DATA_DIR, "pipes-meta.json"), pipes_meta)

    print(
        f"[+] Data -> {DOCS_DATA_DIR} "
        f"(pipes={len(PIPES)}, sensors={len(SENSORS)}, "
        f"history={len(history_all)}, anomalies={len(app_db.anomaly_events)})"
    )


def LEAK_SCENARIO_KEYS():
    from data import LEAK_SCENARIOS

    keys = [k for k in LEAK_SCENARIOS.keys() if k != "random_leak"]
    return keys or list(LEAK_SCENARIOS.keys())


def main() -> None:
    export_pages()
    export_data()
    total = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(DOCS_DIR)
        for f in files
    )
    print(f"[OK] docs/ ready, total {total / 1024 / 1024:.2f} MB")
    _ = timedelta


if __name__ == "__main__":
    main()
