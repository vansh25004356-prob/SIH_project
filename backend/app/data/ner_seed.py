"""Seed data for the North Eastern Region.

Contains a compact demo set of zones spanning all 8 NER states with plausible
terrain metadata (elevation_m / slope_deg / aspect / curvature) so the V5 model
can generate real predictions during the SIH demo. Every seeded item is tagged
`terrain_source: DEMO` for transparency.

Real DEM-derived terrain must replace these values before operational use.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

# (state, district, zone_name, lat, lon, elevation_m, slope_deg, aspect_deg, curvature_1_m, population)
NER_ZONES: List[Dict[str, Any]] = []

_RAW = [
    # Meghalaya (heavy rainfall belt)
    ("Meghalaya", "East Khasi Hills", "Cherrapunji Ridge", 25.2700, 91.7320, 1430, 32, 210, 0.0035, 14000),
    ("Meghalaya", "East Khasi Hills", "Shillong North Slope", 25.5788, 91.8933, 1520, 22, 45, 0.0012, 34000),
    ("Meghalaya", "West Jaintia Hills", "Jowai Escarpment", 25.4520, 92.2000, 1380, 28, 130, 0.0022, 8000),
    ("Meghalaya", "West Khasi Hills", "Nongstoin Bluff", 25.5210, 91.2670, 1450, 30, 200, 0.0028, 6000),
    # Assam
    ("Assam", "Dima Hasao", "Haflong Cut Slope", 25.1670, 93.0170, 680, 26, 300, 0.0018, 12000),
    ("Assam", "Karbi Anglong", "Diphu Hill Zone", 25.8420, 93.4310, 460, 18, 90, 0.0009, 22000),
    ("Assam", "Kamrup Metro", "Guwahati Hill Fringe", 26.1445, 91.7362, 350, 12, 60, 0.0005, 96000),
    # Arunachal Pradesh
    ("Arunachal Pradesh", "Papum Pare", "Itanagar Hill Belt", 27.0844, 93.6053, 950, 24, 180, 0.0021, 44000),
    ("Arunachal Pradesh", "West Kameng", "Bomdila Slope", 27.2620, 92.4160, 2530, 30, 140, 0.003, 8000),
    ("Arunachal Pradesh", "Tawang", "Sela Approach", 27.4990, 92.1050, 3500, 34, 20, 0.004, 3000),
    ("Arunachal Pradesh", "Lohit", "Tezu Highway Zone", 27.9200, 96.1670, 700, 20, 240, 0.0016, 5000),
    # Sikkim
    ("Sikkim", "East Sikkim", "Gangtok North Bluff", 27.3389, 88.6065, 1650, 30, 280, 0.0033, 100000),
    ("Sikkim", "North Sikkim", "Chungthang Corridor", 27.6000, 88.6500, 1780, 34, 190, 0.0036, 4000),
    ("Sikkim", "South Sikkim", "Namchi Slope", 27.1667, 88.3667, 1310, 24, 110, 0.0019, 12000),
    # Mizoram
    ("Mizoram", "Aizawl", "Aizawl Hill Face", 23.7271, 92.7176, 1130, 28, 160, 0.0025, 293000),
    ("Mizoram", "Lunglei", "Lunglei Ridge", 22.8880, 92.7340, 1010, 26, 90, 0.002, 57000),
    # Nagaland
    ("Nagaland", "Kohima", "Kohima Escarpment", 25.6751, 94.1086, 1440, 30, 220, 0.0029, 100000),
    ("Nagaland", "Mokokchung", "Mokokchung Slope", 26.3230, 94.5150, 1325, 24, 60, 0.0018, 35000),
    # Manipur
    ("Manipur", "Senapati", "Mao Cut", 25.5410, 94.1200, 1650, 32, 170, 0.0031, 6000),
    ("Manipur", "Churachandpur", "Churachandpur Bluff", 24.3330, 93.6670, 910, 22, 300, 0.0015, 20000),
    # Tripura
    ("Tripura", "Dhalai", "Kamalpur Hillock", 24.2000, 91.8330, 220, 12, 50, 0.0004, 8000),
    ("Tripura", "North Tripura", "Jampui Range", 24.1500, 92.2500, 950, 20, 130, 0.0012, 5000),
]

for state, district, name, lat, lon, elev, slope, aspect_deg, curv, pop in _RAW:
    rad = math.radians(aspect_deg)
    NER_ZONES.append({
        "zone_id": f"NER-{len(NER_ZONES) + 1:03d}",
        "name": name,
        "state": state,
        "district": district,
        "centroid": {"lat": lat, "lon": lon},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon - 0.05, lat - 0.05], [lon + 0.05, lat - 0.05],
                [lon + 0.05, lat + 0.05], [lon - 0.05, lat + 0.05],
                [lon - 0.05, lat - 0.05],
            ]],
        },
        "terrain": {
            "elevation_m": float(elev),
            "slope_deg": float(slope),
            "aspect_sin": round(math.sin(rad), 4),
            "aspect_cos": round(math.cos(rad), 4),
            "curvature_1_m": float(curv),
        },
        "terrain_source": "DEMO",
        "population": pop,
    })


# Demo sensors distributed across a few high-risk zones
NER_SENSORS: List[Dict[str, Any]] = []
_SENSOR_TYPES = ["soil_moisture", "tilt", "pore_pressure", "rain_gauge"]
for i, z in enumerate(NER_ZONES[:12]):
    for j, stype in enumerate(_SENSOR_TYPES[: 2 + (i % 3)]):
        NER_SENSORS.append({
            "sensor_id": f"SEN-{i * 4 + j + 1:03d}",
            "zone_id": z["zone_id"],
            "type": stype,
            "lat": z["centroid"]["lat"] + 0.005 * (j - 1),
            "lon": z["centroid"]["lon"] + 0.005 * (j - 1),
            "status": "ONLINE" if (i + j) % 5 != 4 else "OFFLINE",
            "battery": max(30, 100 - (i * 3 + j * 4) % 70),
            "last_seen_iso": None,
            "source": "DEMO",
        })


# Demo road segments (LineString) — 3 highway segments per pilot state
NER_ROADS: List[Dict[str, Any]] = []
_ROAD_SEEDS = [
    ("NH-6 Shillong-Cherrapunji", [(91.8933, 25.5788), (91.85, 25.45), (91.7320, 25.2700)], "OPEN"),
    ("NH-10 Gangtok-Chungthang", [(88.6065, 27.3389), (88.63, 27.47), (88.6500, 27.6000)], "AT_RISK"),
    ("NH-2 Kohima-Mokokchung", [(94.1086, 25.6751), (94.30, 25.95), (94.5150, 26.3230)], "OPEN"),
    ("NH-54 Aizawl-Lunglei", [(92.7176, 23.7271), (92.72, 23.30), (92.7340, 22.8880)], "OPEN"),
    ("NH-13 Bomdila-Tawang", [(92.4160, 27.2620), (92.30, 27.38), (92.1050, 27.4990)], "AT_RISK"),
    ("NH-27 Guwahati-Diphu", [(91.7362, 26.1445), (92.5, 26.0), (93.4310, 25.8420)], "OPEN"),
]
for i, (name, coords, status) in enumerate(_ROAD_SEEDS):
    NER_ROADS.append({
        "road_id": f"ROAD-{i + 1:03d}",
        "name": name,
        "status": status,
        "geometry": {"type": "LineString", "coordinates": coords},
        "source": "OSM_DEMO",
    })


# Demo villages
NER_VILLAGES: List[Dict[str, Any]] = []
_VILLAGE_SEEDS = [
    ("Sohra", "Meghalaya", 25.29, 91.72, 3200),
    ("Mawlynnong", "Meghalaya", 25.20, 91.92, 950),
    ("Chungthang", "Sikkim", 27.60, 88.65, 2400),
    ("Lachung", "Sikkim", 27.6899, 88.7430, 1200),
    ("Sela", "Arunachal Pradesh", 27.50, 92.10, 400),
    ("Tuirial", "Mizoram", 23.78, 92.79, 800),
    ("Ukhrul", "Manipur", 25.10, 94.36, 3200),
    ("Mao", "Manipur", 25.54, 94.12, 2100),
    ("Haflong", "Assam", 25.16, 93.02, 4400),
]
for i, (name, state, lat, lon, pop) in enumerate(_VILLAGE_SEEDS):
    NER_VILLAGES.append({
        "village_id": f"VIL-{i + 1:03d}",
        "name": name, "state": state,
        "location": {"lat": lat, "lon": lon},
        "population": pop,
        "source": "OSM_DEMO",
    })
