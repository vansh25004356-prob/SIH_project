# Architecture

Modular monolith (single FastAPI process) with clean service boundaries so any
component (ML, weather, GIS, alerts) can later be split into an independent
microservice without a rewrite.

```
frontend (React + Leaflet)
    ↓ REACT_APP_BACKEND_URL
FastAPI (backend/server.py)
    ├─ services/
    │   ├─ ml_service.py         # V5 model, loaded ONCE
    │   ├─ risk_service.py       # feature assembly + fusion + P1..P4 classification
    │   ├─ weather_service.py    # provider-agnostic cache + entrypoint
    │   ├─ llm_service.py        # Emergent Universal Key (explanation + translation)
    │   └─ (satellite / sensor / etc. stubs)
    ├─ providers/weather/
    │   ├─ open_meteo.py         # active provider
    │   └─ (imd.py stub — enabled when IMD credentials arrive)
    └─ data/ner_seed.py          # NER demo zones + sensors + roads + villages
                     ↓
                MongoDB (dev) / Supabase-Postgres+PostGIS (future)
```

## Why modular monolith?
- SIH judging is fast; a single deploy target keeps iteration cheap.
- Every external call goes through a service module; the frontend only ever
  sees normalized JSON. Swapping providers is a one-line change.

## Data-store adapter
Today the backend uses Motor + MongoDB. All zone/road/village/sensor documents
are stored as GeoJSON-friendly dicts; PostGIS spatial indexes can be added by
routing the same collections through a Postgres adapter later — no route/service
changes required.

## Feature-mapping rule
The 13 V5 features come from **only** two verified sources:

| feature group | source | notes |
|---------------|--------|-------|
| 8 rainfall features | Open-Meteo daily precipitation_sum | 30-day window, chronologically ordered |
| 5 terrain features | zone.terrain block | DEMO today; DEM in production |

If either source is unavailable, prediction returns `feature_unavailable`.
Fabrication is disallowed.
