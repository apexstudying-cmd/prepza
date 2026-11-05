"""Academic catalog SQLAlchemy models.

These models use the shared extension instance from extensions.py. app.py
imports and re-exports the classes at their original declaration position so
existing runtime modules, seed scripts, and QA tools can keep importing them
from app while model ownership moves to a domain module.
"""

from datetime import datetime

from extensions import db


class University(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    short_code = db.Column(db.String(20), nullable=False, unique=True)
    country = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    degree_level = db.Column(db.String(50), nullable=True)
    discipline_category = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
