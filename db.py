import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, Text, Timestamp,
    UniqueConstraint, func, or_
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


# ── models ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Internship(Base):
    __tablename__ = "internships"
    __table_args__ = (UniqueConstraint("company", "role", "apply_link"),)

    id            = Column(Integer, primary_key=True, autoincrement=True)
    company       = Column(Text, nullable=False)
    role          = Column(Text, nullable=False)
    location      = Column(Text)
    apply_link    = Column(Text)
    simplify_link = Column(Text)
    age           = Column(Text)
    seen_at       = Column(Timestamp, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "company":       self.company,
            "role":          self.role,
            "location":      self.location,
            "apply_link":    self.apply_link,
            "simplify_link": self.simplify_link,
            "age":           self.age,
            "seen_at":       self.seen_at,
        }


class Subscriber(Base):
    __tablename__ = "subscribers"

    chat_id        = Column(BigInteger, primary_key=True)
    active         = Column(Integer, nullable=False, default=1)
    keyword_filter = Column(Text)
    joined_at      = Column(Timestamp, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "chat_id":        self.chat_id,
            "active":         self.active,
            "keyword_filter": self.keyword_filter,
            "joined_at":      self.joined_at,
        }


# ── setup ─────────────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(engine)


def get_db() -> Session:
    """Use as a context manager: with get_db() as db: ..."""
    return SessionLocal()


# ── internship helpers ────────────────────────────────────────────────────────

def upsert_internships(rows: list[dict]) -> list[dict]:
    new_entries = []
    with get_db() as db:
        for row in rows:
            exists = db.query(Internship).filter_by(
                company=row["company"],
                role=row["role"],
                apply_link=row["apply_link"],
            ).first()
            if not exists:
                entry = Internship(**row)
                db.add(entry)
                new_entries.append(row)
        db.commit()
    return new_entries


def count_internships() -> int:
    with get_db() as db:
        return db.query(func.count(Internship.id)).scalar()


def get_recent(limit: int = 10) -> list[dict]:
    with get_db() as db:
        rows = (
            db.query(Internship)
            .order_by(Internship.seen_at.desc())
            .limit(limit)
            .all()
        )
    return [r.to_dict() for r in rows]


def search_internships(keyword: str, limit: int = 10) -> list[dict]:
    with get_db() as db:
        rows = (
            db.query(Internship)
            .filter(or_(
                Internship.company.ilike(f"%{keyword}%"),
                Internship.role.ilike(f"%{keyword}%"),
            ))
            .order_by(Internship.seen_at.desc())
            .limit(limit)
            .all()
        )
    return [r.to_dict() for r in rows]


def list_internships(
    search:   str | None = None,
    company:  str | None = None,
    location: str | None = None,
    limit:    int = 50,
    offset:   int = 0,
) -> tuple[list[dict], int]:
    with get_db() as db:
        q = db.query(Internship)

        if search:
            q = q.filter(or_(
                Internship.company.ilike(f"%{search}%"),
                Internship.role.ilike(f"%{search}%"),
            ))
        if company:
            q = q.filter(Internship.company.ilike(f"%{company}%"))
        if location:
            q = q.filter(Internship.location.ilike(f"%{location}%"))

        total = q.count()
        rows  = q.order_by(Internship.seen_at.desc()).offset(offset).limit(limit).all()

    return [r.to_dict() for r in rows], total


# ── subscriber helpers ────────────────────────────────────────────────────────

def subscribe_user(chat_id: int):
    with get_db() as db:
        user = db.query(Subscriber).filter_by(chat_id=chat_id).first()
        if user:
            user.active = 1
        else:
            db.add(Subscriber(chat_id=chat_id, active=1))
        db.commit()


def unsubscribe_user(chat_id: int):
    with get_db() as db:
        user = db.query(Subscriber).filter_by(chat_id=chat_id).first()
        if user:
            user.active = 0
            db.commit()


def set_user_filter(chat_id: int, keyword: str | None):
    with get_db() as db:
        user = db.query(Subscriber).filter_by(chat_id=chat_id).first()
        if user:
            user.keyword_filter = keyword
            db.commit()


def get_subscribers(active_only: bool = True) -> list[dict]:
    with get_db() as db:
        q = db.query(Subscriber)
        if active_only:
            q = q.filter_by(active=1)
        return [r.to_dict() for r in q.all()]


def get_user(chat_id: int) -> dict | None:
    with get_db() as db:
        user = db.query(Subscriber).filter_by(chat_id=chat_id).first()
    return user.to_dict() if user else None