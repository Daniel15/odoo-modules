# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.payment_stripe_terminal_standalone.models.exceptions import (
    ReviewRequired,
)

from .common import StandaloneProcessingCommon


class TestStripeTerminalStandaloneValidation(StandaloneProcessingCommon):
    def _assert_review(self, code, method, *args):
        with self.assertRaises(ReviewRequired) as raised:
            method(*args)
        self.assertEqual(raised.exception.code, code)

    def _valid_payment_method_line(
        self,
        journal_type="bank",
        journal_currency=False,
        payment_method_code="stripe",
        payment_type="inbound",
        account_reconcile=True,
    ):
        return SimpleNamespace(
            journal_id=SimpleNamespace(
                type=journal_type,
                company_id=self.provider.company_id,
                currency_id=journal_currency,
            ),
            payment_method_id=SimpleNamespace(
                code=payment_method_code,
                payment_type=payment_type,
            ),
            payment_account_id=SimpleNamespace(
                deprecated=False,
                company_ids=self.provider.company_id,
                reconcile=account_reconcile,
            ),
        )

    def _valid_post_processing_records(
        self, amount=12.5, amount_residual=0, payment_state="paid"
    ):
        payment_method_line = self._valid_payment_method_line()
        payment = SimpleNamespace(
            state="paid",
            move_id=SimpleNamespace(state="posted"),
            journal_id=payment_method_line.journal_id,
            payment_method_line_id=payment_method_line,
            outstanding_account_id=payment_method_line.payment_account_id,
        )
        tx = SimpleNamespace(
            amount=amount,
            payment_id=payment,
            is_post_processed=True,
        )
        invoice = SimpleNamespace(
            currency_id=SimpleNamespace(is_zero=lambda value: abs(value) < 0.000001),
            amount_residual=amount_residual,
            payment_state=payment_state,
            _get_invoice_in_payment_state=lambda: "paid",
        )
        return tx, invoice, payment_method_line

    def test_provider_validation_rules(self):
        cases = [
            (
                "invalid_provider",
                SimpleNamespace(code="other", state="test"),
            ),
            (
                "provider_mode_mismatch",
                SimpleNamespace(code="stripe", state="disabled"),
            ),
        ]
        for code, provider in cases:
            with self.subTest(code=code):
                self._assert_review(code, self.audit._validate_provider, provider)

    def test_payment_intent_response_must_be_valid(self):
        for response in (None, {"error": {"message": "unavailable"}}):
            with self.subTest(response=response):
                with self.assertRaisesRegex(
                    RuntimeError, "Stripe did not return a PaymentIntent"
                ):
                    self.audit._validate_payment_intent(response)

    def test_automatic_capture_methods_are_supported(self):
        for capture_method in ("automatic", "automatic_async"):
            with self.subTest(capture_method=capture_method):
                self.audit._validate_payment_intent(
                    self._payment_intent(capture_method=capture_method)
                )

    def test_payment_intent_validation_rules(self):
        cases = [
            (
                "payment_intent_mismatch",
                self._payment_intent(id="pi_other"),
            ),
            (
                "payment_intent_not_succeeded",
                self._payment_intent(status="processing"),
            ),
            (
                "payment_intent_mode_mismatch",
                self._payment_intent(livemode=True),
            ),
            (
                "unsupported_capture_method",
                self._payment_intent(capture_method="manual"),
            ),
            (
                "invalid_payment_intent_metadata",
                self._payment_intent(metadata=[]),
            ),
            (
                "payment_intent_note_mismatch",
                self._payment_intent(
                    metadata={"x_terminal_standalone_note": "INV/OTHER"}
                ),
            ),
            (
                "invalid_amount_received",
                self._payment_intent(amount_received=True),
            ),
            (
                "invalid_payment_currency",
                self._payment_intent(currency=""),
            ),
            (
                "missing_successful_charge",
                self._payment_intent(latest_charge=None),
            ),
        ]
        for code, payment_intent in cases:
            with self.subTest(code=code):
                self._assert_review(
                    code,
                    self.audit._validate_payment_intent,
                    payment_intent,
                )

    def test_tip_validation_rules(self):
        cases = [
            (
                "invalid_amount_details",
                self._payment_intent(amount_details=[]),
            ),
            (
                "invalid_tip",
                self._payment_intent(amount_details={"tip": []}),
            ),
            (
                "tipped_payment_unsupported",
                self._payment_intent(amount_details={"tip": {"amount": 100}}),
            ),
        ]
        for code, payment_intent in cases:
            with self.subTest(code=code):
                self._assert_review(code, self.audit._validate_tip, payment_intent)

    def test_charge_response_must_be_valid(self):
        for response in (None, {"error": {"message": "unavailable"}}):
            with self.subTest(response=response):
                with self.assertRaisesRegex(
                    RuntimeError, "Stripe did not return a Charge"
                ):
                    self.audit._validate_charge(
                        response,
                        "ch_processing",
                        1250,
                        "usd",
                    )

    def test_charge_validation_rules(self):
        cases = [
            (
                "charge_mismatch",
                self._charge(payment_intent="pi_other"),
            ),
            (
                "charge_not_succeeded",
                self._charge(captured=False),
            ),
            (
                "charge_mode_mismatch",
                self._charge(livemode=True),
            ),
            (
                "charge_currency_mismatch",
                self._charge(currency="eur"),
            ),
            (
                "captured_amount_mismatch",
                self._charge(amount_captured=1200),
            ),
            (
                "invalid_payment_method_details",
                self._charge(payment_method_details=None),
            ),
            (
                "unsupported_payment_method",
                self._charge(payment_method_details={"type": "card"}),
            ),
            (
                "invalid_card_present_details",
                self._charge(
                    payment_method_details={
                        "type": "card_present",
                        "card_present": "invalid",
                    }
                ),
            ),
        ]
        for code, charge in cases:
            with self.subTest(code=code):
                self._assert_review(
                    code,
                    self.audit._validate_charge,
                    charge,
                    "ch_processing",
                    1250,
                    "usd",
                )

    def test_invoice_lookup_validation_rules(self):
        move_model = self.env["account.move"]
        another_invoice = self._create_invoice_one_line(
            price_unit=12.5,
            tax_ids=self.env["account.tax"],
            post=True,
        )
        cases = [
            ("invoice_not_found", move_model.browse()),
            ("ambiguous_invoice", self.invoice | another_invoice),
        ]
        for code, invoices in cases:
            with self.subTest(code=code):
                with patch.object(type(move_model), "search", return_value=invoices):
                    self._assert_review(
                        code,
                        self.audit._find_invoice,
                        self.provider,
                    )

    def test_invoice_must_still_be_payable_after_lock(self):
        self.invoice.button_draft()
        self._assert_review(
            "invoice_no_longer_payable",
            self.audit._lock_and_validate_invoice,
            self.invoice,
            self.provider,
            1250,
            "usd",
        )

    def test_locked_invoice_must_still_match_provider_company(self):
        other_company = self.env["res.company"].create({"name": "Other Company"})
        provider = SimpleNamespace(company_id=other_company)
        self._assert_review(
            "invoice_company_mismatch",
            self.audit._lock_and_validate_invoice,
            self.invoice,
            provider,
            1250,
            "usd",
        )

    def test_locked_invoice_must_have_residual(self):
        with patch.object(
            type(self.invoice.currency_id),
            "is_zero",
            return_value=True,
        ):
            self._assert_review(
                "invoice_already_paid",
                self.audit._lock_and_validate_invoice,
                self.invoice,
                self.provider,
                1250,
                "usd",
            )

    def test_locked_invoice_must_not_have_conflicting_transaction(self):
        transaction_model = self.env["payment.transaction"]
        with patch.object(
            type(transaction_model),
            "search",
            return_value=transaction_model.browse(-1),
        ):
            self._assert_review(
                "conflicting_payment_transaction",
                self.audit._lock_and_validate_invoice,
                self.invoice,
                self.provider,
                1250,
                "usd",
            )

    def test_locked_invoice_currency_must_match(self):
        self._assert_review(
            "invoice_currency_mismatch",
            self.audit._lock_and_validate_invoice,
            self.invoice,
            self.provider,
            1250,
            "eur",
        )

    def test_locked_invoice_accepts_partial_amount(self):
        residual_before = self.audit._lock_and_validate_invoice(
            self.invoice,
            self.provider,
            1200,
            "usd",
        )
        self.assertEqual(residual_before, 12.5)

    def test_locked_invoice_rejects_amount_above_residual(self):
        self._assert_review(
            "invoice_amount_exceeds_residual",
            self.audit._lock_and_validate_invoice,
            self.invoice,
            self.provider,
            1300,
            "usd",
        )

    def test_provider_must_have_exactly_one_payment_method_line(self):
        line_model = self.env["account.payment.method.line"]
        with patch.object(
            type(line_model),
            "search",
            return_value=line_model.browse(),
        ):
            self._assert_review(
                "ambiguous_payment_method_line",
                self.audit._validate_accounting_configuration,
                self.provider,
                self.invoice,
            )

    def test_payment_method_line_validation_rules(self):
        other_currency = (
            self.currency_euro
            if self.invoice.currency_id != self.currency_euro
            else self.currency_usd
        )
        cases = [
            (
                "invalid_payment_journal",
                self._valid_payment_method_line(journal_type="general"),
            ),
            (
                "payment_journal_currency_mismatch",
                self._valid_payment_method_line(journal_currency=other_currency),
            ),
            (
                "invalid_payment_method_line",
                self._valid_payment_method_line(payment_method_code="manual"),
            ),
            (
                "invalid_outstanding_account",
                self._valid_payment_method_line(account_reconcile=False),
            ),
        ]
        for code, line in cases:
            with self.subTest(code=code):
                self._assert_review(
                    code,
                    self.audit._validate_payment_method_line,
                    line,
                    self.provider,
                    self.invoice,
                )

    def test_transaction_reference_must_be_unique(self):
        transaction_model = self.env["payment.transaction"]
        with patch.object(type(transaction_model), "search_count", return_value=1):
            self._assert_review(
                "transaction_reference_exists",
                self.audit._validate_transaction_reference,
                "STRIPE-STANDALONE-pi_processing",
            )

    def test_handled_transaction_validation_rules(self):
        incomplete_tx = SimpleNamespace(
            state="pending",
            provider_reference=self.audit.payment_intent_id,
        )
        wrong_reference_tx = SimpleNamespace(
            state="done",
            provider_reference="pi_other",
        )
        cases = [
            ("transaction_not_completed", incomplete_tx, incomplete_tx),
            (
                "transaction_provider_reference_mismatch",
                wrong_reference_tx,
                wrong_reference_tx,
            ),
        ]
        for code, tx, handled_tx in cases:
            with self.subTest(code=code):
                self._assert_review(
                    code,
                    self.audit._validate_handled_transaction,
                    tx,
                    handled_tx,
                )

    def test_post_processing_must_create_posted_payment(self):
        tx, invoice, payment_method_line = self._valid_post_processing_records()
        tx.payment_id = False
        self._assert_review(
            "payment_post_processing_failed",
            self.audit._validate_post_processed_accounting,
            tx,
            invoice,
            payment_method_line,
            12.5,
        )

    def test_post_processed_payment_must_use_validated_configuration(self):
        tx, invoice, payment_method_line = self._valid_post_processing_records()
        tx.payment_id.journal_id = False
        self._assert_review(
            "payment_configuration_mismatch",
            self.audit._validate_post_processed_accounting,
            tx,
            invoice,
            payment_method_line,
            12.5,
        )

    def test_post_processing_accepts_expected_partial_residual(self):
        tx, invoice, payment_method_line = self._valid_post_processing_records(
            amount=5, amount_residual=7.5, payment_state="partial"
        )
        self.audit._validate_post_processed_accounting(
            tx,
            invoice,
            payment_method_line,
            12.5,
        )

    def test_post_processing_must_apply_full_transaction_amount(self):
        tx, invoice, payment_method_line = self._valid_post_processing_records()
        invoice.amount_residual = 1
        self._assert_review(
            "invoice_residual_mismatch",
            self.audit._validate_post_processed_accounting,
            tx,
            invoice,
            payment_method_line,
            12.5,
        )

    def test_post_processing_must_set_expected_invoice_state(self):
        tx, invoice, payment_method_line = self._valid_post_processing_records()
        invoice._get_invoice_in_payment_state = lambda: "in_payment"
        self._assert_review(
            "invoice_payment_state_mismatch",
            self.audit._validate_post_processed_accounting,
            tx,
            invoice,
            payment_method_line,
            12.5,
        )
