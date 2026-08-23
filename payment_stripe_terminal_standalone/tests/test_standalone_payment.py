# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestStripeTerminalStandalonePayment(TransactionCase):
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

    def _event(self, event_id="evt_standalone", payment_intent_id="pi_standalone"):
        return {
            "id": event_id,
            "object": "event",
            "api_version": "2025-01-27.acacia",
            "type": "payment_intent.succeeded",
            "livemode": False,
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "object": "payment_intent",
                    "status": "succeeded",
                    "amount": 1250,
                    "amount_received": 1250,
                    "currency": "usd",
                    "latest_charge": "ch_standalone",
                    "metadata": {"x_terminal_standalone_note": " INV/2026/0042 "},
                }
            },
        }

    def test_webhook_subscription_includes_payment_intent_succeeded(self):
        self.assertEqual(
            self.provider._stripe_terminal_get_webhook_events(),
            [
                "terminal.reader.action_succeeded",
                "terminal.reader.action_failed",
                "payment_intent.succeeded",
            ],
        )

    def test_note_bearing_event_creates_received_audit_only(self):
        transaction_count = self.env["payment.transaction"].search_count([])
        payment_count = self.env["account.payment"].search_count([])
        with (
            patch.object(
                type(self.provider),
                "_stripe_terminal_retrieve_payment_intent",
            ) as retrieve_intent,
            patch.object(
                type(self.provider),
                "_stripe_terminal_retrieve_charge",
            ) as retrieve_charge,
            patch.object(
                type(self.env["stripe.terminal.standalone.payment"]),
                "_process_payment_from_webhook",
            ) as process_payment,
        ):
            handled = self.provider._stripe_terminal_dispatch_webhook_event(
                self._event()
            )

        audit = self.env["stripe.terminal.standalone.payment"].search(
            [("payment_intent_id", "=", "pi_standalone")]
        )
        self.assertTrue(handled)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit.state, "received")
        self.assertEqual(audit.internal_note, "INV/2026/0042")
        self.assertEqual(audit.event_id, "evt_standalone")
        self.assertEqual(audit.charge_id, "ch_standalone")
        self.assertEqual(audit.amount_minor, 1250)
        self.assertEqual(audit.amount, 12.5)
        self.assertEqual(audit.currency_id, self.env.ref("base.USD"))
        self.assertFalse(audit.invoice_id)
        self.assertFalse(audit.payment_transaction_id)
        retrieve_intent.assert_not_called()
        retrieve_charge.assert_not_called()
        process_payment.assert_called_once()
        self.assertEqual(
            self.env["payment.transaction"].search_count([]), transaction_count
        )
        self.assertEqual(self.env["account.payment"].search_count([]), payment_count)

    def test_missing_or_blank_notes_are_ignored(self):
        for index, note in enumerate((None, "", "   ")):
            with self.subTest(note=note):
                event = self._event(
                    event_id=f"evt_no_note_{index}",
                    payment_intent_id=f"pi_no_note_{index}",
                )
                metadata = event["data"]["object"]["metadata"]
                if note is None:
                    metadata.clear()
                else:
                    metadata["x_terminal_standalone_note"] = note
                self.assertTrue(
                    self.provider._stripe_terminal_dispatch_webhook_event(event)
                )
        self.assertFalse(
            self.env["stripe.terminal.standalone.payment"].search(
                [("payment_intent_id", "like", "pi_no_note_")]
            )
        )

    def test_wrong_object_or_status_is_ignored(self):
        wrong_object = self._event("evt_wrong_object", "pi_wrong_object")
        wrong_object["data"]["object"]["object"] = "charge"
        self.assertTrue(
            self.provider._stripe_terminal_dispatch_webhook_event(wrong_object)
        )

        wrong_status = self._event("evt_wrong_status", "pi_wrong_status")
        wrong_status["data"]["object"]["status"] = "processing"
        self.assertTrue(
            self.provider._stripe_terminal_dispatch_webhook_event(wrong_status)
        )
        self.assertFalse(
            self.env["stripe.terminal.standalone.payment"].search(
                [("payment_intent_id", "in", ["pi_wrong_object", "pi_wrong_status"])]
            )
        )

    @mute_logger("odoo.sql_db")
    def test_same_event_duplicate_is_idempotent(self):
        event = self._event()
        with (
            patch(
                "odoo.addons.payment_stripe_terminal_standalone.models.payment_provider."
                "_logger.info"
            ) as log_info,
            patch.object(
                type(self.env["stripe.terminal.standalone.payment"]),
                "_process_payment_from_webhook",
            ) as process_payment,
        ):
            self.provider._stripe_terminal_dispatch_webhook_event(event)
            self.provider._stripe_terminal_dispatch_webhook_event(event)
        self.assertEqual(
            self.env["stripe.terminal.standalone.payment"].search_count(
                [("payment_intent_id", "=", "pi_standalone")]
            ),
            1,
        )
        self.assertEqual(log_info.call_count, 1)
        process_payment.assert_called_once()

    @mute_logger("odoo.sql_db")
    def test_same_payment_intent_in_different_event_is_idempotent(self):
        with patch.object(
            type(self.env["stripe.terminal.standalone.payment"]),
            "_process_payment_from_webhook",
        ):
            self.provider._stripe_terminal_dispatch_webhook_event(self._event())
            self.provider._stripe_terminal_dispatch_webhook_event(
                self._event(event_id="evt_standalone_retry")
            )
        audit = self.env["stripe.terminal.standalone.payment"].search(
            [("payment_intent_id", "=", "pi_standalone")]
        )
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit.event_id, "evt_standalone")

    def test_expanded_charge_details_are_stored_without_retrieval(self):
        event = self._event("evt_expanded", "pi_expanded")
        event["data"]["object"]["latest_charge"] = {
            "id": "ch_expanded",
            "payment_method_details": {
                "type": "card_present",
                "card_present": {
                    "reader": "tmr_simulated",
                    "location": "tml_test",
                },
            },
        }
        with (
            patch.object(
                type(self.provider), "_stripe_terminal_retrieve_charge"
            ) as retrieve_charge,
            patch.object(
                type(self.env["stripe.terminal.standalone.payment"]),
                "_process_payment_from_webhook",
            ),
        ):
            self.provider._stripe_terminal_dispatch_webhook_event(event)
        audit = self.env["stripe.terminal.standalone.payment"].search(
            [("payment_intent_id", "=", "pi_expanded")]
        )
        self.assertEqual(audit.charge_id, "ch_expanded")
        self.assertEqual(audit.reader_id, "tmr_simulated")
        self.assertEqual(audit.location_id, "tml_test")
        retrieve_charge.assert_not_called()
