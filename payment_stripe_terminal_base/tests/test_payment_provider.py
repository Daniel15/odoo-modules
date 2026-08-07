# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import hashlib
import hmac
import time
from unittest.mock import patch

from werkzeug.exceptions import Forbidden

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class StripeTerminalProviderCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )

    def setUp(self):
        super().setUp()
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _mock_stripe_request(self, return_value=None, side_effect=None):
        return patch.object(
            type(self.provider),
            "_stripe_make_request",
            return_value=return_value,
            side_effect=side_effect,
        )


class TestStripeTerminalWebhookConfiguration(StripeTerminalProviderCase):
    def setUp(self):
        super().setUp()
        self.provider.write(
            {
                "stripe_terminal_webhook_endpoint_id": False,
                "stripe_terminal_webhook_route_token": False,
                "stripe_terminal_webhook_secret": False,
            }
        )

    def test_create_webhook(self):
        webhook = {
            "id": "we_terminal_123",
            "secret": "whsec_terminal_123",
        }
        with (
            self._mock_stripe_request(return_value=webhook) as mock_request,
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
        ):
            result = self.provider.action_stripe_terminal_create_webhook()

        mock_request.assert_called_once()
        (endpoint,) = mock_request.call_args.args
        payload = mock_request.call_args.kwargs["payload"]
        self.assertEqual(endpoint, "webhook_endpoints")
        self.assertIn("/payment/stripe/terminal/webhook/", payload["url"])
        self.assertEqual(
            payload["enabled_events[]"],
            [
                "terminal.reader.action_succeeded",
                "terminal.reader.action_failed",
            ],
        )
        self.assertTrue(payload["api_version"])
        self.assertIn(
            self.provider.stripe_terminal_webhook_route_token,
            mock_request.call_args.kwargs["idempotency_key"],
        )
        self.assertEqual(
            self.provider.stripe_terminal_webhook_endpoint_id, "we_terminal_123"
        )
        self.assertEqual(
            self.provider.stripe_terminal_webhook_secret, "whsec_terminal_123"
        )
        self.assertTrue(self.provider.stripe_terminal_webhook_route_token)
        self.assertEqual(result["params"]["type"], "info")

    def test_create_webhook_existing_endpoint_is_ignored(self):
        self.provider.stripe_terminal_webhook_endpoint_id = "we_existing"
        with self._mock_stripe_request() as mock_request:
            result = self.provider.action_stripe_terminal_create_webhook()
        mock_request.assert_not_called()
        self.assertEqual(result["params"]["type"], "warning")

    def test_create_webhook_without_api_key_is_rejected(self):
        with patch.object(
            type(self.provider),
            "stripe_secret_key",
            new_callable=lambda: property(lambda _self: ""),
        ):
            result = self.provider.action_stripe_terminal_create_webhook()
        self.assertEqual(result["params"]["type"], "danger")

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_create_webhook_api_error_is_reported(self):
        with (
            self._mock_stripe_request(side_effect=ValidationError("Stripe failed")),
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
            self.assertRaisesRegex(ValidationError, "Stripe failed"),
        ):
            self.provider.action_stripe_terminal_create_webhook()

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_create_webhook_requires_id_and_secret(self):
        with (
            self._mock_stripe_request(return_value={"id": "we_incomplete"}),
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
            self.assertRaisesRegex(ValidationError, "invalid response"),
        ):
            self.provider.action_stripe_terminal_create_webhook()
        self.assertFalse(self.provider.stripe_terminal_webhook_endpoint_id)

    def test_webhook_url_uses_provider_route_token(self):
        self.provider.stripe_terminal_webhook_route_token = "route_existing"
        self.assertTrue(
            self.provider.stripe_terminal_webhook_url.endswith(
                "/payment/stripe/terminal/webhook/route_existing"
            )
        )

    def test_update_webhook(self):
        self.provider.write(
            {
                "stripe_terminal_webhook_endpoint_id": "we_existing",
                "stripe_terminal_webhook_route_token": "route_existing",
                "stripe_terminal_webhook_secret": "whsec_existing",
            }
        )
        with (
            self._mock_stripe_request(return_value={"id": "we_existing"}) as request,
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
        ):
            result = self.provider.action_stripe_terminal_update_webhook()

        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "webhook_endpoints/we_existing")
        self.assertIn("route_existing", request.call_args.kwargs["payload"]["url"])
        self.assertNotIn("api_version", request.call_args.kwargs["payload"])
        self.assertEqual(result["params"]["type"], "info")


