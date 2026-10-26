"""Week Planner API (phase 1 scaffold).

Run from this folder:  ../.venv/bin/uvicorn main:app --reload --port 8000

Phase 2: accounts (auth.py), profile (profile_routes.py), calendar import and free time (calendar_routes.py).
Phase 3: the week description and follow-up questions (interview_routes.py, agents/interview_agent.py).
Phase 4: the plan proposal and its code-side validation (plan_routes.py, agents/planner_agent.py, lib/plan).
Approval and .ics export come in a later phase (see docs/design.md). Every model call must go
through lib/llm.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import auth
import calendar_routes
import interview_routes
import plan_routes
import profile_routes
import store
from lib.llm import LIMITS, MODEL_NAME, ai_enabled

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5200,http://127.0.0.1:5200").split(",")

store.init()


app = FastAPI(title="Week Planner API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


app.include_router(auth.router)
app.include_router(profile_routes.router)
app.include_router(calendar_routes.router)
app.include_router(interview_routes.router)
app.include_router(plan_routes.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Refuse state-changing requests from other sites (defence in depth; cookie sessions are also SameSite=Lax).
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"  # calendar-derived data must never be cached
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # The default 422 body echoes submitted values (which could be calendar text or a private link).
    fields = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
    return JSONResponse({"detail": "Invalid request", "errors": fields}, status_code=422)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "ai_enabled": ai_enabled(),
        "model": MODEL_NAME,
        "daily_cap_usd": LIMITS.daily_cap_usd,
        "spent_today_usd": round(store.spend_today(), 4),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("BACKEND_PORT", "8000")), reload=False)
