# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models

from .exceptions import ReviewRequired


class StripeTerminalStandalonePaymentValidation(models.Model):
    _inherit = "stripe.terminal.standalone.payment"

    def _validate_provider(self, provider):
        expected_state = "enabled" if self.livemode else "test"
        self._require_review(
            provider.code == "stripe",
            "invalid_provider",
            "The audit record is not linked to a Stripe provider.",
        )
        self._require_review(
            provider.state == expected_state,
            "provider_mode_mismatch",
            "The Stripe provider mode no longer matches the received event.",
        )

    def _validate_payment_intent(self, payment_intent):
        if not isinstance(payment_intent, dict) or payment_intent.get("error"):
            raise RuntimeError("Stripe did not return a PaymentIntent")
        self._require_review(
            payment_intent.get("object") == "payment_intent"
            and payment_intent.get("id") == self.payment_intent_id,
            "payment_intent_mismatch",
            "Stripe returned a different PaymentIntent.",
        )
        self._require_review(
            payment_intent.get("status") == "succeeded",
            "payment_intent_not_succeeded",
            "The Stripe PaymentIntent is not succeeded.",
        )
        self._require_review(
            payment_intent.get("livemode") is self.livemode,
            "payment_intent_mode_mismatch",
            "The PaymentIntent mode does not match the received event.",
        )
        self._require_review(
            payment_intent.get("capture_method") in ("automatic", "automatic_async"),
            "unsupported_capture_method",
            "Only automatically captured standalone payments are supported.",
        )

        metadata = payment_intent.get("metadata", {})
        self._require_review(
            isinstance(metadata, dict),
            "invalid_payment_intent_metadata",
            "The PaymentIntent metadata is malformed.",
        )
        if "x_terminal_standalone_note" in metadata:
            retrieved_note = metadata.get("x_terminal_standalone_note")
            self._require_review(
                isinstance(retrieved_note, str)
                and retrieved_note.strip() == self.internal_note,
                "payment_intent_note_mismatch",
                "The PaymentIntent note changed after webhook receipt.",
            )

        amount_minor = payment_intent.get("amount_received")
        self._require_review(
            isinstance(amount_minor, int)
            and not isinstance(amount_minor, bool)
            and amount_minor > 0,
            "invalid_amount_received",
            "The PaymentIntent has no valid positive received amount.",
        )
        currency = payment_intent.get("currency")
        self._require_review(
            isinstance(currency, str) and bool(currency),
            "invalid_payment_currency",
            "The PaymentIntent currency is missing or invalid.",
        )
        self._validate_tip(payment_intent)

        latest_charge = payment_intent.get("latest_charge")
        charge_id = (
            latest_charge.get("id")
            if isinstance(latest_charge, dict)
            else latest_charge
        )
        self._require_review(
            isinstance(charge_id, str) and bool(charge_id),
            "missing_successful_charge",
            "The PaymentIntent has no latest Charge.",
        )
        return {
            "amount_minor": amount_minor,
            "currency": currency.lower(),
            "charge_id": charge_id,
        }

    def _validate_tip(self, payment_intent):
        amount_details = payment_intent.get("amount_details")
        if amount_details is None:
            return
        self._require_review(
            isinstance(amount_details, dict),
            "invalid_amount_details",
            "The PaymentIntent amount details are malformed.",
        )
        tip = amount_details.get("tip")
        if tip is None:
            return
        self._require_review(
            isinstance(tip, dict),
            "invalid_tip",
            "The PaymentIntent tip details are malformed.",
        )
        tip_amount = tip.get("amount", 0)
        self._require_review(
            isinstance(tip_amount, int)
            and not isinstance(tip_amount, bool)
            and tip_amount == 0,
            "tipped_payment_unsupported",
            "Tipped standalone payments require manual review.",
        )

    def _validate_charge(self, charge, expected_charge_id, amount_minor, currency):
        if not isinstance(charge, dict) or charge.get("error"):
            raise RuntimeError("Stripe did not return a Charge")
        payment_intent = charge.get("payment_intent")
        payment_intent_id = (
            payment_intent.get("id")
            if isinstance(payment_intent, dict)
            else payment_intent
        )
        self._require_review(
            charge.get("object") == "charge"
            and charge.get("id") == expected_charge_id
            and payment_intent_id == self.payment_intent_id,
            "charge_mismatch",
            "The Charge does not belong to the received PaymentIntent.",
        )
        self._require_review(
            charge.get("status") == "succeeded"
            and charge.get("paid") is True
            and charge.get("captured") is True,
            "charge_not_succeeded",
            "The latest Charge is not successfully captured.",
        )
        self._require_review(
            charge.get("livemode") is self.livemode,
            "charge_mode_mismatch",
            "The Charge mode does not match the received event.",
        )
        self._require_review(
            charge.get("currency") == currency,
            "charge_currency_mismatch",
            "The Charge currency differs from the PaymentIntent currency.",
        )
        captured = charge.get("amount_captured")
        self._require_review(
            isinstance(captured, int)
            and not isinstance(captured, bool)
            and captured > 0
            and captured == amount_minor,
            "captured_amount_mismatch",
            "The Charge captured amount differs from the received amount.",
        )

        payment_method_details = charge.get("payment_method_details")
        self._require_review(
            isinstance(payment_method_details, dict),
            "invalid_payment_method_details",
            "The Charge payment method details are missing.",
        )
        payment_method_type = payment_method_details.get("type")
        self._require_review(
            payment_method_type in ("card_present", "interac_present"),
            "unsupported_payment_method",
            "The Charge was not collected with a supported card-present method.",
        )
        present_details = payment_method_details.get(payment_method_type) or {}
        self._require_review(
            isinstance(present_details, dict),
            "invalid_card_present_details",
            "The Charge card-present details are malformed.",
        )
        return {
            "charge_id": charge["id"],
            "reader_id": present_details.get("reader"),
            "location_id": present_details.get("location"),
        }

    def _find_invoice(self, provider):
        invoices = (
            self.env["account.move"]
            .sudo()
            .search(
                [
                    ("name", "=", self.internal_note),
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    ("company_id", "=", provider.company_id.id),
                ]
            )
        )
        self._require_review(
            len(invoices) == 1,
            "invoice_not_found" if not invoices else "ambiguous_invoice",
            (
                "No posted customer invoice exactly matches the standalone note."
                if not invoices
                else (
                    "More than one posted customer invoice matches the standalone note."
                )
            ),
        )
        return invoices

    def _lock_and_validate_invoice(self, invoice, provider, amount_minor, currency):
        fields_to_read = [
            "state",
            "move_type",
            "company_id",
            "currency_id",
            "partner_id",
            "amount_residual",
            "payment_state",
        ]
        invoice.flush_recordset(fields_to_read)
        # A second terminal payment can arrive before the first request commits. Locking
        # makes the residual and conflict checks observe those requests in sequence.
        self.env.cr.execute(
            "SELECT id FROM account_move WHERE id = %s FOR UPDATE", [invoice.id]
        )
        invoice.invalidate_recordset(fields_to_read, flush=False)

        self._require_review(
            invoice.state == "posted" and invoice.move_type == "out_invoice",
            "invoice_no_longer_payable",
            "The matched invoice is no longer a posted customer invoice.",
        )
        self._require_review(
            invoice.company_id == provider.company_id,
            "invoice_company_mismatch",
            "The matched invoice belongs to a different company.",
        )
        self._require_review(
            not invoice.currency_id.is_zero(invoice.amount_residual),
            "invoice_already_paid",
            "The matched invoice is already fully paid.",
        )
        conflicts = (
            self.env["payment.transaction"]
            .sudo()
            .search(
                [
                    ("invoice_ids", "in", invoice.id),
                    ("state", "in", ("pending", "authorized", "done")),
                ]
            )
        )
        self._require_review(
            not conflicts,
            "conflicting_payment_transaction",
            "The invoice already has a pending, authorized, or completed transaction.",
        )
        self._require_review(
            invoice.currency_id.name.lower() == currency,
            "invoice_currency_mismatch",
            "The PaymentIntent currency differs from the invoice currency.",
        )
        expected_minor = provider._stripe_terminal_to_minor_currency_units(
            invoice.amount_residual, invoice.currency_id
        )
        self._require_review(
            expected_minor == amount_minor,
            "invoice_amount_mismatch",
            "The captured amount does not equal the full invoice residual.",
        )

    def _validate_accounting_configuration(self, provider, invoice):
        lines = (
            self.env["account.payment.method.line"]
            .sudo()
            .search([("payment_provider_id", "=", provider.id)])
        )
        self._require_review(
            len(lines) == 1,
            "ambiguous_payment_method_line",
            "The Stripe provider must have exactly one inbound payment method line.",
        )
        self._validate_payment_method_line(lines, provider, invoice)
        return lines

    def _validate_payment_method_line(self, line, provider, invoice):
        journal = line.journal_id
        self._require_review(
            bool(journal)
            and journal.type == "bank"
            and journal.company_id == provider.company_id
            and journal.company_id == invoice.company_id,
            "invalid_payment_journal",
            "The Stripe provider payment journal is missing or inconsistent.",
        )
        self._require_review(
            not journal.currency_id or journal.currency_id == invoice.currency_id,
            "payment_journal_currency_mismatch",
            "The Stripe payment journal does not support the invoice currency.",
        )
        self._require_review(
            line.payment_method_id.code == "stripe"
            and line.payment_method_id.payment_type == "inbound",
            "invalid_payment_method_line",
            "The provider payment method line is not an inbound Stripe method.",
        )
        account = line.payment_account_id
        self._require_review(
            bool(account)
            and not account.deprecated
            and provider.company_id in account.company_ids
            and account.reconcile,
            "invalid_outstanding_account",
            "The Stripe payment method needs a valid reconcilable outstanding account.",
        )

    def _validate_transaction_reference(self, reference):
        self._require_review(
            not self.env["payment.transaction"]
            .sudo()
            .search_count([("reference", "=", reference)], limit=1),
            "transaction_reference_exists",
            "A payment transaction already uses this standalone reference.",
        )

    def _validate_handled_transaction(self, tx, handled_tx):
        self._require_review(
            handled_tx == tx and tx.state == "done",
            "transaction_not_completed",
            "Stripe notification handling did not complete the transaction.",
        )
        self._require_review(
            tx.provider_reference == self.payment_intent_id,
            "transaction_provider_reference_mismatch",
            "The transaction provider reference is not the PaymentIntent ID.",
        )

    def _validate_post_processed_accounting(self, tx, invoice, payment_method_line):
        payment = tx.payment_id
        self._require_review(
            bool(payment)
            and payment.state in ("in_process", "paid")
            and bool(payment.move_id)
            and payment.move_id.state == "posted"
            and tx.is_post_processed,
            "payment_post_processing_failed",
            "Odoo did not create and post the expected accounting payment.",
        )
        self._require_review(
            payment.journal_id == payment_method_line.journal_id
            and payment.payment_method_line_id == payment_method_line
            and payment.outstanding_account_id
            == payment_method_line.payment_account_id,
            "payment_configuration_mismatch",
            "The accounting payment did not use the configured Stripe payment method.",
        )
        self._require_review(
            invoice.currency_id.is_zero(invoice.amount_residual),
            "invoice_not_fully_paid",
            "The accounting payment did not clear the invoice residual.",
        )
        self._require_review(
            invoice.payment_state == invoice._get_invoice_in_payment_state(),
            "invoice_payment_state_mismatch",
            "The invoice did not reach Odoo's expected paid state.",
        )

    @staticmethod
    def _require_review(condition, code, reason):
        if not condition:
            raise ReviewRequired(code, reason)
