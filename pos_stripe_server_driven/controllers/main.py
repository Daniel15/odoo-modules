# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from werkzeug.exceptions import BadRequest, Forbidden

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

WEBHOOK_AGE_TOLERANCE = 10 * 60  # seconds


class PosStripeServerDrivenController(http.Controller):
    _webhook_url = "/pos_stripe_server_driven/webhook"

    @http.route(
        _webhook_url,
        type="http",
        methods=["POST"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def stripe_terminal_webhook(self):
        try:
            event = request.get_json_data()
        except Exception:
            raise BadRequest("Invalid JSON payload") from None

        event_type = event.get("type")
        if event_type not in (
            "terminal.reader.action_succeeded",
            "terminal.reader.action_failed",
        ):
            return request.make_response("", status=200)

        stripe_object = event.get("data", {}).get("object", {})
        reader_id = stripe_object.get("id")

        if not reader_id:
            _logger.warning("Received terminal webhook without reader ID")
            return request.make_response("", status=200)

        # Find the payment method associated with this reader
        payment_method_sudo = (
            request.env["pos.payment.method"]
            .sudo()
            .search([("stripe_reader_id", "=", reader_id)], limit=1)
        )

        if not payment_method_sudo:
            _logger.warning(
                "Received terminal webhook for unknown reader: %s", reader_id
            )
            return request.make_response("", status=200)

        # Verify webhook signature
        self._verify_webhook_signature(payment_method_sudo)

        _logger.info(
            "Terminal notification received from Stripe: type=%s reader=%s",
            event_type,
            reader_id,
        )

        # Extract payment intent info
        action = stripe_object.get("action", {})
        payment_intent_id = action.get("process_payment_intent", {}).get(
            "payment_intent"
        )

        if not payment_intent_id:
            _logger.warning("Received terminal webhook without payment_intent_id")
            return request.make_response("", status=200)

        # Determine status
        if event_type == "terminal.reader.action_succeeded":
            status = "succeeded"
            failure_message = ""
        else:
            status = "failed"
            failure_message = (
                action.get("failure_message", "")
                or stripe_object.get("last_error", {}).get("message", "")
                or "Payment failed"
            )

        # Find POS configs and send bus notification
        notification_data = {
            "payment_intent_id": payment_intent_id,
            "status": status,
            "failure_message": failure_message,
        }
        for pos_config in self._find_pos_configs(payment_method_sudo):
            pos_config._notify("STRIPE_SD_PAYMENT_STATUS", notification_data)

        return request.make_response("", status=200)

    def _find_pos_configs(self, payment_method_sudo):
        """Find all POS configs with open sessions using this payment method."""
        pos_sessions = (
            request.env["pos.session"]
            .sudo()
            .search(
                [
                    ("state", "=", "opened"),
                    (
                        "config_id.payment_method_ids",
                        "in",
                        payment_method_sudo.ids,
                    ),
                ],
            )
        )
        return pos_sessions.mapped("config_id")

    def _verify_webhook_signature(self, payment_method_sudo):
        """Verify the Stripe webhook signature using HMAC-SHA256."""
        webhook_secret = payment_method_sudo.stripe_terminal_webhook_secret
        if not webhook_secret:
            _logger.warning("Ignored webhook event due to undefined webhook secret")
            raise Forbidden()

        notification_payload = request.httprequest.data.decode("utf-8")
        signature_header = request.httprequest.headers.get("Stripe-Signature", "")
        signature_entries = signature_header.split(",")
        timestamp = None
        v1_signatures = []
        for entry in signature_entries:
            parts = entry.strip().split("=", 1)
            if len(parts) == 2:
                if parts[0] == "t":
                    timestamp = parts[1]
                elif parts[0] == "v1":
                    v1_signatures.append(parts[1])

        # Retrieve the timestamp
        if not timestamp:
            _logger.warning("Received notification with missing timestamp")
            raise Forbidden()
        try:
            event_timestamp = int(timestamp)
        except ValueError:
            _logger.warning(
                "Received notification with invalid timestamp: %s", timestamp
            )
            raise Forbidden() from None

        # Check timestamp age (reject both outdated and far-future timestamps)
        diff = datetime.now(timezone.utc).timestamp() - event_timestamp
        if abs(diff) > WEBHOOK_AGE_TOLERANCE:
            _logger.warning(
                "Received notification with timestamp outside tolerance: %s",
                event_timestamp,
            )
            raise Forbidden()

        # Retrieve the received signatures
        if not v1_signatures:
            _logger.warning("Received notification with missing signature")
            raise Forbidden()

        # Compare signatures - accept if any provided v1 signature matches
        signed_payload = f"{event_timestamp}.{notification_payload}"
        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not any(
            hmac.compare_digest(sig, expected_signature) for sig in v1_signatures
        ):
            _logger.warning("Received notification with invalid signature")
            raise Forbidden()
