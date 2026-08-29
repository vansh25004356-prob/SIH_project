"""NER-SLIDE Backend — FastAPI monolith exposing all /api endpoints.

Modular services live under app/services/ and are wired here so the
container can later be split into microservices without a rewrite.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

BACKEND_DIR = Path(__file__).parent
load_dotenv(BACKEND_DIR / ".env")

import sys
sys.path.insert(0, str(BACKEND_DIR))

from app.services.ml_service import ml_service
from app.services import weather_service, risk_service, terrain_service, sms_service
from app.services.llm_service import explain_risk, translate_alert, SUPPORTED_LANGUAGES
from app.data.ner_seed import NER_ZONES, NER_SENSORS, NER_ROADS, NER_VILLAGES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("nerslide")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="NER-SLIDE API", version="1.0.0")
api = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Startup — seed zones/sensors/roads/villages if empty (idempotent)
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def seed_if_empty() -> None:
    if await db.zones.count_documents({}) == 0:
        await db.zones.insert_many([dict(z) for z in NER_ZONES])
        log.info("Seeded %d zones", len(NER_ZONES))
    if await db.sensors.count_documents({}) == 0:
        for s in NER_SENSORS:
            s["last_seen_iso"] = datetime.now(timezone.utc).isoformat()
        await db.sensors.insert_many([dict(s) for s in NER_SENSORS])
        log.info("Seeded %d sensors", len(NER_SENSORS))
    if await db.roads.count_documents({}) == 0:
        await db.roads.insert_many([dict(r) for r in NER_ROADS])
    if await db.villages.count_documents({}) == 0:
        await db.villages.insert_many([dict(v) for v in NER_VILLAGES])
    if await db.recipients.count_documents({}) == 0:
        demo_recipients = [
            {"id": str(uuid.uuid4()), "name": "Meghalaya Ops Officer", "phone": "+919000000001", "role": "AUTHORITY", "district": "East Khasi Hills", "language": "as", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "Sikkim District Head",  "phone": "+919000000002", "role": "AUTHORITY", "district": "North Sikkim", "language": "ne", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "Mizoram Field Officer", "phone": "+919000000003", "role": "FIELD_OFFICER", "district": None, "language": "lus", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.recipients.insert_many(demo_recipients)
        log.info("Seeded %d demo recipients", len(demo_recipients))
    # Recompute terrain from DEM (Open-Meteo elevation) for any zone still
    # tagged as DEMO. Runs once at boot; failures leave DEMO in place.
    import asyncio
    async def _dem_bootstrap() -> None:
        demo_zones = [z async for z in db.zones.find({"terrain_source": "DEMO"})]
        if not demo_zones:
            return
        log.info("Recomputing DEM terrain for %d zones", len(demo_zones))
        ok, failed = 0, 0
        for z in demo_zones:
            try:
                t = await terrain_service.compute_dem_features(z["centroid"]["lat"], z["centroid"]["lon"])
                await db.zones.update_one(
                    {"zone_id": z["zone_id"]},
                    {"$set": {"terrain": t, "terrain_source": "DEM_OPEN_METEO"}},
                )
                ok += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("DEM recompute failed zone=%s reason=%s", z.get("zone_id"), exc)
                failed += 1
        log.info("DEM recompute done ok=%d failed=%d", ok, failed)
    asyncio.create_task(_dem_bootstrap())


@app.on_event("shutdown")
async def _close() -> None:
    client.close()


def _strip(d: Dict[str, Any]) -> Dict[str, Any]:
    d.pop("_id", None)
    return d


# ---------------------------------------------------------------------------
# Health + model meta
# ---------------------------------------------------------------------------
@api.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": ml_service.model is not None,
        "model_version": ml_service.version,
        "feature_count": len(ml_service.feature_list()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api.get("/model/info")
async def model_info() -> Dict[str, Any]:
    return {
        "version": ml_service.version,
        "features": ml_service.feature_list(),
        "threshold_operational": 0.15,
        "severity_bands": [
            {"label": lbl, "lo": lo, "hi": hi} for lbl, lo, hi in
            [("LOW", 0.0, 0.15), ("MEDIUM", 0.15, 0.35), ("HIGH", 0.35, 0.65), ("CRITICAL", 0.65, 1.01)]
        ],
    }


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------
class PredictRequest(BaseModel):
    features: Dict[str, float]


@api.post("/predictions/predict")
async def predict(req: PredictRequest) -> Dict[str, Any]:
    try:
        result = ml_service.predict_one(req.features)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    return result


class ZonePredictRequest(BaseModel):
    zone_id: str
    rainfall_override: Optional[Dict[str, float]] = None  # for the SIH "simulate more rain" demo


@api.post("/predictions/zone")
async def predict_zone_api(req: ZonePredictRequest) -> Dict[str, Any]:
    z = await db.zones.find_one({"zone_id": req.zone_id})
    if not z:
        raise HTTPException(status_code=404, detail="zone_not_found")
    _strip(z)
    result = await risk_service.predict_zone(z, req.rainfall_override)
    if "error" in result:
        raise HTTPException(status_code=424, detail=result)
    result["response_priority"] = risk_service.classify_response_priority(result, z)
    # persist latest
    await db.risk_predictions.update_one(
        {"zone_id": req.zone_id},
        {"$set": {**result, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return result


@api.get("/predictions/{zone_id}")
async def get_latest_prediction(zone_id: str) -> Dict[str, Any]:
    doc = await db.risk_predictions.find_one({"zone_id": zone_id})
    if not doc:
        raise HTTPException(status_code=404, detail="no_prediction_yet")
    return _strip(doc)


# ---------------------------------------------------------------------------
# Zones + GIS
# ---------------------------------------------------------------------------
@api.get("/zones")
async def list_zones(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if state:
        q["state"] = state
    zones = await db.zones.find(q).to_list(500)
    # merge latest severity
    preds = {p["zone_id"]: p async for p in db.risk_predictions.find({})}
    out = []
    for z in zones:
        _strip(z)
        p = preds.get(z["zone_id"])
        if p:
            z["latest"] = {
                "severity": p.get("severity"),
                "risk_score": p.get("risk_score"),
                "probability": p.get("probability"),
                "updated_at": p.get("updated_at"),
            }
        if severity and (not p or p.get("severity") != severity):
            continue
        out.append(z)
    return out


@api.get("/zones/{zone_id}")
async def get_zone(zone_id: str) -> Dict[str, Any]:
    z = await db.zones.find_one({"zone_id": zone_id})
    if not z:
        raise HTTPException(status_code=404, detail="zone_not_found")
    _strip(z)
    p = await db.risk_predictions.find_one({"zone_id": zone_id})
    if p:
        z["latest"] = _strip(p)
    # attach nearby sensors + roads + villages
    z["sensors"] = [_strip(s) async for s in db.sensors.find({"zone_id": zone_id})]
    z["roads_nearby"] = await _nearest_roads(z["centroid"]["lat"], z["centroid"]["lon"], limit=3)
    z["villages_nearby"] = await _nearest_villages(z["centroid"]["lat"], z["centroid"]["lon"], limit=3)
    return z


@api.get("/gis/risk-zones")
async def gis_risk_zones() -> Dict[str, Any]:
    zones = await db.zones.find({}).to_list(500)
    preds = {p["zone_id"]: p async for p in db.risk_predictions.find({})}
    features = []
    for z in zones:
        _strip(z)
        p = preds.get(z["zone_id"]) or {}
        features.append({
            "type": "Feature",
            "geometry": z["geometry"],
            "properties": {
                "zone_id": z["zone_id"],
                "name": z["name"],
                "state": z["state"],
                "district": z["district"],
                "severity": p.get("severity", "UNKNOWN"),
                "risk_score": p.get("risk_score"),
                "probability": p.get("probability"),
                "population": z.get("population"),
                "updated_at": p.get("updated_at"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


@api.get("/gis/heatmap")
async def gis_heatmap() -> List[Dict[str, Any]]:
    zones = await db.zones.find({}).to_list(500)
    preds = {p["zone_id"]: p async for p in db.risk_predictions.find({})}
    points = []
    for z in zones:
        _strip(z)
        p = preds.get(z["zone_id"]) or {}
        intensity = float(p.get("probability", 0.0)) if p else 0.0
        points.append({
            "lat": z["centroid"]["lat"],
            "lon": z["centroid"]["lon"],
            "intensity": intensity,
            "zone_id": z["zone_id"],
            "severity": p.get("severity", "UNKNOWN"),
        })
    return points


@api.get("/gis/sensors")
async def gis_sensors() -> Dict[str, Any]:
    sensors = [_strip(s) async for s in db.sensors.find({})]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                "properties": s,
            }
            for s in sensors
        ],
    }


@api.get("/gis/roads")
async def gis_roads() -> Dict[str, Any]:
    roads = [_strip(r) async for r in db.roads.find({})]
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": r["geometry"], "properties": {k: v for k, v in r.items() if k != "geometry"}} for r in roads],
    }


@api.get("/gis/villages")
async def gis_villages() -> Dict[str, Any]:
    v = [_strip(x) async for x in db.villages.find({})]
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x["location"]["lon"], x["location"]["lat"]]}, "properties": x}
            for x in v
        ],
    }


@api.get("/gis/reports")
async def gis_reports() -> Dict[str, Any]:
    r = [_strip(x) async for x in db.reports.find({}).sort("timestamp", -1)]
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x["lon"], x["lat"]]}, "properties": x}
            for x in r
        ],
    }


@api.get("/gis/alerts")
async def gis_alerts() -> List[Dict[str, Any]]:
    return [_strip(x) async for x in db.alerts.find({}).sort("timestamp", -1).limit(50)]


# ---------------------------------------------------------------------------
# Nearest-anything helpers (haversine — no PostGIS available)
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def _nearest_roads(lat: float, lon: float, limit: int = 3):
    roads = [_strip(r) async for r in db.roads.find({})]
    scored = []
    for r in roads:
        coords = r["geometry"]["coordinates"]
        d = min(_haversine(lat, lon, c[1], c[0]) for c in coords)
        scored.append((d, r))
    scored.sort(key=lambda x: x[0])
    return [{**r, "distance_km": round(d, 2)} for d, r in scored[:limit]]


async def _nearest_villages(lat: float, lon: float, limit: int = 3):
    villages = [_strip(v) async for v in db.villages.find({})]
    scored = [(_haversine(lat, lon, v["location"]["lat"], v["location"]["lon"]), v) for v in villages]
    scored.sort(key=lambda x: x[0])
    return [{**v, "distance_km": round(d, 2)} for d, v in scored[:limit]]


@api.get("/gis/nearby")
async def gis_nearby(lat: float, lon: float) -> Dict[str, Any]:
    return {
        "roads": await _nearest_roads(lat, lon, 3),
        "villages": await _nearest_villages(lat, lon, 3),
    }


# ---------------------------------------------------------------------------
# Weather + terrain
# ---------------------------------------------------------------------------
@api.get("/weather")
async def weather(latitude: float, longitude: float) -> Dict[str, Any]:
    return await weather_service.get_current(latitude, longitude)


@api.get("/weather/history")
async def weather_history(latitude: float, longitude: float, days: int = 30) -> Dict[str, Any]:
    return await weather_service.get_history(latitude, longitude, days)


@api.get("/terrain/elevation")
async def terrain_elevation(latitude: float, longitude: float) -> Dict[str, Any]:
    return await weather_service.get_elevation(latitude, longitude)


@api.post("/terrain/recompute")
async def terrain_recompute(zone_id: Optional[str] = None) -> Dict[str, Any]:
    q = {"zone_id": zone_id} if zone_id else {}
    zones = [z async for z in db.zones.find(q)]
    ok, failed = 0, 0
    for z in zones:
        try:
            t = await terrain_service.compute_dem_features(z["centroid"]["lat"], z["centroid"]["lon"])
            await db.zones.update_one(
                {"zone_id": z["zone_id"]},
                {"$set": {"terrain": t, "terrain_source": "DEM_OPEN_METEO"}},
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("DEM recompute failed zone=%s reason=%s", z.get("zone_id"), exc)
            failed += 1
    return {"ok": ok, "failed": failed, "source": "OPEN_METEO_ELEVATION"}


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------
@api.get("/sensors")
async def sensors_list(status: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    return [_strip(s) async for s in db.sensors.find(q).sort("sensor_id", 1)]


class SensorReading(BaseModel):
    sensor_id: str
    measurement_type: str
    value: float


@api.post("/sensors/readings")
async def post_reading(r: SensorReading) -> Dict[str, Any]:
    doc = {**r.model_dump(), "timestamp": datetime.now(timezone.utc).isoformat(), "id": str(uuid.uuid4())}
    await db.sensor_readings.insert_one(doc)
    await db.sensors.update_one({"sensor_id": r.sensor_id}, {"$set": {"last_seen_iso": doc["timestamp"]}})
    return _strip(doc)


# ---------------------------------------------------------------------------
# Reports (citizen / field officer)
# ---------------------------------------------------------------------------
class ReportCreate(BaseModel):
    lat: float
    lon: float
    report_type: str  # CRACK / SEEPAGE / SLOPE_MOVEMENT / ROCKFALL / ROAD_BLOCKAGE / LANDSLIDE / OTHER
    description: Optional[str] = ""
    photo_url: Optional[str] = None
    reporter_role: str = "CITIZEN"  # or FIELD_OFFICER
    reporter_name: Optional[str] = "Anonymous"
    client_uuid: Optional[str] = None  # for offline sync dedup


@api.post("/reports")
async def create_report(r: ReportCreate) -> Dict[str, Any]:
    if r.client_uuid:
        existing = await db.reports.find_one({"client_uuid": r.client_uuid})
        if existing:
            return _strip(existing)
    doc: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        **r.model_dump(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "FIELD_OFFICER" if r.reporter_role == "FIELD_OFFICER" else "CITIZEN",
        "status": "OPEN",
    }
    # side-effect: if ROAD_BLOCKAGE, mark nearest road BLOCKED + flag zone
    if r.report_type == "ROAD_BLOCKAGE":
        near = await _nearest_roads(r.lat, r.lon, 1)
        if near:
            road = near[0]
            await db.roads.update_one({"road_id": road["road_id"]}, {"$set": {"status": "BLOCKED"}})
            doc["affected_road"] = road["road_id"]
    # attach to nearest zone
    zones = await db.zones.find({}).to_list(500)
    if zones:
        z = min(zones, key=lambda x: _haversine(r.lat, r.lon, x["centroid"]["lat"], x["centroid"]["lon"]))
        doc["zone_id"] = z["zone_id"]
        await db.zones.update_one({"zone_id": z["zone_id"]}, {"$set": {"recent_field_report": True}})
    await db.reports.insert_one(doc)
    return _strip(doc)


@api.get("/reports")
async def list_reports(limit: int = 100) -> List[Dict[str, Any]]:
    return [_strip(r) async for r in db.reports.find({}).sort("timestamp", -1).limit(limit)]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class AlertCreate(BaseModel):
    zone_id: str
    severity: str
    reason: str
    recommended_action: str = "Evacuate at-risk slopes; halt construction; notify local authorities."


@api.post("/alerts")
async def create_alert(a: AlertCreate) -> Dict[str, Any]:
    zone = await db.zones.find_one({"zone_id": a.zone_id})
    if not zone:
        raise HTTPException(status_code=404, detail="zone_not_found")
    en_msg = (
        f"{a.severity} landslide risk near {zone.get('name')} ({zone.get('district')}, {zone.get('state')}). "
        f"Reason: {a.reason}. Action: {a.recommended_action}"
    )
    tx = await translate_alert(en_msg, list(SUPPORTED_LANGUAGES.keys()))
    doc: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "zone_id": a.zone_id,
        "severity": a.severity,
        "reason": a.reason,
        "recommended_action": a.recommended_action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "translations": tx,
        "status": "ACTIVE",
    }
    await db.alerts.insert_one(doc)
    # Fan-out to district officers via SMS (log-only until Twilio creds present)
    _strip(zone)
    try:
        deliveries = await sms_service.blast_alert(db, doc, zone)
        doc["deliveries"] = deliveries
        await db.alerts.update_one({"id": doc["id"]}, {"$set": {"deliveries": deliveries}})
    except Exception as exc:  # noqa: BLE001
        log.warning("SMS blast failed: %s", exc)
    return _strip(doc)


# ---------------------------------------------------------------------------
# Recipients (SMS distribution list)
# ---------------------------------------------------------------------------
class RecipientCreate(BaseModel):
    name: str
    phone: str
    role: str = "AUTHORITY"       # AUTHORITY / FIELD_OFFICER / CITIZEN
    district: Optional[str] = None
    language: str = "en"


@api.post("/recipients")
async def create_recipient(r: RecipientCreate) -> Dict[str, Any]:
    doc = {"id": str(uuid.uuid4()), **r.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
    await db.recipients.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@api.get("/recipients")
async def list_recipients() -> List[Dict[str, Any]]:
    return [_strip(r) async for r in db.recipients.find({}).sort("created_at", -1)]


@api.delete("/recipients/{recipient_id}")
async def delete_recipient(recipient_id: str) -> Dict[str, Any]:
    res = await db.recipients.delete_one({"id": recipient_id})
    return {"deleted": res.deleted_count}


@api.get("/notifications")
async def list_notifications(limit: int = 200) -> List[Dict[str, Any]]:
    return [_strip(n) async for n in db.notifications.find({}).sort("timestamp", -1).limit(limit)]


@api.get("/notifications/status")
async def notification_status() -> Dict[str, Any]:
    return {
        "provider": "TWILIO" if os.environ.get("TWILIO_ACCOUNT_SID") else "LOG_ONLY",
        "twilio_configured": bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN") and os.environ.get("TWILIO_FROM_NUMBER")),
    }


@api.get("/alerts")
async def list_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    return [_strip(a) async for a in db.alerts.find({}).sort("timestamp", -1).limit(limit)]


# ---------------------------------------------------------------------------
# Response priorities
# ---------------------------------------------------------------------------
@api.get("/response/priorities")
async def response_priorities() -> List[Dict[str, Any]]:
    out = []
    async for p in db.risk_predictions.find({}):
        _strip(p)
        z = await db.zones.find_one({"zone_id": p["zone_id"]})
        if not z:
            continue
        _strip(z)
        pr = risk_service.classify_response_priority(p, z)
        out.append({
            "zone_id": p["zone_id"],
            "zone_name": z.get("name"),
            "state": z.get("state"),
            "district": z.get("district"),
            "severity": p.get("severity"),
            "risk_score": p.get("risk_score"),
            **pr,
        })
    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    out.sort(key=lambda x: order.get(x["priority"], 9))
    return out


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@api.get("/dashboard/summary")
async def dashboard_summary() -> Dict[str, Any]:
    zones_total = await db.zones.count_documents({})
    sensors = await db.sensors.find({}).to_list(1000)
    online = sum(1 for s in sensors if s.get("status") == "ONLINE")
    offline = sum(1 for s in sensors if s.get("status") == "OFFLINE")
    roads = await db.roads.find({}).to_list(1000)
    blocked = sum(1 for r in roads if r.get("status") == "BLOCKED")
    at_risk = sum(1 for r in roads if r.get("status") == "AT_RISK")
    preds = [p async for p in db.risk_predictions.find({})]
    sev_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0, "UNKNOWN": 0}
    for p in preds:
        sev_counts[p.get("severity", "UNKNOWN")] = sev_counts.get(p.get("severity", "UNKNOWN"), 0) + 1
    active_alerts = await db.alerts.count_documents({"status": "ACTIVE"})
    pending_reports = await db.reports.count_documents({"status": "OPEN"})
    return {
        "zones_total": zones_total,
        "zones_predicted": len(preds),
        "severity_counts": sev_counts,
        "sensors_online": online,
        "sensors_offline": offline,
        "roads_blocked": blocked,
        "roads_at_risk": at_risk,
        "active_alerts": active_alerts,
        "pending_reports": pending_reports,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Batch inference — for the "run risk over all zones now" button
# ---------------------------------------------------------------------------
@api.post("/predictions/run-all")
async def run_all() -> Dict[str, Any]:
    zones = await db.zones.find({}).to_list(500)
    ok, failed = 0, 0
    for z in zones:
        _strip(z)
        try:
            result = await risk_service.predict_zone(z)
            if "error" in result:
                failed += 1
                continue
            result["response_priority"] = risk_service.classify_response_priority(result, z)
            await db.risk_predictions.update_one(
                {"zone_id": z["zone_id"]},
                {"$set": {**result, "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("run-all zone %s failed: %s", z.get("zone_id"), exc)
            failed += 1
    return {"ok": ok, "failed": failed}


# ---------------------------------------------------------------------------
# Explainability (LLM)
# ---------------------------------------------------------------------------
class ExplainRequest(BaseModel):
    severity: str
    factors: List[Dict[str, Any]]
    zone_name: str


@api.post("/explain")
async def explain(req: ExplainRequest) -> Dict[str, Any]:
    text = await explain_risk(req.severity, req.factors, req.zone_name)
    return {"explanation": text}


# ---------------------------------------------------------------------------
# Satellite (stub — clearly unavailable until Copernicus configured)
# ---------------------------------------------------------------------------
@api.get("/satellite/search")
async def satellite_search(zone_id: str) -> Dict[str, Any]:
    return {"status": "unavailable", "reason": "Copernicus credentials not configured", "source": "COPERNICUS"}


# ---------------------------------------------------------------------------
# Model feedback
# ---------------------------------------------------------------------------
class FeedbackReq(BaseModel):
    zone_id: str
    prediction_id: Optional[str] = None
    label: str  # CONFIRMED / FALSE_ALERT / UNKNOWN
    notes: Optional[str] = ""


@api.post("/model/feedback")
async def model_feedback(f: FeedbackReq) -> Dict[str, Any]:
    doc = {**f.model_dump(), "id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat()}
    await db.model_feedback.insert_one(doc)
    return _strip(doc)


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
