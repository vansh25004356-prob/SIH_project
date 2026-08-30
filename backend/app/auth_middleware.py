"""Authentication middleware for protected API routes.

Health/model metadata stay public. All other /api endpoints require a valid
Supabase Auth bearer token. Authorization-sensitive writes should additionally
use route-level role checks where required.
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

PUBLIC_PATHS = {"/api/health", "/api/model/info", "/docs", "/openapi.json", "/redoc"}


def install_auth_middleware(app) -> None:
    @app.middleware("http")
    async def supabase_auth(request: Request, call_next: Callable):
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"detail": "authentication_required"}, status_code=401)
        token = auth[7:].strip()
        if not token:
            return JSONResponse({"detail": "authentication_required"}, status_code=401)

        supabase_url = os.environ.get("SUPABASE_URL")
        if not supabase_url:
            return JSONResponse({"detail": "supabase_not_configured"}, status_code=500)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{supabase_url.rstrip('/')}/auth/v1/user",
                    headers={"Authorization": f"Bearer {token}", "apikey": os.environ.get("SUPABASE_ANON_KEY", token)},
                )
            if response.status_code != 200:
                return JSONResponse({"detail": "invalid_or_expired_token"}, status_code=401)
            request.state.supabase_user = response.json()
        except httpx.HTTPError:
            return JSONResponse({"detail": "auth_service_unavailable"}, status_code=503)

        return await call_next(request)
