"""Supabase persistence repository for the Mongo -> Postgres migration."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import AsyncClient, acreate_client
from app.services.push_service import send_to_tokens

_client: Optional[AsyncClient] = None

async def client() -> AsyncClient:
    global _client
    if _client is not None: return _client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key: raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    _client = await acreate_client(url, key); return _client

async def close() -> None:
    global _client
    if _client is not None:
        try: await _client.auth.sign_out()
        finally: _client = None

def _zone(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": row.get("id"), "zone_id": row.get("zone_id"), "name": row.get("name"), "district": row.get("district"), "state": row.get("state"), "centroid": row.get("centroid") or {}, "geometry": row.get("geometry"), "population": row.get("population"), "terrain": {k: row[k] for k in ("elevation_m", "slope_deg", "aspect_sin", "aspect_cos", "curvature_1_m") if row.get(k) is not None}, "terrain_source": row.get("terrain_source"), "road_blocked": row.get("road_blocked", False), "isolated_villages": row.get("isolated_villages", 0), "recent_field_report": row.get("recent_field_report", False), "created_at": row.get("created_at"), "updated_at": row.get("updated_at")}

async def list_zones(state: Optional[str] = None) -> List[Dict[str, Any]]:
    c = await client(); res = await c.rpc("list_zones_geojson", {"p_state": state}).execute(); return [_zone(x) for x in (res.data or [])]
async def get_zone(zone_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.rpc("get_zone_geojson",{"p_zone_id":zone_id}).execute(); return _zone(res.data[0]) if res.data else None
async def count_zones() -> int:
    c=await client(); res=await c.table("zones").select("id",count="exact").execute(); return int(res.count or 0)
async def nearest_roads(lat: float, lon: float, limit: int = 3) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("nearby_roads",{"p_lat":lat,"p_lon":lon,"p_limit":limit}).execute(); return [{"road_id":x["road_id"],"name":x["name"],"status":x["status"],"geometry":x["geometry"],"distance_km":x["distance_km"]} for x in (res.data or [])]
async def nearest_villages(lat: float, lon: float, limit: int = 3) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("nearby_villages",{"p_lat":lat,"p_lon":lon,"p_limit":limit}).execute(); return [dict(x) for x in (res.data or [])]
async def list_sensors(status: Optional[str] = None) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_sensors_geojson",{"p_status":status}).execute(); return [{"sensor_id":x["sensor_id"],"zone_id":x.get("zone_id"),"type":x["sensor_type"],"status":x["status"],"lat":x["lat"],"lon":x["lon"],"metadata":x.get("metadata") or {},"last_seen_iso":x.get("last_seen_at")} for x in (res.data or [])]
async def insert_sensor_reading(sensor_id: str, measurement_type: str, value: float) -> Dict[str, Any]:
    c=await client(); sensor=await c.table("sensors").select("id").eq("sensor_id",sensor_id).maybe_single().execute()
    if not sensor.data: raise ValueError("sensor_not_found")
    now=datetime.now(timezone.utc).isoformat(); res=await c.table("sensor_readings").insert({"sensor_id":sensor.data["id"],"measurement_type":measurement_type,"value":value,"recorded_at":now}).select("*").single().execute(); await c.table("sensors").update({"last_seen_at":now,"updated_at":now}).eq("id",sensor.data["id"]).execute(); return {"id":str(res.data["id"]),"sensor_id":sensor_id,"measurement_type":measurement_type,"value":value,"timestamp":now}
async def list_roads() -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_roads_geojson").execute(); return [dict(x) for x in (res.data or [])]
async def update_road_status(road_id: str, status: str) -> None:
    c=await client(); await c.table("roads").update({"status":status,"updated_at":datetime.now(timezone.utc).isoformat()}).eq("road_id",road_id).execute()
async def list_villages() -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_villages_geojson").execute(); return [dict(x) for x in (res.data or [])]
async def find_report_by_client_uuid(client_uuid: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("reports").select("*").eq("client_uuid",client_uuid).maybe_single().execute(); return res.data
async def insert_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); row={"client_uuid":payload.get("client_uuid"),"reporter_id":payload.get("reporter_id"),"lat":payload["lat"],"lon":payload["lon"],"report_type":payload["report_type"],"description":payload.get("description") or "","reporter_role":payload.get("reporter_role","CITIZEN"),"status":"SUBMITTED"}; res=await c.table("reports").insert(row).select("*").single().execute(); return dict(res.data)
async def can_access_report(report_id: str, user_id: str, role: str) -> bool:
    if role in {"ADMIN","AUTHORITY","FIELD_OFFICER"}: return True
    c=await client(); res=await c.table("reports").select("id").eq("id",report_id).eq("reporter_id",user_id).maybe_single().execute(); return bool(res.data)
async def insert_report_media(report_id: str, media: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); row={"report_id":report_id,"storage_path":media["storage_path"],"media_type":media.get("media_type","PHOTO"),"mime_type":media.get("mime_type"),"size_bytes":media.get("size_bytes")}; res=await c.table("report_media").insert(row).select("*").single().execute(); return dict(res.data)
async def list_reports(limit: int = 100) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("reports").select("*").order("created_at",desc=True).limit(limit).execute(); return [dict(x) for x in (res.data or [])]
async def create_alert(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); alert=dict((await c.table("alerts").insert(payload).select("*").single().execute()).data)
    devices=await c.table("user_devices").select("user_id,fcm_token").eq("is_active",True).execute()
    tokens=[x["fcm_token"] for x in (devices.data or []) if x.get("fcm_token")]
    title=f"{alert['severity']} landslide alert"
    body=payload.get("reason") or "New landslide risk alert"
    data={"alert_id":str(alert["id"]),"severity":str(alert["severity"]),"zone_id":str(alert.get("zone_id") or "")}
    if tokens and os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"):
        delivery=await send_to_tokens(tokens,title,body,data)
        for device in devices.data or []:
            if device.get("fcm_token"):
                status="SENT" if device["fcm_token"] in tokens and delivery["failed"] < len(tokens) else "FAILED"
                await c.table("notifications").insert({"user_id":device.get("user_id"),"alert_id":alert["id"],"channel":"PUSH","status":status,"provider":"FCM_HTTP_V1","payload":data,"sent_at":datetime.now(timezone.utc).isoformat() if status=="SENT" else None}).execute()
    return alert
async def list_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("alerts").select("*").order("created_at",desc=True).limit(limit).execute(); return [dict(x) for x in (res.data or [])]
async def list_notifications(limit: int = 200) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("notifications").select("*").order("created_at",desc=True).limit(limit).execute(); return [dict(x) for x in (res.data or [])]
async def create_notification(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); res=await c.table("notifications").insert(payload).select("*").single().execute(); return dict(res.data)
async def list_active_device_tokens() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("user_devices").select("user_id,fcm_token,platform").eq("is_active",True).execute(); return [dict(x) for x in (res.data or [])]
async def deactivate_device_token(token: str) -> None:
    c=await client(); await c.table("user_devices").update({"is_active":False}).eq("fcm_token",token).execute()
async def create_recipient(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); res=await c.table("recipients").insert(payload).select("*").single().execute(); return dict(res.data)
async def list_recipients() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("recipients").select("*").order("created_at",desc=True).execute(); return [dict(x) for x in (res.data or [])]
async def delete_recipient(recipient_id: str) -> int:
    c=await client(); res=await c.table("recipients").delete().eq("id",recipient_id).execute(); return len(res.data or [])
async def get_predictions() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("risk_predictions").select("*,zones!inner(zone_id,name,state,district,population,road_blocked,isolated_villages,recent_field_report)").order("predicted_at",desc=True).execute(); out=[]
    for x in res.data or []:
        z=x.pop("zones",{}) or {}; x["zone_id"]=z.get("zone_id"); x["zone_name"]=z.get("name"); x["state"]=z.get("state"); x["district"]=z.get("district"); out.append(x)
    return out
async def get_latest_prediction(zone_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); zone=await c.table("zones").select("id,zone_id").eq("zone_id",zone_id).maybe_single().execute()
    if not zone.data:return None
    res=await c.table("risk_predictions").select("*").eq("zone_id",zone.data["id"]).order("predicted_at",desc=True).limit(1).maybe_single().execute()
    if not res.data:return None
    row=dict(res.data); row["zone_id"]=zone_id; return row
async def upsert_prediction(zone_id: str, result: Dict[str, Any], priority: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); zone=await c.table("zones").select("id").eq("zone_id",zone_id).single().execute(); row={"zone_id":zone.data["id"],"probability":result["probability"],"risk_score":result["risk_score"],"prediction":result["prediction"],"severity":result["severity"],"priority":priority["priority"],"model_version":result["model_version"],"features_used":result.get("features_used") or {},"contributing_factors":result.get("contributing_factors") or [],"source_map":result.get("source_map") or {},"predicted_at":result.get("timestamp") or datetime.now(timezone.utc).isoformat()}; res=await c.table("risk_predictions").upsert(row,on_conflict="zone_id").select("*").single().execute(); out=dict(res.data); out["zone_id"]=zone_id; out["response_priority"]=priority; return out
async def create_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); zone=await c.table("zones").select("id").eq("zone_id",payload["zone_id"]).single().execute(); row={"zone_id":zone.data["id"],"label":payload["label"],"notes":payload.get("notes") or "","created_by":payload.get("created_by")};
    if payload.get("prediction_id"): row["prediction_id"]=payload["prediction_id"]
    res=await c.table("model_feedback").insert(row).select("*").single().execute(); return dict(res.data)
async def dashboard_counts() -> Dict[str, Any]:
    c=await client(); zones=await c.table("zones").select("id",count="exact").execute(); sensors=await list_sensors(); roads=await list_roads(); preds=await get_predictions(); alerts=await c.table("alerts").select("id",count="exact").eq("status","ACTIVE").execute(); reports=await c.table("reports").select("id",count="exact").eq("status","SUBMITTED").execute(); sev={"LOW":0,"MEDIUM":0,"HIGH":0,"CRITICAL":0,"UNKNOWN":0}
    for p in preds: sev[p.get("severity","UNKNOWN")]=sev.get(p.get("severity","UNKNOWN"),0)+1
    return {"zones_total":int(zones.count or 0),"zones_predicted":len(preds),"severity_counts":sev,"sensors_online":sum(s.get("status")=="ONLINE" for s in sensors),"sensors_offline":sum(s.get("status")=="OFFLINE" for s in sensors),"roads_blocked":sum(r.get("status")=="BLOCKED" for r in roads),"roads_at_risk":sum(r.get("status")=="RESTRICTED" for r in roads),"active_alerts":int(alerts.count or 0),"pending_reports":int(reports.count or 0)}
