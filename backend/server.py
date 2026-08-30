"""NER-SLIDE Backend — Supabase/PostGIS API."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.services.ml_service import ml_service
from app.services import weather_service, risk_service, terrain_service
from app.services.llm_service import explain_risk, translate_alert, SUPPORTED_LANGUAGES
from app.db import supabase_repo as repo
from app.auth_middleware import install_auth_middleware
from app.authorization import require_roles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("nerslide")

app = FastAPI(title="NER-SLIDE API", version="2.1.0-supabase")
api = APIRouter(prefix="/api")
install_auth_middleware(app)


@app.on_event("startup")
async def startup() -> None:
    await repo.client()
    log.info("Supabase persistence initialized")


@app.on_event("shutdown")
async def shutdown() -> None:
    await repo.close()


@api.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "model_loaded": ml_service.model is not None, "model_version": ml_service.version,
            "feature_count": len(ml_service.feature_list()), "persistence": "SUPABASE", "timestamp": datetime.now(timezone.utc).isoformat()}


@api.get("/model/info")
async def model_info() -> Dict[str, Any]:
    return {"version": ml_service.version, "features": ml_service.feature_list(), "threshold_operational": 0.15,
            "severity_bands": [{"label": x[0], "lo": x[1], "hi": x[2]} for x in [("LOW",0.0,0.15),("MEDIUM",0.15,0.35),("HIGH",0.35,0.65),("CRITICAL",0.65,1.01)]]}


@api.get("/me")
async def me(request: Request) -> Dict[str, Any]:
    return {"user": request.state.supabase_user, "profile": request.state.profile}


class PredictRequest(BaseModel):
    features: Dict[str, float]


@api.post("/predictions/predict")
async def predict(req: PredictRequest) -> Dict[str, Any]:
    try:
        return ml_service.predict_one(req.features)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ZonePredictRequest(BaseModel):
    zone_id: str
    rainfall_override: Optional[Dict[str, float]] = None


@api.post("/predictions/zone")
async def predict_zone_api(req: ZonePredictRequest, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zone = await repo.get_zone(req.zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="zone_not_found")
    result = await risk_service.predict_zone(zone, req.rainfall_override)
    if "error" in result:
        raise HTTPException(status_code=424, detail=result)
    priority = risk_service.classify_response_priority(result, zone)
    return await repo.upsert_prediction(req.zone_id, result, priority)


@api.get("/predictions/{zone_id}")
async def get_latest_prediction(zone_id: str) -> Dict[str, Any]:
    result = await repo.get_latest_prediction(zone_id)
    if not result:
        raise HTTPException(status_code=404, detail="no_prediction_yet")
    return result


@api.post("/predictions/run-all")
async def run_all(_=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zones = await repo.list_zones()
    ok = failed = 0
    for zone in zones:
        try:
            result = await risk_service.predict_zone(zone)
            if "error" in result:
                failed += 1
                continue
            priority = risk_service.classify_response_priority(result, zone)
            await repo.upsert_prediction(zone["zone_id"], result, priority)
            ok += 1
        except Exception as exc:
            log.warning("run-all zone=%s failed=%s", zone.get("zone_id"), exc)
            failed += 1
    return {"ok": ok, "failed": failed}


async def _zones_payload(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    zones = await repo.list_zones(state)
    predictions = {p.get("zone_id"): p for p in await repo.get_predictions()}
    out = []
    for zone in zones:
        p = predictions.get(zone["zone_id"])
        if p:
            zone["latest"] = {"severity": p.get("severity"), "risk_score": p.get("risk_score"), "probability": p.get("probability"), "updated_at": p.get("predicted_at")}
        if severity and (not p or p.get("severity") != severity):
            continue
        out.append(zone)
    return out


@api.get("/zones")
async def list_zones(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    return await _zones_payload(state, severity)


@api.get("/public/zones")
async def public_zones(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    return await _zones_payload(state, severity)


@api.get("/zones/{zone_id}")
async def get_zone(zone_id: str) -> Dict[str, Any]:
    zone = await repo.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="zone_not_found")
    p = await repo.get_latest_prediction(zone_id)
    if p: zone["latest"] = p
    zone["sensors"] = [s for s in await repo.list_sensors() if s.get("zone_id") == zone.get("id")]
    zone["roads_nearby"] = await repo.nearest_roads(zone["centroid"]["lat"], zone["centroid"]["lon"], 3)
    zone["villages_nearby"] = await repo.nearest_villages(zone["centroid"]["lat"], zone["centroid"]["lon"], 3)
    return zone


async def _gis_risk_zones() -> Dict[str, Any]:
    zones = await repo.list_zones()
    predictions = {p.get("zone_id"): p for p in await repo.get_predictions()}
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": z.get("geometry"), "properties": {"zone_id": z["zone_id"], "name": z["name"], "state": z["state"], "district": z["district"], "severity": (predictions.get(z["zone_id"]) or {}).get("severity", "UNKNOWN"), "risk_score": (predictions.get(z["zone_id"]) or {}).get("risk_score"), "probability": (predictions.get(z["zone_id"]) or {}).get("probability"), "population": z.get("population")}} for z in zones]}


@api.get("/gis/risk-zones")
async def gis_risk_zones() -> Dict[str, Any]:
    return await _gis_risk_zones()


@api.get("/public/gis/risk-zones")
async def public_gis_risk_zones() -> Dict[str, Any]:
    return await _gis_risk_zones()


async def _gis_heatmap() -> List[Dict[str, Any]]:
    zones = await repo.list_zones()
    predictions = {p.get("zone_id"): p for p in await repo.get_predictions()}
    return [{"lat": z["centroid"]["lat"], "lon": z["centroid"]["lon"], "intensity": float((predictions.get(z["zone_id"]) or {}).get("probability", 0.0)), "zone_id": z["zone_id"], "severity": (predictions.get(z["zone_id"]) or {}).get("severity", "UNKNOWN")} for z in zones]


@api.get("/gis/heatmap")
async def gis_heatmap() -> List[Dict[str, Any]]: return await _gis_heatmap()

@api.get("/public/gis/heatmap")
async def public_gis_heatmap() -> List[Dict[str, Any]]: return await _gis_heatmap()


async def _gis_sensors() -> Dict[str, Any]:
    sensors = await repo.list_sensors()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}, "properties": s} for s in sensors]}

@api.get("/gis/sensors")
async def gis_sensors() -> Dict[str, Any]: return await _gis_sensors()


async def _gis_roads() -> Dict[str, Any]:
    roads = await repo.list_roads()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": r["geometry"], "properties": {k: v for k, v in r.items() if k != "geometry"}} for r in roads]}

@api.get("/gis/roads")
async def gis_roads() -> Dict[str, Any]: return await _gis_roads()

@api.get("/public/gis/roads")
async def public_gis_roads() -> Dict[str, Any]: return await _gis_roads()


async def _gis_villages() -> Dict[str, Any]:
    villages = await repo.list_villages()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [v["lon"], v["lat"]]}, "properties": v} for v in villages]}

@api.get("/gis/villages")
async def gis_villages() -> Dict[str, Any]: return await _gis_villages()

@api.get("/public/gis/villages")
async def public_gis_villages() -> Dict[str, Any]: return await _gis_villages()


@api.get("/gis/reports")
async def gis_reports() -> Dict[str, Any]:
    reports = await repo.list_reports(200)
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}, "properties": r} for r in reports]}


@api.get("/gis/alerts")
async def gis_alerts() -> List[Dict[str, Any]]: return await repo.list_alerts(50)

@api.get("/public/alerts")
async def public_alerts(limit: int = 50) -> List[Dict[str, Any]]: return await repo.list_alerts(limit)


@api.get("/gis/nearby")
async def gis_nearby(lat: float, lon: float) -> Dict[str, Any]:
    return {"roads": await repo.nearest_roads(lat, lon, 3), "villages": await repo.nearest_villages(lat, lon, 3)}


@api.get("/weather")
async def weather(latitude: float, longitude: float) -> Dict[str, Any]: return await weather_service.get_current(latitude, longitude)

@api.get("/weather/history")
async def weather_history(latitude: float, longitude: float, days: int = 30) -> Dict[str, Any]: return await weather_service.get_history(latitude, longitude, days)

@api.get("/terrain/elevation")
async def terrain_elevation(latitude: float, longitude: float) -> Dict[str, Any]: return await weather_service.get_elevation(latitude, longitude)


@api.post("/terrain/recompute")
async def terrain_recompute(zone_id: Optional[str] = None, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zones = [await repo.get_zone(zone_id)] if zone_id else await repo.list_zones()
    zones = [z for z in zones if z]
    c = await repo.client(); ok = failed = 0
    for zone in zones:
        try:
            t = await terrain_service.compute_dem_features(zone["centroid"]["lat"], zone["centroid"]["lon"])
            await c.table("zones").update({**t, "terrain_source": "DEM"}).eq("zone_id", zone["zone_id"]).execute()
            await c.table("terrain_data").upsert({"zone_id": zone["id"], **t, "source": "DEM", "fetched_at": datetime.now(timezone.utc).isoformat()}, on_conflict="zone_id").execute(); ok += 1
        except Exception as exc: log.warning("DEM recompute failed zone=%s reason=%s", zone.get("zone_id"), exc); failed += 1
    return {"ok": ok, "failed": failed, "source": "OPEN_METEO_ELEVATION"}


@api.get("/sensors")
async def sensors_list(status: Optional[str] = None) -> List[Dict[str, Any]]: return await repo.list_sensors(status)

class SensorReading(BaseModel):
    sensor_id: str
    measurement_type: str
    value: float

@api.post("/sensors/readings")
async def post_reading(r: SensorReading, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    try: return await repo.insert_sensor_reading(r.sensor_id, r.measurement_type, r.value)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


class ReportCreate(BaseModel):
    lat: float
    lon: float
    report_type: str
    description: Optional[str] = ""
    photo_url: Optional[str] = None
    reporter_role: Optional[str] = None
    reporter_name: Optional[str] = None
    client_uuid: Optional[str] = None

@api.post("/reports")
async def create_report(r: ReportCreate, request: Request) -> Dict[str, Any]:
    user = request.state.supabase_user
    profile = request.state.profile
    if r.client_uuid:
        existing = await repo.find_report_by_client_uuid(r.client_uuid)
        if existing: return existing
    if r.report_type == "ROAD_BLOCKAGE":
        near = await repo.nearest_roads(r.lat, r.lon, 1)
        if near and profile["role"] in {"ADMIN", "AUTHORITY", "FIELD_OFFICER"}:
            await repo.update_road_status(near[0]["road_id"], "BLOCKED")
    zones = await repo.list_zones()
    if not zones: raise HTTPException(status_code=503, detail="no_zones_configured")
    zone = min(zones, key=lambda z: ((z["centroid"]["lat"]-r.lat)**2 + (z["centroid"]["lon"]-r.lon)**2))
    payload = r.model_dump()
    payload.update({"reporter_id": user["id"], "reporter_role": profile["role"], "reporter_name": profile.get("full_name") or user.get("email") or "User"})
    result = await repo.insert_report(payload)
    result["zone_id"] = zone["zone_id"]
    return result

@api.get("/reports")
async def list_reports(limit: int = 100) -> List[Dict[str, Any]]: return await repo.list_reports(limit)


@api.post("/reports/{report_id}/media")
async def attach_report_media(report_id: str, media: Dict[str, Any], request: Request) -> Dict[str, Any]:
    if not await repo.can_access_report(report_id, request.state.supabase_user["id"], request.state.profile["role"]):
        raise HTTPException(status_code=403, detail="report_media_forbidden")
    return await repo.insert_report_media(report_id, media)


class AlertCreate(BaseModel):
    zone_id: str
    severity: str
    reason: str
    recommended_action: str = "Evacuate at-risk slopes; halt construction; notify local authorities."

@api.post("/alerts")
async def create_alert(a: AlertCreate, request: Request, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zone = await repo.get_zone(a.zone_id)
    if not zone: raise HTTPException(status_code=404, detail="zone_not_found")
    text = f"{a.severity} landslide risk near {zone['name']} ({zone['district']}, {zone['state']}). Reason: {a.reason}. Action: {a.recommended_action}"
    translations = await translate_alert(text, list(SUPPORTED_LANGUAGES.keys()))
    return await repo.create_alert({"zone_id": zone["id"], "severity": a.severity, "reason": a.reason, "recommended_action": a.recommended_action, "translations": translations, "status": "ACTIVE", "created_by": request.state.supabase_user["id"]})

@api.get("/alerts")
async def list_alerts(limit: int = 100) -> List[Dict[str, Any]]: return await repo.list_alerts(limit)

@api.get("/notifications")
async def list_notifications(limit: int = 200) -> List[Dict[str, Any]]: return await repo.list_notifications(limit)

@api.get("/notifications/status")
async def notification_status() -> Dict[str, Any]:
    configured = bool(os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"))
    return {"provider": "FCM_HTTP_V1" if configured else "LOG_ONLY", "firebase_configured": configured}


class RecipientCreate(BaseModel):
    name: str
    phone: str
    role: str = "AUTHORITY"
    district: Optional[str] = None
    language: str = "en"

@api.post("/recipients")
async def create_recipient(r: RecipientCreate, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]: return await repo.create_recipient(r.model_dump())

@api.get("/recipients")
async def list_recipients(_=Depends(require_roles("AUTHORITY"))) -> List[Dict[str, Any]]: return await repo.list_recipients()

@api.delete("/recipients/{recipient_id}")
async def delete_recipient(recipient_id: str, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]: return {"deleted": await repo.delete_recipient(recipient_id)}


@api.get("/response/priorities")
async def response_priorities(_=Depends(require_roles("AUTHORITY"))) -> List[Dict[str, Any]]:
    predictions = await repo.get_predictions(); out = []
    for p in predictions:
        zone = await repo.get_zone(p["zone_id"])
        if not zone: continue
        priority = risk_service.classify_response_priority(p, zone)
        out.append({"zone_id": p["zone_id"], "zone_name": zone["name"], "state": zone["state"], "district": zone["district"], "severity": p.get("severity"), "risk_score": p.get("risk_score"), **priority})
    order = {"P1":0,"P2":1,"P3":2,"P4":3}; return sorted(out, key=lambda x: order.get(x["priority"],9))

@api.get("/dashboard/summary")
async def dashboard_summary() -> Dict[str, Any]: return {**await repo.dashboard_counts(), "timestamp": datetime.now(timezone.utc).isoformat()}

class ExplainRequest(BaseModel):
    severity: str
    factors: List[Dict[str, Any]]
    zone_name: str

@api.post("/explain")
async def explain(req: ExplainRequest) -> Dict[str, Any]: return {"explanation": await explain_risk(req.severity, req.factors, req.zone_name)}

@api.get("/satellite/search")
async def satellite_search(zone_id: str) -> Dict[str, Any]: return {"status":"unavailable","reason":"Copernicus credentials not configured","source":"COPERNICUS","zone_id":zone_id}

class FeedbackReq(BaseModel):
    zone_id: str
    prediction_id: Optional[str] = None
    label: str
    notes: Optional[str] = ""

@api.post("/model/feedback")
async def model_feedback(f: FeedbackReq, request: Request, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    payload = f.model_dump()
    payload["created_by"] = request.state.supabase_user["id"]
    return await repo.create_feedback(payload)

@app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=[x.strip() for x in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if x.strip()], allow_methods=["*"], allow_headers=["*"])
