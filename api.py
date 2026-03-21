"""
api.py – Standalone REST API for the internship tracker database.

Endpoints:
    GET    /internships         – paginated list with filters
    GET    /internships/:id     – single internship
    POST   /internships         – add a new internship manually
    GET    /subscribers         – list subscribers
    POST   /subscribers         – add a subscriber
    DELETE /subscribers/:id     – remove a subscriber
    GET    /stats               – counts and latest entry

Auth: X-API-Key header

Run locally:
    API_KEY=secret DATABASE_URL=postgresql://... uvicorn api:app --reload

Railway start command:
    uvicorn api:app --host 0.0.0.0 --port $PORT
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from db import (
    init_db, get_db,
    Internship, Subscriber,
    list_internships, count_internships, get_recent,
    get_subscribers,
)
from sqlalchemy import func, or_

# ── auth ──────────────────────────────────────────────────────────────────────

API_KEY        = os.environ["API_KEY"]
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return key


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Internship Tracker API",
    description="Access internship listings and subscriber data.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    init_db()


# ── schemas ───────────────────────────────────────────────────────────────────

class InternshipOut(BaseModel):
    id:            int
    company:       str
    role:          str
    location:      Optional[str]
    apply_link:    Optional[str]
    simplify_link: Optional[str]
    age:           Optional[str]
    seen_at:       Optional[datetime]

    class Config:
        from_attributes = True


class InternshipIn(BaseModel):
    company:       str
    role:          str
    location:      Optional[str] = None
    apply_link:    Optional[str] = None
    simplify_link: Optional[str] = None
    age:           Optional[str] = None


class InternshipList(BaseModel):
    total:   int
    limit:   int
    offset:  int
    results: list[InternshipOut]


class SubscriberOut(BaseModel):
    chat_id:        int
    active:         int
    keyword_filter: Optional[str]
    joined_at:      Optional[datetime]

    class Config:
        from_attributes = True


class SubscriberIn(BaseModel):
    chat_id:        int
    keyword_filter: Optional[str] = None


class SubscriberList(BaseModel):
    total:   int
    results: list[SubscriberOut]


class Stats(BaseModel):
    total_internships: int
    total_subscribers: int
    active_subscribers: int
    latest_seen_at:    Optional[datetime]


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "total_internships": count_internships()}


# ── internships ───────────────────────────────────────────────────────────────

@app.get("/internships", response_model=InternshipList, tags=["Internships"])
def get_internships(
    search:   Optional[str] = Query(None, description="Search in company or role"),
    company:  Optional[str] = Query(None, description="Filter by company"),
    location: Optional[str] = Query(None, description="Filter by location"),
    limit:    int           = Query(50, ge=1, le=200),
    offset:   int           = Query(0, ge=0),
    _:        str           = Security(require_api_key),
):
    rows, total = list_internships(
        search=search, company=company,
        location=location, limit=limit, offset=offset,
    )
    return InternshipList(total=total, limit=limit, offset=offset, results=rows)


@app.get("/internships/{internship_id}", response_model=InternshipOut, tags=["Internships"])
def get_internship(
    internship_id: int,
    _: str = Security(require_api_key),
):
    with get_db() as db:
        row = db.query(Internship).filter_by(id=internship_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Internship not found")
    return row.to_dict()


@app.post("/internships", response_model=InternshipOut, status_code=201, tags=["Internships"])
def create_internship(
    body: InternshipIn,
    _:    str = Security(require_api_key),
):
    with get_db() as db:
        # Check for duplicate
        exists = db.query(Internship).filter_by(
            company=body.company,
            role=body.role,
            apply_link=body.apply_link,
        ).first()
        if exists:
            raise HTTPException(status_code=409, detail="Internship already exists")

        entry = Internship(**body.model_dump())
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.to_dict()


# ── subscribers ───────────────────────────────────────────────────────────────

@app.get("/subscribers", response_model=SubscriberList, tags=["Subscribers"])
def get_subscribers_endpoint(
    active_only: bool = Query(True),
    _:           str  = Security(require_api_key),
):
    rows = get_subscribers(active_only=active_only)
    return SubscriberList(total=len(rows), results=rows)


@app.post("/subscribers", response_model=SubscriberOut, status_code=201, tags=["Subscribers"])
def create_subscriber(
    body: SubscriberIn,
    _:    str = Security(require_api_key),
):
    with get_db() as db:
        existing = db.query(Subscriber).filter_by(chat_id=body.chat_id).first()
        if existing:
            # Re-activate if already exists
            existing.active = 1
            existing.keyword_filter = body.keyword_filter
            db.commit()
            db.refresh(existing)
            return existing.to_dict()

        sub = Subscriber(
            chat_id=body.chat_id,
            active=1,
            keyword_filter=body.keyword_filter,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub.to_dict()


@app.delete("/subscribers/{chat_id}", status_code=204, tags=["Subscribers"])
def delete_subscriber(
    chat_id: int,
    _:       str = Security(require_api_key),
):
    with get_db() as db:
        sub = db.query(Subscriber).filter_by(chat_id=chat_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        db.delete(sub)
        db.commit()


# ── stats ─────────────────────────────────────────────────────────────────────

@app.get("/stats", response_model=Stats, tags=["Stats"])
def get_stats(_: str = Security(require_api_key)):
    with get_db() as db:
        total_internships  = db.query(func.count(Internship.id)).scalar()
        total_subscribers  = db.query(func.count(Subscriber.chat_id)).scalar()
        active_subscribers = db.query(func.count(Subscriber.chat_id)).filter_by(active=1).scalar()
        latest = (
            db.query(Internship.seen_at)
            .order_by(Internship.seen_at.desc())
            .first()
        )
    return Stats(
        total_internships=total_internships,
        total_subscribers=total_subscribers,
        active_subscribers=active_subscribers,
        latest_seen_at=latest[0] if latest else None,
    )