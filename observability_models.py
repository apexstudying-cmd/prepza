"""Privacy-minimized HTTP request observability model."""
from datetime import datetime

from extensions import db


class RequestObservabilityEvent(db.Model):
    """Only slow/error request metadata; never request bodies or user identifiers."""
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(64), nullable=False, index=True)
    method = db.Column(db.String(12), nullable=False)
    route = db.Column(db.String(160), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    duration_ms = db.Column(db.Float, nullable=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    __table_args__ = (
        db.Index(
            "ix_request_observability_status_time",
            "status_code", "occurred_at",
        ),
    )
