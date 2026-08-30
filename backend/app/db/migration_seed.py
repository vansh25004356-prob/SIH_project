"""One-shot migration of existing NER demo seed data into Supabase.

Run this only after SUPABASE_URL and SUPABASE_SECRET_KEY are configured.
The migration is idempotent on the application's stable IDs.
"""
from __future__ import annotations

from typing import Any, Dict

from app.data.ner_seed import NER_ROADS, NER_SENSORS, NER_VILLAGES, NER_ZONES
from app.db.supabase_db import init_supabase


def _point(lon: float, lat: float) -> str:
    return f"POINT({lon} {lat})"


def _polygon(geometry: Dict[str, Any]) -> str:
    rings = geometry["coordinates"]
    ring = ", ".join(f"{lon} {lat}" for lon, lat in rings[0])
    return f"POLYGON(({ring}))"


def _line(geometry: Dict[str, Any]) -> str:
    coords = ", ".join(f"{lon} {lat}" for lon, lat in geometry["coordinates"])
    return f"LINESTRING({coords})"


async def migrate() -> None:
    client = await init_supabase()

    for z in NER_ZONES:
        t = z.get("terrain", {})
        row = {
            "zone_id": z["zone_id"],
            "name": z["name"],
            "district": z.get("district"),
            "state": z.get("state"),
            "population": z.get("population"),
            "terrain_source": z.get("terrain_source", "DEMO"),
            "elevation_m": t.get("elevation_m"),
            "slope_deg": t.get("slope_deg"),
            "aspect_sin": t.get("aspect_sin"),
            "aspect_cos": t.get("aspect_cos"),
            "curvature_1_m": t.get("curvature_1_m"),
        }
        row["centroid"] = _point(z["centroid"]["lon"], z["centroid"]["lat"])
        row["boundary"] = _polygon(z["geometry"])
        await client.table("zones").upsert(row, on_conflict="zone_id").execute()

    zone_rows = await client.table("zones").select("id,zone_id").execute()
    zone_ids = {r["zone_id"]: r["id"] for r in (zone_rows.data or [])}

    for s in NER_SENSORS:
        await client.table("sensors").upsert({
            "sensor_id": s["sensor_id"],
            "zone_id": zone_ids.get(s.get("zone_id")),
            "sensor_type": s.get("type", "unknown"),
            "status": s.get("status", "OFFLINE"),
            "location": _point(s["lon"], s["lat"]),
            "metadata": {k: v for k, v in s.items() if k not in {"sensor_id", "zone_id", "type", "status", "lat", "lon"}},
            "last_seen_at": s.get("last_seen_iso"),
        }, on_conflict="sensor_id").execute()

    for r in NER_ROADS:
        await client.table("roads").upsert({
            "road_id": r["road_id"],
            "name": r.get("name"),
            "status": r.get("status") if r.get("status") in {"OPEN", "BLOCKED", "RESTRICTED", "UNKNOWN"} else "UNKNOWN",
            "geometry": _line(r["geometry"]),
            "metadata": {k: v for k, v in r.items() if k not in {"road_id", "name", "status", "geometry"}},
        }, on_conflict="road_id").execute()

    for v in NER_VILLAGES:
        await client.table("villages").upsert({
            "village_id": v["village_id"],
            "name": v["name"],
            "state": v.get("state"),
            "population": v.get("population"),
            "location": _point(v["location"]["lon"], v["location"]["lat"]),
            "metadata": {k: val for k, val in v.items() if k not in {"village_id", "name", "state", "population", "location"}},
        }, on_conflict="village_id").execute()


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
