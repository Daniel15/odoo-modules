# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from odoo import models

_logger = logging.getLogger(__name__)

STANDALONE_PAYMENT_EVENT = "payment_intent.succeeded"
# https://docs.stripe.com/terminal/payments/standalone-mode/get-started#payment-reconciliation
STANDALONE_NOTE_KEY = "x_terminal_standalone_note"


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    def _stripe_terminal_get_webhook_events(self):
        events = super()._stripe_terminal_get_webhook_events()
        if STANDALONE_PAYMENT_EVENT not in events:
            events.append(STANDALONE_PAYMENT_EVENT)
        return events

    def _stripe_terminal_dispatch_webhook_event(self, event):
        self.ensure_one()
        if super()._stripe_terminal_dispatch_webhook_event(event):
            return True
        if event.get("type") != STANDALONE_PAYMENT_EVENT:
            return False

        data = event.get("data")
        stripe_object = data.get("object") if isinstance(data, dict) else None
        if not isinstance(stripe_object, dict):
            return True
        if (
            stripe_object.get("object") != "payment_intent"
            or stripe_object.get("status") != "succeeded"
        ):
            return True

        metadata = stripe_object.get("metadata")
        note = metadata.get(STANDALONE_NOTE_KEY) if isinstance(metadata, dict) else None
        if not isinstance(note, str) or not (note := note.strip()):
            return True

        audit, created = (
            self.env["stripe.terminal.standalone.payment"]
            .sudo()
            ._log_event(self, event, stripe_object, note)
        )
        if created:
            _logger.info(
                "Logged Stripe Terminal standalone candidate %s for %s %s with invoice "
                "note %s and provider %s; automatic processing is not implemented yet.",
                audit.payment_intent_id,
                audit.amount,
                audit.currency_id.name,
                audit.internal_note,
                self.display_name,
            )
        return True
