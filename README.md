# NER-SLIDE

AI-powered landslide early warning, monitoring, GIS, and disaster-response platform
for the North Eastern Region (NER) of India — built for Smart India Hackathon.

## What's inside
- **V5 RandomForest ML model** (13 features) loaded once at process start
- **Real weather** via Open-Meteo (forecast + historical rainfall + elevation)
- **Interactive GIS map** (Leaflet + OSM tiles) with risk zones, heatmap, roads,
  villages, sensors, reports and per-severity color coding
- **Zone detail view** with "Why is this zone at risk?" (LLM-generated
  explanation, rule-based fallback)
- **Response prioritization** (P1-P4) using severity + population + road status
- **Multilingual alerts** (English, Assamese, Khasi, Mizo, Nepali, Bodo)
- **Field officer / citizen portal** with GPS capture, photo upload, and an
  offline-first localStorage sync queue
- **Analytics** (severity distribution, priority stack, Open-Meteo 30-day rainfall)

## Quickstart
```
supervisorctl restart backend frontend
```
Backend: `http://localhost:8001/api/health`
Frontend: `http://localhost:3000/`

## Model files
Place the V5 trained artifact at `backend/ml/v5_final_model.joblib`.
Training report + threshold analysis live under `model/`.

## Data-source transparency
Every record is tagged with a `source` field (OPEN_METEO, OSM_DEMO, DEMO, etc.)
so operators can see exactly what's real and what's demo data.

## Docs
- `ARCHITECTURE.md` — modular monolith layout
- `API.md` — full endpoint list
- `MODEL_INTEGRATION.md` — V5 features / thresholds / regression tests
- `DEMO.md` — 5-minute SIH demonstration script
