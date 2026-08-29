# API

All routes prefixed with `/api`.

## Health / model
- `GET /api/health` → status + model_version + feature_count
- `GET /api/model/info` → feature list + severity bands
- `POST /api/predictions/predict` — features → prediction
- `POST /api/predictions/zone` — {zone_id, rainfall_override?} → prediction + priority
- `POST /api/predictions/run-all` — batch predict all seeded zones
- `GET  /api/predictions/{zone_id}` — latest stored prediction

## Zones + GIS
- `GET /api/zones` [?state, ?severity]
- `GET /api/zones/{zone_id}`
- `GET /api/gis/risk-zones` — GeoJSON FeatureCollection (Polygons)
- `GET /api/gis/heatmap` — [{lat,lon,intensity,severity}]
- `GET /api/gis/sensors` / `roads` / `villages` / `reports` — GeoJSON
- `GET /api/gis/alerts`
- `GET /api/gis/nearby?lat=&lon=` — nearest roads + villages

## Weather + terrain
- `GET /api/weather?latitude=&longitude=` (Open-Meteo forecast normalized)
- `GET /api/weather/history?latitude=&longitude=&days=30` (Open-Meteo archive)
- `GET /api/terrain/elevation?latitude=&longitude=`

## Sensors
- `GET /api/sensors[?status=ONLINE|OFFLINE]`
- `POST /api/sensors/readings` {sensor_id, measurement_type, value}

## Reports (citizen / field officer)
- `POST /api/reports` {lat, lon, report_type, description, photo_url, reporter_role, client_uuid}
- `GET /api/reports[?limit=100]`
  - `ROAD_BLOCKAGE` reports auto-mark the nearest road as `BLOCKED`
  - `client_uuid` gives idempotency for offline-first sync

## Alerts
- `POST /api/alerts` {zone_id, severity, reason, recommended_action?}
  - Auto-translated into en, as, kha, lus, ne, brx via Emergent Universal LLM key
- `GET /api/alerts`

## Response prioritization
- `GET /api/response/priorities` → P1..P4 with known/unknown factor list

## Dashboard
- `GET /api/dashboard/summary` — headline counters

## Model feedback
- `POST /api/model/feedback` {zone_id, label: CONFIRMED|FALSE_ALERT|UNKNOWN, notes?}

## Explainability (LLM)
- `POST /api/explain` {severity, factors, zone_name} → natural-language "why?"

## Satellite (stub)
- `GET /api/satellite/search?zone_id=` — returns `{status: "unavailable"}` until Copernicus is configured
