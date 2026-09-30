"""Pure B2B prepaid campaign accounting helpers.

Kept free of Flask, SQLAlchemy, HTTP, and provider dependencies so financial
invariants can be unit-tested in lightweight CI jobs and reused by a hosted
deployment without pulling web-stack concerns into accounting logic.
"""


def available_prepaid_campaign_balance(funded_amount_minor, ledger_net_minor):
    """Return unused campaign value without double-counting funding.

    The campaign ledger already contains the original funding credit plus
    subsequent delivery/refund entries, so its net is the current prepaid
    balance. The recorded funded amount is a safety ceiling.
    """
    funded = max(0, int(funded_amount_minor or 0))
    ledger_net = max(0, int(ledger_net_minor or 0))
    return min(funded, ledger_net)
