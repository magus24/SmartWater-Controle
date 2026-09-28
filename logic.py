"""
logic.py — Бизнес-логика: расчёт давлений, анализ инцидентов, сборка payload.
"""

import math
import random
from typing import Dict, List, Optional

from datetime import datetime, timedelta
import uuid

from data import NODES, PIPES, SENSORS, LEAK_SCENARIOS, CITY_CONFIG
from models import app_state, app_db

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))
from analytics.ai_detector import ai_detector


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def route_midpoint(route: List[List[float]]) -> Dict[str, float]:
    """Возвращает географическую середину полилинии."""
    if not route:
        return {"lat": 0.0, "lng": 0.0}
    if len(route) == 1:
        return {"lat": route[0][0], "lng": route[0][1]}

    total = 0.0
    segments = []
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        length = math.dist(a, b)
        segments.append((a, b, length))
        total += length

    half = total / 2
    acc = 0.0
    for a, b, length in segments:
        if acc + length >= half:
            ratio = (half - acc) / length if length else 0.0
            return {
                "lat": a[0] + (b[0] - a[0]) * ratio,
                "lng": a[1] + (b[1] - a[1]) * ratio,
            }
        acc += length

    last = route[-1]
    return {"lat": last[0], "lng": last[1]}


def calculate_pressure_status(current: float, baseline: float) -> str:
    """Определяет статус датчика по отклонению давления."""
    delta = baseline - current
    if delta >= 1.2:
        return "critical"
    if delta >= 0.6:
        return "warning"
    return "normal"


# ---------------------------------------------------------------------------
# Построение снапшота датчиков
# ---------------------------------------------------------------------------

def build_sensor_snapshot(leak_key: Optional[str] = None) -> List[Dict]:
    """Ssenariyni hisobga olgan holda barcha datchiklarning joriy ko'rsatkichlarini yaratadi."""
    scenario = LEAK_SCENARIOS.get(leak_key) if leak_key else None
    snapshot = []

    for sensor_id, sensor in SENSORS.items():
        # Agar sensorda baseline_pressure bo'lmasa, xavfsiz qiymat sifatida 7.0 olinadi
        baseline = sensor.get("baseline_pressure", 7.0)
        noise = round(random.uniform(-0.06, 0.06), 2)
        
        # Scenario ichida affected_sensors bo'lmasa xato bermasligi uchun tekshirish
        leak_delta = 0.0
        if scenario and "affected_sensors" in scenario:
            leak_delta = scenario["affected_sensors"].get(sensor_id, 0.0)
            
        current = round(max(3.0, baseline + leak_delta + noise), 2)

        snapshot.append({
            "id": sensor_id,
            "pipe_id": sensor.get("pipe_id"),
            "node": sensor.get("node"),
            "label": sensor.get("label"),
            "lat": sensor.get("lat", 0.0),
            "lng": sensor.get("lng", 0.0),
            "baseline_pressure": baseline,
            "current_pressure": current,
            "delta": round(current - baseline, 2),
            "status": calculate_pressure_status(current, baseline),
        })

    return snapshot


# ---------------------------------------------------------------------------
# Анализ инцидента (имитация ИИ-логики)
# ---------------------------------------------------------------------------

