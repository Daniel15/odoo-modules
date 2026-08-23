# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import hashlib
import hmac
import time


class WebhookSignatureError(ValueError):
    """Raised when a Stripe webhook signature cannot be validated."""


def compute_webhook_signature(raw_payload, webhook_secret, event_timestamp):
    """Compute the Stripe v1 HMAC for an exact payload and event timestamp."""
    if isinstance(raw_payload, str):
        raw_payload = raw_payload.encode()
    signed_payload = str(event_timestamp).encode() + b"." + raw_payload
    return hmac.new(
        webhook_secret.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()


def build_webhook_signature_header(raw_payload, webhook_secret, event_timestamp=None):
    """Build a Stripe-Signature header, primarily for webhook integration tests."""
    event_timestamp = int(time.time()) if event_timestamp is None else event_timestamp
    signature = compute_webhook_signature(raw_payload, webhook_secret, event_timestamp)
    return f"t={event_timestamp},v1={signature}"


def verify_webhook_signature(
    raw_payload,
    signature_header,
    webhook_secret,
    timestamp_tolerance,
    current_timestamp=None,
):
    """Validate a Stripe webhook signature against the exact request payload."""
    if not webhook_secret:
        raise WebhookSignatureError("missing webhook secret")
    if isinstance(raw_payload, str):
        raw_payload = raw_payload.encode()

    timestamp = None
    v1_signatures = []
    for entry in (signature_header or "").split(","):
        key, separator, value = entry.strip().partition("=")
        if not separator:
            continue
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1_signatures.append(value)

    if not timestamp:
        raise WebhookSignatureError("missing timestamp")
    # Bound attacker-controlled integer parsing; 20 characters cover int64 timestamps.
    if len(timestamp) > 20:
        raise WebhookSignatureError("invalid timestamp")
    try:
        event_timestamp = int(timestamp)
    except ValueError:
        raise WebhookSignatureError("invalid timestamp") from None

    current_timestamp = (
        int(time.time()) if current_timestamp is None else current_timestamp
    )
    if not (
        current_timestamp - timestamp_tolerance
        <= event_timestamp
        <= current_timestamp + timestamp_tolerance
    ):
        raise WebhookSignatureError("timestamp outside tolerance")
    if not v1_signatures:
        raise WebhookSignatureError("missing v1 signature")

    expected_signature = compute_webhook_signature(
        raw_payload,
        webhook_secret,
        event_timestamp,
    )
    if not any(
        hmac.compare_digest(signature, expected_signature)
        for signature in v1_signatures
    ):
        raise WebhookSignatureError("invalid v1 signature")
    return True
