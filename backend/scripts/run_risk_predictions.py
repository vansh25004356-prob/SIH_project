"""Run V5 risk predictions against Supabase zones.

Usage from backend/:
  python scripts/run_risk_predictions.py
  python scripts/run_risk_predictions.py --zone NER-001
  python scripts/run_risk_predictions.py --zone NER-001 --demo-rainfall --persist

Without --persist this is a dry run and never writes predictions. The
--demo-rainfall flag is explicitly labelled SIMULATED and is intended only for
integration testing when Open-Meteo historical data is unavailable.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.db import supabase_repo as repo
from app.services import risk_service


DEMO_RAINFALL = {
    "rainfall_1d": 45.0,
    "rainfall_3d": 110.0,
    "rainfall_7d": 230.0,
    "rainfall_15d": 390.0,
    "rainfall_30d": 680.0,
    "max_rainfall_3d": 95.0,
    "max_rainfall_7d": 175.0,
    "rainy_days_7d": 5.0,
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", help="stable zone ID such as NER-001")
    parser.add_argument("--demo-rainfall", action="store_true", help="use clearly-labelled simulated rainfall for integration testing")
    parser.add_argument("--persist", action="store_true", help="write predictions to Supabase")
    args = parser.parse_args()

    zones = [await repo.get_zone(args.zone)] if args.zone else await repo.list_zones()
    zones = [z for z in zones if z]
    if not zones:
        raise SystemExit("No matching zones")

    results = []
    for zone in zones:
        result = await risk_service.predict_zone(zone, DEMO_RAINFALL if args.demo_rainfall else None)
        if "error" in result:
            results.append(result)
            continue
        priority = risk_service.classify_response_priority(result, zone)
        if args.persist:
            result = await repo.upsert_prediction(zone["zone_id"], result, priority)
        results.append({
            "zone_id": zone["zone_id"],
            "probability": result["probability"],
            "risk_score": result["risk_score"],
            "severity": result["severity"],
            "priority": priority,
            "source_map": result.get("source_map"),
            "persisted": args.persist,
        })

    print(json.dumps(results, indent=2, default=str))
    await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
