# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import hashlib
import hmac
import json
import time

from werkzeug.exceptions import Forbidden

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestLegacyStripeTerminalWebhookController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return
        cls.webhook_secret = "whsec_legacy_controller_test"
        cls.provider.write(
            {
                "stripe_terminal_legacy_webhook_secret": cls.webhook_secret,
                "stripe_terminal_webhook_endpoint_id": "we_current",
                "stripe_terminal_webhook_secret": "whsec_current_controller_test",
            }
        )
        cls.env.cr.execute(
            """
            UPDATE payment_provider
               SET state = 'test',
                   stripe_publishable_key = 'pk_test_fake',
                   stripe_secret_key = 'sk_test_fake'
             WHERE id = %s
            """,
            [cls.provider.id],
        )
        cls.provider.invalidate_recordset(
            ["state", "stripe_publishable_key", "stripe_secret_key"]
        )
        cls.pos_manager = new_test_user(
            cls.env,
            login="terminal_pos_manager",
            groups="point_of_sale.group_pos_manager",
        )

    def setUp(self):
        super().setUp()
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _signature_header(self, payload):
        timestamp = int(time.time())
        signature = hmac.new(
            self.webhook_secret.encode(),
            str(timestamp).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    def _post_webhook(self, payload, signature_header=None):
        return self.url_open(
            "/pos_stripe_server_driven/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": signature_header or "invalid",
            },
            allow_redirects=False,
        )

    @mute_logger(
        "odoo.addons.payment_stripe_terminal_base.models.payment_provider",
        "odoo.addons.pos_stripe_server_driven.models.payment_provider",
    )
    def test_signature_is_checked_before_json_parsing(self):
        response = self._post_webhook(b"not-json")
        self.assertEqual(response.status_code, 403)

    def test_legacy_secret_is_accepted_during_cutover(self):
        payload = json.dumps(
            {"id": "evt_legacy", "type": "unhandled.event", "livemode": False}
        ).encode()
        response = self._post_webhook(payload, self._signature_header(payload))
        self.assertEqual(response.status_code, 200)

    def test_retired_legacy_secret_is_rejected(self):
        result = self.provider.action_stripe_terminal_retire_legacy_webhook()
        self.assertFalse(self.provider.stripe_terminal_legacy_webhook_secret)
        self.assertEqual(result["params"]["type"], "info")

        payload = b'{"id":"evt_legacy"}'
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_legacy_webhook_signature(
                payload, self._signature_header(payload)
            )

    def test_signed_non_object_json_is_rejected(self):
        payload = b"[]"
        response = self._post_webhook(payload, self._signature_header(payload))
        self.assertEqual(response.status_code, 400)

    def test_pos_manager_cannot_configure_terminal_webhooks(self):
        provider = self.provider.with_user(self.pos_manager)
        with self.assertRaisesRegex(AccessError, "Settings administrators"):
            provider.action_stripe_sd_create_webhook()
        with self.assertRaisesRegex(AccessError, "Settings administrators"):
            provider.action_stripe_terminal_retire_legacy_webhook()
