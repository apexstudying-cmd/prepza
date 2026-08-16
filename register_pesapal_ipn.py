"""
One-time setup script: registers Prepza's IPN (webhook) URL with Pesapal
and prints the notification_id you need to set as PESAPAL_IPN_ID.

Run this ONCE per environment (once for sandbox, again later when you go
to production - the IDs are different because the URLs/keys are different).

Requires PESAPAL_CONSUMER_KEY, PESAPAL_CONSUMER_SECRET, PESAPAL_ENV, and
BASE_URL to already be set - reads them the same way app.py does, via a
local .env file.

Usage:
    cd ~/desktop/prepza
    python register_pesapal_ipn.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

PESAPAL_SANDBOX_BASE = "https://cybqa.pesapal.com/pesapalv3"
PESAPAL_PRODUCTION_BASE = "https://pay.pesapal.com/v3"


def base_url():
    env = os.environ.get("PESAPAL_ENV", "sandbox").strip().lower()
    return PESAPAL_PRODUCTION_BASE if env == "production" else PESAPAL_SANDBOX_BASE


def get_token():
    response = requests.post(
        f"{base_url()}/api/Auth/RequestToken",
        json={
            "consumer_key": os.environ.get("PESAPAL_CONSUMER_KEY"),
            "consumer_secret": os.environ.get("PESAPAL_CONSUMER_SECRET"),
        },
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("token")
    if not token:
        raise SystemExit(f"Auth failed: {data.get('message') or data}")
    return token


def main():
    app_base_url = os.environ.get("BASE_URL", "https://prepza-sf60.onrender.com").rstrip("/")
    ipn_url = f"{app_base_url}/payment/pesapal/ipn"

    print(f"Environment : {os.environ.get('PESAPAL_ENV', 'sandbox')}")
    print(f"Registering : {ipn_url}")

    token = get_token()
    response = requests.post(
        f"{base_url()}/api/URLSetup/RegisterIPN",
        json={"url": ipn_url, "ipn_notification_type": "POST"},
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    notification_id = data.get("ipn_id")
    if not notification_id:
        raise SystemExit(f"Registration failed: {data}")

    print()
    print("Registered successfully.")
    print(f"PESAPAL_IPN_ID = {notification_id}")
    print()
    print("Set this as an env var named PESAPAL_IPN_ID on Render.")


if __name__ == "__main__":
    main()
