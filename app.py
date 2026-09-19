app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")


@app.after_request
def add_security_headers(response):
    # Auth/reset/verification URLs can contain one-time tokens. Prevent
    # those query strings from becoming Referer data on subsequent requests.
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)
from usage_billing import register_usage_billing
register_usage_billing(app, db)
from organisation_billing import register_organisation_billing
register_organisation_billing(app, db)
from discovery_billing import register_discovery
register_discovery(app, db)

# Offline chat retries need a server-side idempotency record. The client keeps
# one stable UUID for a queued send; this table lets a retry return the
# already-created message instead of creating a second message when the first
# response was lost during reconnect.
_CHAT_IDEMPOTENCY_SCHEMA_READY = False
_CHAT_IDEMPOTENCY_SCHEMA_LOCK = Lock()


def _ensure_chat_idempotency_schema():
    global _CHAT_IDEMPOTENCY_SCHEMA_READY
    if _CHAT_IDEMPOTENCY_SCHEMA_READY:
        return True