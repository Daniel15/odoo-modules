# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json
from unittest.mock import patch

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.payment_stripe_terminal_base.webhook_signature import (
    build_webhook_signature_header,
)


@tagged("post_install", "-at_install")
class TestStripeTerminalStandaloneWebhookController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return
        cls.route_token = "standalone_controller_route"
        cls.webhook_secret = "whsec_standalone_controller"
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

    def _payload(self, event_id, payment_intent_id, note=True):
        metadata = {}
        if note:
            metadata["x_terminal_standalone_note"] = "INV/2026/0042"
        return json.dumps(
            {
                "id": event_id,
                "type": "payment_intent.succeeded",
                "livemode": False,
                "data": {
                    "object": {
                        "id": payment_intent_id,
                        "object": "payment_intent",
                        "status": "succeeded",
                        "amount_received": 1250,
                        "currency": "usd",
                        "metadata": metadata,
                    }
                },
            }
        ).encode()

    def _post(self, payload, signature=None):
        return self.url_open(
            f"/payment/stripe/terminal/webhook/{self.route_token}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": signature or "invalid",
            },
            allow_redirects=False,
        )

    def test_verified_note_bearing_event_is_received(self):
        payload = self._payload("evt_http_standalone", "pi_http_standalone")
        with patch.object(
            type(self.env["stripe.terminal.standalone.payment"]),
            "_process_payment_from_webhook",
        ):
            response = self._post(
                payload,
                build_webhook_signature_header(payload, self.webhook_secret),
            )
        self.assertEqual(response.status_code, 200)
        audit = self.env["stripe.terminal.standalone.payment"].search(
            [("payment_intent_id", "=", "pi_http_standalone")]
        )
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit.state, "received")

    def test_verified_no_note_event_is_ignored(self):
        payload = self._payload("evt_http_no_note", "pi_http_no_note", note=False)
        response = self._post(
            payload,
            build_webhook_signature_header(payload, self.webhook_secret),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            self.env["stripe.terminal.standalone.payment"].search(
                [("payment_intent_id", "=", "pi_http_no_note")]
            )
        )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_invalid_signature_creates_no_audit(self):
        payload = self._payload("evt_http_invalid", "pi_http_invalid")
        response = self._post(payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.env["stripe.terminal.standalone.payment"].search(
                [("payment_intent_id", "=", "pi_http_invalid")]
            )
        )
