# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import patch

from odoo.tools import mute_logger

from odoo.addons.account_payment.tests.common import AccountPaymentCommon


class StandaloneProcessingCommon(AccountPaymentCommon):
    @classmethod
    def setUpClass(cls):
        with mute_logger("odoo.addons.account.models.chart_template"):
            super().setUpClass()
        cls.provider = cls._prepare_provider(
            "stripe",
            update_values={
                "stripe_publishable_key": "pk_test_standalone",
                "stripe_secret_key": "sk_test_standalone",
            },
        )
        if not cls.provider:
            return

        cls.provider.journal_id = cls.company_data["default_journal_bank"]
        cls.payment_method_line = cls.env["account.payment.method.line"].search(
            [("payment_provider_id", "=", cls.provider.id)]
        )
        cls.payment_method_line.payment_account_id = (
            cls.inbound_payment_method_line.payment_account_id
        )

    def setUp(self):
        super().setUp()
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        self.invoice = self._create_invoice_one_line(
            price_unit=12.5,
            tax_ids=self.env["account.tax"],
            post=True,
        )
        self.audit = self._receive_audit(self.invoice.name)

    def _receive_audit(
        self,
        note,
        event_id="evt_processing",
        payment_intent_id="pi_processing",
    ):
        event = {
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
                    "amount_received": 1250,
                    "currency": "usd",
                    "latest_charge": "ch_processing",
                    "metadata": {"x_terminal_standalone_note": note},
                }
            },
        }
        payment_intent = event["data"]["object"]
        audit, _created = (
            self.env["stripe.terminal.standalone.payment"]
            .sudo()
            ._receive_event(
                self.provider,
                event,
                payment_intent,
                note.strip(),
            )
        )
        return audit

    def _payment_intent(self, **values):
        return {
            "id": self.audit.payment_intent_id,
            "object": "payment_intent",
            "status": "succeeded",
            "livemode": False,
            "amount_received": 1250,
            "amount_details": {"tip": {}},
            "capture_method": "automatic",
            "currency": "usd",
            "latest_charge": "ch_processing",
            "payment_method": "pm_processing",
            "metadata": {
                "x_terminal_standalone_note": self.audit.internal_note,
            },
            **values,
        }

    def _charge(self, **values):
        return {
            "id": "ch_processing",
            "object": "charge",
            "status": "succeeded",
            "paid": True,
            "captured": True,
            "livemode": False,
            "amount_captured": 1250,
            "currency": "usd",
            "payment_intent": self.audit.payment_intent_id,
            "payment_method_details": {
                "type": "card_present",
                "card_present": {
                    "reader": "tmr_processing",
                    "location": "tml_processing",
                },
            },
            **values,
        }

    def _process_payment(self, payment_intent=None, charge=None):
        with (
            patch.object(
                type(self.provider),
                "_stripe_terminal_retrieve_payment_intent",
                return_value=payment_intent or self._payment_intent(),
            ),
            patch.object(
                type(self.provider),
                "_stripe_terminal_retrieve_charge",
                return_value=charge or self._charge(),
            ),
        ):
            self.audit._process_payment_from_webhook()