class TestStripeTerminalWebhookSignature(StripeTerminalProviderCase):
    def setUp(self):
        super().setUp()
        self.provider.stripe_terminal_webhook_secret = "whsec_test_secret"
        self.payload = b'{"id":"evt_test"}'

    def _signature(self, timestamp, secret="whsec_test_secret"):
        return hmac.new(
            secret.encode(),
            str(timestamp).encode() + b"." + self.payload,
            hashlib.sha256,
        ).hexdigest()

    def test_valid_signature(self):
        timestamp = int(time.time())
        result = self.provider._stripe_terminal_verify_webhook_signature(
            self.payload, f"t={timestamp},v1={self._signature(timestamp)}"
        )
        self.assertTrue(result)

    def test_any_valid_v1_signature_is_accepted(self):
        timestamp = int(time.time())
        result = self.provider._stripe_terminal_verify_webhook_signature(
            self.payload,
            f"t={timestamp},v1=invalid,v1={self._signature(timestamp)}",
        )
        self.assertTrue(result)

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_invalid_signature_is_rejected(self):
        timestamp = int(time.time())
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_webhook_signature(
                self.payload, f"t={timestamp},v1=invalid"
            )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_missing_signature_is_rejected(self):
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_webhook_signature(self.payload, "")

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_non_integer_timestamp_is_rejected(self):
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_webhook_signature(
                self.payload, "t=not-an-integer,v1=invalid"
            )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_old_timestamp_is_rejected(self):
        timestamp = int(time.time()) - 3600
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_webhook_signature(
                self.payload, f"t={timestamp},v1={self._signature(timestamp)}"
            )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_future_timestamp_is_rejected(self):
        timestamp = int(time.time()) + 3600
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_webhook_signature(
                self.payload, f"t={timestamp},v1={self._signature(timestamp)}"
            )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_oversized_timestamp_is_rejected(self):
        timestamp = 10**1000
        with self.assertRaises(Forbidden):
            self.provider._stripe_terminal_verify_webhook_signature(
                self.payload, f"t={timestamp},v1=invalid"
            )


class TestStripeTerminalHelpers(StripeTerminalProviderCase):
    def test_retrieve_helpers(self):
        with self._mock_stripe_request(return_value={}) as request:
            self.provider._stripe_terminal_retrieve_payment_intent("pi_test")
            self.provider._stripe_terminal_retrieve_charge("ch_test")
            self.provider._stripe_terminal_retrieve_refund("re_test")
        self.assertEqual(
            [call.args for call in request.call_args_list],
            [
                ("payment_intents/pi_test",),
                ("charges/ch_test",),
                ("refunds/re_test",),
            ],
        )
        self.assertTrue(
            all(call.kwargs["method"] == "GET" for call in request.call_args_list)
        )

    def test_extract_expanded_card_present_details(self):
        details = self.provider._stripe_terminal_extract_card_present_details(
            {
                "latest_charge": {
                    "id": "ch_test",
                    "payment_method_details": {
                        "type": "card_present",
                        "card_present": {
                            "brand": "visa",
                            "reader": "tmr_test",
                            "location": "tml_test",
                        },
                    },
                }
            }
        )
        self.assertEqual(
            details,
            {
                "charge_id": "ch_test",
                "payment_method_type": "card_present",
                "card_brand": "visa",
                "reader_id": "tmr_test",
                "location_id": "tml_test",
            },
        )

    def test_extract_retrieved_card_present_details(self):
        charge = {
            "id": "ch_test",
            "payment_method_details": {
                "type": "card_present",
                "card_present": {"brand": "mastercard"},
            },
        }
        with self._mock_stripe_request(return_value=charge) as request:
            details = self.provider._stripe_terminal_extract_card_present_details(
                {"latest_charge": "ch_test"}
            )
        request.assert_called_once_with("charges/ch_test", method="GET")
        self.assertEqual(details["charge_id"], "ch_test")
        self.assertEqual(details["card_brand"], "mastercard")

    def test_currency_conversion(self):
        currency = self.env.ref("base.USD")
        minor = self.provider._stripe_terminal_to_minor_currency_units(12.34, currency)
        major = self.provider._stripe_terminal_to_major_currency_units(minor, currency)
        self.assertEqual(minor, 1234)
        self.assertEqual(major, 12.34)

    def test_zero_decimal_currency_conversion(self):
        currency = self.env.ref("base.JPY")
        minor = self.provider._stripe_terminal_to_minor_currency_units(1234, currency)
        major = self.provider._stripe_terminal_to_major_currency_units(minor, currency)
        self.assertEqual(minor, 1234)
        self.assertEqual(major, 1234)

    def test_stripe_specific_currency_conversion(self):
        currency = self.env.ref("base.ISK")
        minor = self.provider._stripe_terminal_to_minor_currency_units(12.34, currency)
        major = self.provider._stripe_terminal_to_major_currency_units(minor, currency)
        self.assertEqual(minor, 1234)
        self.assertEqual(major, 12.34)

    def test_charge_retrieval_error_returns_empty_details(self):
        with self._mock_stripe_request(return_value={"error": {"message": "failed"}}):
            details = self.provider._stripe_terminal_extract_card_present_details(
                {"latest_charge": "ch_failed"}
            )
        self.assertEqual(details["charge_id"], "ch_failed")
        self.assertFalse(details["card_brand"])

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_connect_event_is_ignored(self):
        self.assertFalse(
            self.provider._stripe_terminal_validate_webhook_event(
                {"id": "evt_test", "account": "acct_connected"}
            )
        )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_disabled_provider_is_ignored(self):
        self.env.cr.execute(
            "UPDATE payment_provider SET state = 'disabled' WHERE id = %s",
            [self.provider.id],
        )
        self.provider.invalidate_recordset(["state"])
        self.assertFalse(
            self.provider._stripe_terminal_validate_webhook_event(
                {"id": "evt_test", "livemode": False}
            )
        )

    @mute_logger("odoo.addons.payment_stripe_terminal_base.models.payment_provider")
    def test_provider_mode_mismatch_is_ignored(self):
        self.env.cr.execute(
            "UPDATE payment_provider SET state = 'test' WHERE id = %s",
            [self.provider.id],
        )
        self.provider.invalidate_recordset(["state"])
        self.assertFalse(
            self.provider._stripe_terminal_validate_webhook_event(
                {"id": "evt_test", "livemode": True}
            )
        )
