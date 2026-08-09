# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from psycopg2.errors import UniqueViolation

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StripeTerminalStandalonePayment(models.Model):
    _name = "stripe.terminal.standalone.payment"
    _description = "Stripe Terminal Standalone Payment Audit"
    _order = "id desc"

    event_id = fields.Char(
        required=True,
        index=True,
        readonly=True,
        help=(
            "ID of the Stripe Event that delivered this webhook (evt_...). See "
            "https://docs.stripe.com/api/events/object."
        ),
    )
    event_api_version = fields.Char(
        readonly=True,
        help=(
            "Stripe API version used to serialize this event. Retaining it makes "
            "payload-shape changes auditable. See "
            "https://docs.stripe.com/api/events/object#event_object-api_version."
        ),
    )
    payment_intent_id = fields.Char(
        required=True,
        index=True,
        readonly=True,
        help=(
            "ID of the Stripe PaymentIntent representing the customer's payment "
            "(pi_...). See https://docs.stripe.com/api/payment_intents/object."
        ),
    )
    charge_id = fields.Char(
        index=True,
        readonly=True,
        help=(
            "ID of the Stripe Charge created by the PaymentIntent (ch_...). This is a "
            "Stripe payment-attempt record, not an Odoo payment transaction. See "
            "https://docs.stripe.com/api/charges/object."
        ),
    )
    provider_id = fields.Many2one(
        "payment.provider",
        required=True,
        index=True,
        ondelete="restrict",
        readonly=True,
        help=(
            "Odoo Stripe payment provider whose provider-bound webhook verified and "
            "received the event."
        ),
    )
    company_id = fields.Many2one(
        related="provider_id.company_id",
        store=True,
        index=True,
        readonly=True,
        help=(
            "Odoo company owning the Stripe provider. This stored field enforces "
            "multi-company audit access."
        ),
    )
    livemode = fields.Boolean(
        required=True,
        readonly=True,
        help=(
            "Whether Stripe created the event in live mode. False identifies a test "
            "mode event. See "
            "https://docs.stripe.com/api/events/object#event_object-livemode."
        ),
    )
    reader_id = fields.Char(
        index=True,
        readonly=True,
        help=(
            "ID of the Stripe Terminal Reader that collected the payment (tmr_...), "
            "when included in the event. See "
            "https://docs.stripe.com/api/terminal/readers/object."
        ),
    )
    location_id = fields.Char(
        index=True,
        readonly=True,
        help=(
            "ID of the Stripe Terminal Location assigned to the reader (tml_...), "
            "when included in the event. See "
            "https://docs.stripe.com/api/terminal/locations/object."
        ),
    )
    internal_note = fields.Char(
        required=True,
        readonly=True,
        help=(
            "Trimmed invoice reference copied from the PaymentIntent metadata key "
            "x_terminal_standalone_note. See ."
            "https://docs.stripe.com/terminal/payments/standalone-mode/get-started#payment-reconciliation"
        ),
    )
    amount_minor = fields.Integer(
        readonly=True,
        help=(
            "Amount received by Stripe in the currency's minor unit, such as cents. "
            "For example, 1250 USD means USD 12.50. See "
            "https://docs.stripe.com/currencies."
        ),
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        help="Amount received by Stripe expressed in major currency units.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        ondelete="restrict",
        readonly=True,
        help=(
            "Odoo currency matching the lowercase currency code in the Stripe "
            "PaymentIntent. See https://docs.stripe.com/currencies."
        ),
    )
    invoice_id = fields.Many2one(
        "account.move",
        index=True,
        ondelete="restrict",
        readonly=True,
        help=("Odoo customer invoice matched from the internal note."),
    )
    payment_transaction_id = fields.Many2one(
        "payment.transaction",
        index=True,
        ondelete="restrict",
        readonly=True,
        help=(
            "Odoo payment.transaction created to process this payment through Odoo's "
            "payment and accounting lifecycle. Unlike charge_id, this references an "
            "Odoo record."
        ),
    )
    state = fields.Selection(
        selection=[
            ("logged", "Logged"),
            ("received", "Received"),
            ("processing", "Processing"),
            ("matched", "Matched"),
            ("processed", "Processed"),
            ("review_required", "Review Required"),
            ("failed", "Failed"),
        ],
        required=True,
        default="logged",
        index=True,
        readonly=True,
        help=("Current Odoo processing state of this audit record."),
    )
    failure_code = fields.Char(
        readonly=True,
        help=(
            "Stable integration-defined code identifying why later automatic "
            "processing failed or requires review."
        ),
    )
    failure_reason = fields.Text(
        readonly=True,
        help=("Human-readable details about a later processing or validation failure."),
    )
    retry_count = fields.Integer(
        readonly=True,
        help=(
            "Number of automatic processing attempts made by a later queued "
            "processor. Always zero in Part 2."
        ),
    )
    next_retry_at = fields.Datetime(
        index=True,
        readonly=True,
        help=(
            "Earliest time at which a later queued processor may retry this record. "
            "Unused in Part 2."
        ),
    )
    processing_started_at = fields.Datetime(
        readonly=True,
        help=(
            "Time at which a later worker claimed this record for processing. Unused "
            "in Part 2."
        ),
    )
    processed_at = fields.Datetime(
        readonly=True,
        help=(
            "Time at which Odoo successfully finished processing the standalone "
            "payment. Unused in Part 2."
        ),
    )
    event_summary = fields.Text(
        readonly=True,
        help=(
            "Concise, non-sensitive description of the verified Stripe event. The "
            "complete webhook payload is deliberately not stored."
        ),
    )

    _sql_constraints = [
        (
            "provider_event_unique",
            "unique(provider_id, event_id)",
            "This Stripe event has already been logged for this provider.",
        ),
        (
            "provider_intent_unique",
            "unique(provider_id, payment_intent_id)",
            "This Stripe PaymentIntent has already been logged for this provider.",
        ),
    ]

    @api.model
    def _log_event(self, provider, event, payment_intent, note):
        event_id = event.get("id")
        payment_intent_id = payment_intent.get("id")
        values = self._get_event_values(provider, event, payment_intent, note)
        try:
            with self.env.cr.savepoint():
                return self.create(values)
        except UniqueViolation:
            existing = self.search(
                [
                    ("provider_id", "=", provider.id),
                    "|",
                    ("event_id", "=", event_id),
                    ("payment_intent_id", "=", payment_intent_id),
                ],
                order="id",
                limit=1,
            )
            if not existing:
                raise
            _logger.info(
                "Ignored duplicate Stripe Terminal standalone event %s for %s",
                event_id,
                payment_intent_id,
            )
            return existing

    @api.model
    def _get_event_values(self, provider, event, payment_intent, note):
        # Stripe reports amounts as integer minor units. Reject booleans explicitly
        # because Python treats bool as a subclass of int.
        amount_minor = payment_intent.get("amount_received")
        if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
            amount_minor = 0

        # Stripe uses lowercase ISO currency codes. Include inactive Odoo currencies so
        # the event can still be audited even when that currency is not currently used.
        currency_code = payment_intent.get("currency")
        currency = self.env["res.currency"].browse()
        if isinstance(currency_code, str) and currency_code:
            currency = (
                self.env["res.currency"]
                .with_context(active_test=False)
                .search([("name", "=", currency_code.upper())], limit=1)
            )

        # Stripe expandable fields may contain either an object or only its ID.
        latest_charge = payment_intent.get("latest_charge")
        if isinstance(latest_charge, str):
            charge_id = latest_charge
            charge = {}
        elif isinstance(latest_charge, dict):
            charge_id = latest_charge.get("id")
            charge = latest_charge
        else:
            charge_id = False
            charge = {}

        # Reader and location are nested under the Charge's payment-method type. They
        # remain empty when latest_charge was not expanded in the webhook payload.
        payment_method_details = charge.get("payment_method_details") or {}
        if not isinstance(payment_method_details, dict):
            payment_method_details = {}
        payment_method_type = payment_method_details.get("type")
        present_details = payment_method_details.get(payment_method_type) or {}
        if not isinstance(present_details, dict):
            present_details = {}

        event_id = event.get("id")
        payment_intent_id = payment_intent.get("id")
        # Persist only the small, whitelisted snapshot needed for audit and later
        # processing. The complete verified webhook payload is deliberately discarded.
        return {
            "event_id": event_id,
            "event_api_version": event.get("api_version"),
            "payment_intent_id": payment_intent_id,
            "charge_id": charge_id,
            "provider_id": provider.id,
            "livemode": event.get("livemode") is True,
            "reader_id": present_details.get("reader"),
            "location_id": present_details.get("location"),
            "internal_note": note,
            "amount_minor": amount_minor,
            "amount": (
                provider._stripe_terminal_to_major_currency_units(
                    amount_minor, currency
                )
                if currency
                else 0
            ),
            "currency_id": currency.id,
            "state": "logged",
            "event_summary": (
                f"Verified payment_intent.succeeded event {event_id} for "
                f"PaymentIntent {payment_intent_id}."
            ),
        }
