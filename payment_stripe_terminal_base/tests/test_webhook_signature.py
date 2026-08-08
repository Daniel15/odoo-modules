# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from textwrap import dedent

from odoo.tests.common import BaseCase

from ..webhook_signature import WebhookSignatureError, verify_webhook_signature


class TestWebhookSignature(BaseCase):
    # Fixed test vector from Stripe's official .NET SDK at commit 6045930:
    # https://github.com/stripe/stripe-dotnet/tree/6045930/src/StripeTests
    # src/StripeTests/Resources/event_test_signature.json and
    # src/StripeTests/Services/Events/EventUtilityTest.cs.
    secret = "webhook_secret"
    payload = dedent("""\
        {
          "id": "evt_123",
          "object": "event",
          "account": "acct_123",
          "api_version": "2017-05-25",
          "created": 1533204620,
          "data": {
            "object": {
              "id": "cus_123",
              "object": "customer",
              "created": 123456789,
              "email": "test@stripe.com",
              "livemode": false,
              "metadata": {}
            }
          },
          "livemode": false,
          "pending_webhooks": 1,
          "request": {
            "id": "req_123",
            "idempotency_key": "idempotency-key-123"
          },
          "type": "customer.created"
        }
        """).encode()
    signature_header = (
        "t=1533204620,"
        "v1=2220f87ef101a04665f11cdf770523143f875572008577fa0f20882ddb9cc3c7,"
        "v0=63f3a72374a733066c4be69ed7f8e5ac85c22c9f0a6a612ab9a025a9e4ee7eef"
    )
    timestamp = 1_533_204_620
    tolerance = 300

    def test_valid_signature(self):
        self.assertTrue(
            verify_webhook_signature(
                self.payload,
                self.signature_header,
                self.secret,
                self.tolerance,
                current_timestamp=self.timestamp + 100,
            )
        )

    def test_any_matching_v1_signature_is_accepted(self):
        self.assertTrue(
            verify_webhook_signature(
                self.payload,
                f"{self.signature_header},v1=invalid",
                self.secret,
                self.tolerance,
                current_timestamp=self.timestamp,
            )
        )

    def test_invalid_signature_is_rejected(self):
        with self.assertRaisesRegex(WebhookSignatureError, "invalid v1 signature"):
            verify_webhook_signature(
                self.payload,
                "t=1533204620,v1=invalid",
                self.secret,
                self.tolerance,
                current_timestamp=self.timestamp,
            )

    def test_timestamp_outside_tolerance_is_rejected(self):
        with self.assertRaisesRegex(
            WebhookSignatureError, "timestamp outside tolerance"
        ):
            verify_webhook_signature(
                self.payload,
                self.signature_header,
                self.secret,
                self.tolerance,
                current_timestamp=self.timestamp + self.tolerance + 1,
            )

    def test_oversized_timestamp_is_rejected_before_parsing(self):
        with self.assertRaisesRegex(WebhookSignatureError, "invalid timestamp"):
            verify_webhook_signature(
                self.payload,
                f"t={'1' * 21},v1=invalid",
                self.secret,
                self.tolerance,
                current_timestamp=self.timestamp,
            )