def infer_incident(
    sensor_snapshot: List[Dict],
    leak_key: Optional[str],
) -> Optional[Dict]:
    """
    Snapshotni tahlil qiladi va hodisa tavsifini qaytaradi.
    MVP da bosim pasayishini qidirishning deterministik algoritmidan foydalanadi.
    """
    if not leak_key:
        return None

    scenario = LEAK_SCENARIOS.get(leak_key)
    if not scenario:
        return None

    pipe_id = scenario.get("pipe_id")
    pipe = PIPES.get(pipe_id, {"id": pipe_id, "name": f"Quvur {pipe_id}"})
    suspected_point = route_midpoint(pipe.get("route") or [])

    # Eng ko'p bosim tushgan 5 ta datchik
    strongest = sorted(
        sensor_snapshot,
        key=lambda x: x["baseline_pressure"] - x["current_pressure"],
        reverse=True,
    )[:5]

    avg_drop = sum(s["baseline_pressure"] - s["current_pressure"] for s in strongest) / max(1, len(strongest))
    confidence = min(98, max(62, round(70 + avg_drop * 12)))

    if avg_drop >= 1.35:
        severity = "critical"
    elif avg_drop >= 0.8:
        severity = "high"
    else:
        severity = "medium"

    reasons = [
        f"{s['id']}: bosim {round(s['baseline_pressure'] - s['current_pressure'], 2)} bar ga pasaydi"
        for s in strongest[:3]
    ]
    reasons.append(f"Anomaliya «{pipe['name']}» quvuri atrofida aniqlandi")
    reasons.append("Yaqin atrofidagi datchiklar bosim pasayishini tasdiqlamoqda")

    summary = (
        f"AI «{pipe['name']}» hududida beqaror bosimni aniqladi. "
        f"Quvur bo'ylab datchiklarda sezilarli bosim pasayishi qayd etildi. "
        f"Ehtimoliy sizib chiqish yuz bergan."
    )

    return {
        "title": scenario.get("name", "Noma'lum hodisa"),
        "severity": severity,
        "confidence": confidence,
        "pipe_id": pipe["id"],
        "pipe_name": pipe["name"],
        "road_hint": pipe.get("road_hint"),
        "suspected_location": suspected_point,
        "reasons": reasons,
        "summary": summary,
        "suggested_action": (
            "Belgilangan hududni tekshirish uchun mobil guruh yuborilsin. "
            "Agar bosim pasayishda davom etsa, quvur tarmog'i izolyatsiya qilinsin. "
            "Yaqin atrofdagi klapanlar va ulanishlar tekshirilsin."
        ),
    }


# ---------------------------------------------------------------------------
# Сборка полного payload сети
# ---------------------------------------------------------------------------

def build_network_payload() -> Dict:
    """Tarmoq holati to'g'risidagi to'liq JSON ma'lumotlarini yig'adi."""
    sensor_snapshot = app_state.sensor_pressures or build_sensor_snapshot(app_state.active_leak)
    app_state.sensor_pressures = sensor_snapshot
    app_state.incident = infer_incident(sensor_snapshot, app_state.active_leak)

    leak_pipe_id = app_state.incident["pipe_id"] if app_state.incident else None

    enriched_nodes = [
        {
            **node,
            "sensor_count": sum(1 for s in sensor_snapshot if s.get("node") == node_id),
        }
        for node_id, node in NODES.items()
    ]

    enriched_pipes = []
    for pipe_id, pipe in PIPES.items():
        coords = pipe.get("route") or [
            [NODES[pipe["from"]]["lat"], NODES[pipe["from"]]["lng"]],
            [NODES[pipe["to"]]["lat"],   NODES[pipe["to"]]["lng"]],
        ]
        enriched_pipes.append({
            **pipe,
            "coordinates": coords,
            "status": "anomaly" if pipe_id == leak_pipe_id else "normal",
        })

    return {
        "city": CITY_CONFIG,
        "nodes": enriched_nodes,
        "pipes": enriched_pipes,
        "sensors": sensor_snapshot,
        "incident": app_state.incident,
        "simulation": {
            "active": app_state.active_leak is not None,
            "scenario_key": app_state.active_leak,
        },
    }

