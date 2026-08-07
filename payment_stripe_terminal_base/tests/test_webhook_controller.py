# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import hashlib
import hmac
import json
import time

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestStripeTerminalWebhookController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return
        cls.route_token = "terminal_test_route"
        cls.webhook_secret = "whsec_controller_test"
        cls.env.cr.execute(
            """
            UPDATE payment_provider
               SET state = 'test',
                   stripe_terminal_webhook_route_token = %s,
                   stripe_terminal_webhook_secret = %s
             WHERE id = %s
            """,
            [cls.route_token, cls.webhook_secret, cls.provider.id],
        )
        cls.provider.invalidate_recordset(
            [
                "state",
                "stripe_terminal_webhook_route_token",
                "stripe_terminal_webhook_secret",
            ]
        )

    def setUp(self):
        super().setUp()
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _signature_header(self, payload, secret=None):
        timestamp = int(time.time())
        signature = hmac.new(
            (secret or self.webhook_secret).encode(),
            str(timestamp).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    def _post_webhook(self, payload, signature_header=None, route_token=None):
        return self.url_open(
            "/payment/stripe/terminal/webhook/" + (route_token or self.route_token),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": signature_header or "invalid",
            },
            allow_redirects=False,
        )

    def test_valid_signed_event_is_acknowledged(self):
        payload = json.dumps(
            {
                "id": "evt_controller",
                "type": "unhandled.event",
                "livemode": False,
            }
        ).encode()
        response = self._post_webhook(payload, self._signature_header(payload))
        self.assertEqual(response.status_code, 200)

    def test_signature_is_checked_before_json_parsing(self):
        response = self._post_webhook(b"not-json")
        self.assertEqual(response.status_code, 403)

    def test_signed_invalid_json_is_rejected(self):
        payload = b"not-json"
        response = self._post_webhook(payload, self._signature_header(payload))
        self.assertEqual(response.status_code, 400)

    def test_unknown_provider_route_is_rejected(self):
        payload = b"{}"
        response = self._post_webhook(
            payload,
            self._signature_header(payload),
            route_token="unknown_terminal_route",
        )
        self.assertEqual(response.status_code, 403)
