# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import patch

from odoo.tools import mute_logger

from .common import StandaloneProcessingCommon

_STANDALONE_PAYMENT_LOGGER = (
    "odoo.addons.payment_stripe_terminal_standalone.models."
    "stripe_terminal_standalone_payment"
)


class TestStripeTerminalStandaloneProcessing(StandaloneProcessingCommon):
    def test_success_uses_standard_transaction_and_payment(self):
        self._process_payment()

        self.audit.invalidate_recordset()
        self.invoice.invalidate_recordset(["amount_residual", "payment_state"])
        tx = self.audit.payment_transaction_id
        payment = tx.payment_id
        self.assertEqual(self.audit.state, "processed")
        self.assertEqual(self.audit.invoice_id, self.invoice)
        self.assertEqual(self.audit.charge_id, "ch_processing")
        self.assertEqual(self.audit.reader_id, "tmr_processing")
        self.assertEqual(self.audit.location_id, "tml_processing")
        self.assertEqual(tx.reference, "STRIPE-STANDALONE-pi_processing")
        self.assertEqual(tx.provider_reference, "pi_processing")
        self.assertEqual(tx.state, "done")
        self.assertTrue(tx.is_post_processed)
        self.assertEqual(tx.invoice_ids, self.invoice)
        self.assertEqual(payment.journal_id, self.payment_method_line.journal_id)
        self.assertEqual(payment.payment_method_line_id, self.payment_method_line)
        self.assertEqual(
            payment.outstanding_account_id,
            self.payment_method_line.payment_account_id,
        )
        self.assertEqual(payment.move_id.state, "posted")
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertTrue(self.invoice.currency_id.is_zero(self.invoice.amount_residual))
        self.assertEqual(
            self.invoice.payment_state,
            self.invoice._get_invoice_in_payment_state(),
        )

    def test_success_matches_custom_invoice_number(self):
        self.invoice = self._create_invoice_one_line(
            price_unit=12.5,
            tax_ids=self.env["account.tax"],
            move_name="INV-1",
            post=True,
        )
        self.audit = self._receive_audit(
            self.invoice.name,
            event_id="evt_custom_invoice_number",
            payment_intent_id="pi_custom_invoice_number",
        )

        self._process_payment()

        self.audit.invalidate_recordset()
        self.invoice.invalidate_recordset(["amount_residual", "payment_state"])
        self.assertEqual(self.invoice.name, "INV-1")
        self.assertEqual(self.audit.internal_note, "INV-1")
        self.assertEqual(self.audit.state, "processed")
        self.assertEqual(self.audit.invoice_id, self.invoice)
        self.assertEqual(self.audit.payment_transaction_id.invoice_ids, self.invoice)
        self.assertTrue(self.invoice.currency_id.is_zero(self.invoice.amount_residual))
        self.assertEqual(
            self.invoice.payment_state,
            self.invoice._get_invoice_in_payment_state(),
        )

    def test_two_partial_payments_are_applied_to_the_same_invoice(self):
        self._process_payment(
            payment_intent=self._payment_intent(amount_received=750),
            charge=self._charge(amount_captured=750),
        )

        self.audit.invalidate_recordset()
        self.invoice.invalidate_recordset(["amount_residual", "payment_state"])
        first_audit = self.audit
        first_tx = first_audit.payment_transaction_id
        self.assertEqual(first_audit.state, "processed")
        self.assertEqual(first_audit.amount, 7.5)
        self.assertEqual(first_tx.amount, 7.5)
        self.assertEqual(first_tx.invoice_ids, self.invoice)
        self.assertEqual(first_tx.payment_id.invoice_ids, self.invoice)
        self.assertEqual(self.invoice.amount_residual, 5)
        self.assertEqual(self.invoice.payment_state, "partial")

        self.audit = self._receive_audit(
            self.invoice.name,
            event_id="evt_remaining",
            payment_intent_id="pi_remaining",
            amount_minor=500,
        )
        self._process_payment(
            payment_intent=self._payment_intent(
                amount_received=500,
                latest_charge="ch_remaining",
            ),
            charge=self._charge(id="ch_remaining", amount_captured=500),
        )

        self.audit.invalidate_recordset()
        self.invoice.invalidate_recordset(["amount_residual", "payment_state"])
        second_tx = self.audit.payment_transaction_id
        self.assertEqual(self.audit.state, "processed")
        self.assertEqual(self.audit.amount, 5)
        self.assertEqual(second_tx.amount, 5)
        self.assertNotEqual(second_tx, first_tx)
        self.assertEqual(second_tx.invoice_ids, self.invoice)
        self.assertEqual(second_tx.payment_id.invoice_ids, self.invoice)
        self.assertEqual(self.invoice.transaction_ids, first_tx | second_tx)
        self.assertTrue(self.invoice.currency_id.is_zero(self.invoice.amount_residual))
        self.assertEqual(
            self.invoice.payment_state,
            self.invoice._get_invoice_in_payment_state(),
        )

    @mute_logger(_STANDALONE_PAYMENT_LOGGER)
    def test_amount_above_invoice_residual_requires_review(self):
        self._process_payment(
            payment_intent=self._payment_intent(amount_received=1300),
            charge=self._charge(amount_captured=1300),
        )

        self.audit.invalidate_recordset()
        self.assertEqual(self.audit.state, "review_required")
        self.assertEqual(self.audit.failure_code, "invoice_amount_exceeds_residual")
        self.assertFalse(self.audit.payment_transaction_id)
        self.assertFalse(
            self.env["payment.transaction"].search(
                [("reference", "=", "STRIPE-STANDALONE-pi_processing")]
            )
        )

    @mute_logger(_STANDALONE_PAYMENT_LOGGER)
    def test_wrong_amount_requires_review_without_accounting(self):
        self._process_payment(payment_intent=self._payment_intent(amount_received=1200))

        self.audit.invalidate_recordset()
        self.assertEqual(self.audit.state, "review_required")
        self.assertEqual(self.audit.failure_code, "captured_amount_mismatch")
        self.assertFalse(self.audit.payment_transaction_id)
        self.assertFalse(
            self.env["payment.transaction"].search(
                [("reference", "=", "STRIPE-STANDALONE-pi_processing")]
            )
        )

    @mute_logger(_STANDALONE_PAYMENT_LOGGER)
    def test_non_card_present_charge_requires_review(self):
        charge = self._charge(payment_method_details={"type": "card", "card": {}})
        self._process_payment(charge=charge)

        self.audit.invalidate_recordset()
        self.assertEqual(self.audit.state, "review_required")
        self.assertEqual(self.audit.failure_code, "unsupported_payment_method")
        self.assertFalse(self.audit.payment_transaction_id)

    @mute_logger(_STANDALONE_PAYMENT_LOGGER)
    def test_unknown_invoice_requires_review(self):
        self.audit.internal_note = "INV/DOES/NOT/EXIST"
        self._process_payment()

        self.audit.invalidate_recordset()
        self.assertEqual(self.audit.state, "review_required")
        self.assertEqual(self.audit.failure_code, "invoice_not_found")
        self.assertFalse(self.audit.payment_transaction_id)
        log = self.env["ir.logging"].search(
            [
                (
                    "name",
                    "=",
                    "odoo.addons.payment_stripe_terminal_standalone.models.stripe_terminal_standalone_payment",
                ),
                ("func", "=", "_mark_review_required"),
                ("message", "ilike", self.audit.payment_intent_id),
            ]
        )
        self.assertEqual(len(log), 1)
        self.assertEqual(log.level, "WARNING")
        self.assertEqual(log.dbname, self.env.cr.dbname)
        self.assertIn("invoice_not_found", log.message)

    def test_technical_failure_rolls_back_for_stripe_retry(self):
        with self.assertRaisesRegex(RuntimeError, "Stripe unavailable"):
            with self.env.cr.savepoint():
                with patch.object(
                    type(self.provider),
                    "_stripe_terminal_retrieve_payment_intent",
                    side_effect=RuntimeError("Stripe unavailable"),
                ):
                    self.audit._process_payment_from_webhook()

        self.audit.invalidate_recordset()
        self.assertEqual(self.audit.state, "received")
        self.assertFalse(self.audit.failure_code)

    @mute_logger(_STANDALONE_PAYMENT_LOGGER)
    def test_post_processing_failure_rolls_back_accounting(self):
        transaction_model = type(self.env["payment.transaction"])
        original_post_process = transaction_model._post_process

        def fail_after_post_process(transactions):
            original_post_process(transactions)
            raise RuntimeError("Failure after post-processing")

        with patch.object(
            transaction_model,
            "_post_process",
            fail_after_post_process,
        ):
            with self.assertRaisesRegex(RuntimeError, "Failure after post-processing"):
                with self.env.cr.savepoint():
                    self._process_payment()

        self.audit.invalidate_recordset()
        self.invoice.invalidate_recordset(["amount_residual"])
        self.assertEqual(self.audit.state, "received")
        self.assertFalse(self.audit.failure_code)
        self.assertFalse(self.audit.payment_transaction_id)
        self.assertFalse(
            self.env["payment.transaction"].search(
                [("reference", "=", "STRIPE-STANDALONE-pi_processing")]
            )
        )
        self.assertEqual(self.invoice.amount_residual, 12.5)

    def test_historical_logged_record_is_never_processed(self):
        self.audit.state = "logged"
        with patch.object(
            type(self.provider), "_stripe_terminal_retrieve_payment_intent"
        ) as retrieve_intent:
            self.audit._process_payment_from_webhook()

        self.assertEqual(self.audit.state, "logged")
        retrieve_intent.assert_not_called()
