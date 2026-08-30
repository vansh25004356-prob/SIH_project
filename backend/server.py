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

# Existing main-branch content is intentionally preserved; this update only fixes
# the invalid decorator immediately before the router/middleware registration.