# ---------------------------------------------------------------------------
# AI Database (History & Anomalies) Management
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Генерирует начальные исторические данные для базы данных AI (MVP)."""
    if app_db.pipes:
        return
        
    now = datetime.now()
    
    # Берем трубы, у которых есть датчики
    tracked_pipe_ids = list(PIPES.keys())[:20] # Для демо берем часть труб
    for sensor_id, sensor in SENSORS.items():
        pipe_id = sensor.get("pipe_id")
        if pipe_id and pipe_id not in tracked_pipe_ids:
            tracked_pipe_ids.append(pipe_id)
            
    tracked_pipe_ids = list(set(tracked_pipe_ids))
    
    for pid in tracked_pipe_ids:
        p_data = PIPES.get(pid, {})
        
        # Получаем baseline_pressure из датчика или по умолчанию 7.0
        sensor_baseline = 7.0
        for sid, sval in SENSORS.items():
            if sval.get("pipe_id") == pid:
                sensor_baseline = sval.get("baseline_pressure", 7.0)
                break
                
        baseline = float(sensor_baseline)
        
        app_db.pipes[pid] = {
            "id": pid,
            "name": p_data.get("name", f"Quvur {pid}"),
            "road_hint": p_data.get("road_hint", "Asosiy trassa"),
            "baseline": round(baseline, 2)
        }
        
        # Генерируем 5 прошлых "нормальных" записей
        for i in range(5):
            t = now - timedelta(minutes=15 * (5 - i))
            actual = baseline + random.uniform(-0.15, 0.15)
            
            app_db.pressure_history.append({
                "id": str(uuid.uuid4())[:8],
                "pipe_id": pid,
                "timestamp": t.isoformat(),
                "expected_pressure": round(baseline, 2),
                "actual_pressure": round(actual, 2),
                "deviation_percent": round(((actual - baseline) / baseline) * 100, 1),
                "status": "normal"
            })

    ai_detector.train(app_db.pressure_history)

def record_sensor_snapshot(snapshot: List[Dict], incident: Optional[Dict]) -> None:
    """Сохраняет текущий снимок в историческую БД и фиксирует аномалии."""
    now = datetime.now().isoformat()
    incident_pipe = incident["pipe_id"] if incident else None
    pipe_aggregated = {}
    
    ai_payload = []
    for s in snapshot:
        pid = s.get("pipe_id")
        if not pid or pid not in app_db.pipes:
            continue
        ai_payload.append({
            "current_pressure": s["current_pressure"],
            "baseline_pressure": s.get("baseline_pressure", app_db.pipes[pid]["baseline"]),
            "s_ref": s,
            "pid": pid
        })
        
    ai_results = ai_detector.predict_batch(ai_payload)
    
    for i, item in enumerate(ai_payload):
        pid = item["pid"]
        s = item["s_ref"]
        actual = item["current_pressure"]
        baseline = item["baseline_pressure"]
        ai_pred = ai_results[i]
        
        dev_pct = round(((actual - baseline) / baseline) * 100, 1) if baseline else 0
        is_incident_pipe = (pid == incident_pipe)
        
        status = "anomaly" if (is_incident_pipe and s["status"] != "normal") or ai_pred["is_anomaly"] else "normal"
        
        if pid not in pipe_aggregated:
            pipe_aggregated[pid] = {
                "id": str(uuid.uuid4())[:8],
                "pipe_id": pid,
                "timestamp": now,
                "expected_pressure": round(baseline, 2),
                "actual_pressure": round(actual, 2),
                "deviation_percent": dev_pct,
                "status": status,
                "ai_confidence": ai_pred["confidence"],
                "ai_score": ai_pred["score"],
                "ai_explanation": ai_pred["explanation"]
            }
        else:
            existing = pipe_aggregated[pid]
            if status == "anomaly" and existing["status"] == "normal":
                existing["status"] = "anomaly"
                existing["actual_pressure"] = round(actual, 2)
                existing["deviation_percent"] = dev_pct
                existing["ai_confidence"] = ai_pred["confidence"]
                existing["ai_score"] = ai_pred["score"]
                existing["ai_explanation"] = ai_pred["explanation"]
            elif status == existing["status"]:
                if abs(dev_pct) > abs(existing["deviation_percent"]):
                    existing["actual_pressure"] = round(actual, 2)
                    existing["deviation_percent"] = dev_pct
                    existing["ai_confidence"] = ai_pred["confidence"]
                    existing["ai_score"] = ai_pred["score"]
                    existing["ai_explanation"] = ai_pred["explanation"]

    for rec in pipe_aggregated.values():
        app_db.pressure_history.append(rec)
        
    if incident:
        rec = pipe_aggregated.get(incident["pipe_id"], {})
        ai_confidence = rec.get("ai_confidence", 50.0)
        ai_score = rec.get("ai_score", 0.0)
        explanation = rec.get("ai_explanation", "Fallback explanation")
        
        # Добавляем инцидент в журнал
        app_db.anomaly_events.insert(0, {
            "incident_id": str(uuid.uuid4())[:8],
            "pipe_id": incident["pipe_id"],
            "pipe_name": incident["pipe_name"],
            "detected_at": now,
            "severity": incident["severity"],
            "confidence": ai_confidence,
            "reasons": incident["reasons"],
            "summary": incident["summary"],
            "status": "New",
            "ai_confidence": ai_confidence,
            "ai_score": ai_score,
            "explanation": explanation
        })
