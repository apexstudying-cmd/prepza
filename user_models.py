"""Core user identity and account ORM model."""
from extensions import db
from academic_models import University, Program


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    display_name = db.Column(db.String(50), nullable=True)
    avatar_storage_path = db.Column(db.String(500), nullable=True)
    bio = db.Column(db.String(160), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    # Private field only - never exposed on public/other-user profile
    # endpoints, not searchable. See patch_add_phone_number.py.
    email_verified = db.Column(db.Boolean, default=False)
    profile_visibility = db.Column(db.String(10), nullable=False, default="public")
    # public | private
    who_can_message = db.Column(db.String(10), nullable=False, default="everyone")
    # everyone | followers
    who_can_follow = db.Column(db.String(20), nullable=False, default="everyone")
    read_receipts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # everyone | approval_required
    verification_token = db.Column(db.String(64), nullable=True)
    reset_token = db.Column(db.String(64), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)
    requested_program_name = db.Column(db.String(150), nullable=True)


    created_at = db.Column(db.DateTime, nullable=True)
    signup_source = db.Column(db.String(100), nullable=True)
    is_suspended = db.Column(db.Boolean, nullable=False, default=False)
    last_active_at = db.Column(db.DateTime, nullable=True)
    # Bumped whenever this user's password changes (or an admin needs to
    # force-logout them). Every request compares this to the number
    # stamped in the session cookie at login time - a mismatch means the
    # cookie is stale and gets cleared. See enforce_session_version().
    session_version = db.Column(db.Integer, nullable=False, default=0)
    # Updated (throttled, see track_last_active()) on any authenticated
    # request - login, browsing, chatting, anything - not just specific
    # study actions. That's a different, broader signal than
    # StudyActivityLog, which only covers document/quiz/flashcard study.
