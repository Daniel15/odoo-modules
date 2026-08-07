# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from werkzeug.exceptions import Forbidden

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    stripe_terminal_legacy_webhook_secret = fields.Char(
        help=(
            "Signing secret for the temporary legacy POS Terminal webhook. Clear this "
            "after removing the legacy endpoint from Stripe."
        ),
        groups="base.group_system",
        copy=False,
    )

    def action_stripe_sd_create_webhook(self):
        """Compatibility action for the original POS provider view."""
        self.ensure_one()
        self._stripe_terminal_check_webhook_configuration_access()
        if self.stripe_terminal_webhook_endpoint_id:
            return self.action_stripe_terminal_update_webhook()
        return self.action_stripe_terminal_create_webhook()

    def action_stripe_terminal_retire_legacy_webhook(self):
        self.ensure_one()
        self._stripe_terminal_check_webhook_configuration_access()
        self.stripe_terminal_legacy_webhook_secret = False
        return self._stripe_terminal_webhook_notification(
            _(
                "The legacy Terminal webhook secret was cleared. Ensure the old "
                "endpoint has also been removed from Stripe."
            ),
            "info",
        )

    def _stripe_terminal_verify_legacy_webhook_signature(
        self, raw_payload, signature_header
    ):
        self.ensure_one()
        legacy_secret = self.stripe_terminal_legacy_webhook_secret
        if not legacy_secret and not self.stripe_terminal_webhook_endpoint_id:
            legacy_secret = self.stripe_terminal_webhook_secret
        if not legacy_secret:
            raise Forbidden()
        return self._stripe_terminal_verify_webhook_signature(
            raw_payload, signature_header, webhook_secret=legacy_secret
        )

    def _stripe_terminal_find_legacy_webhook_providers(
        self, raw_payload, signature_header
    ):
        candidates = self.search(
            [
                ("code", "=", "stripe"),
                "|",
                ("stripe_terminal_legacy_webhook_secret", "!=", False),
                "&",
                ("stripe_terminal_webhook_endpoint_id", "=", False),
                ("stripe_terminal_webhook_secret", "!=", False),
            ]
        )
        matching_providers = self.browse()
        for provider in candidates:
            try:
                provider._stripe_terminal_verify_legacy_webhook_signature(
                    raw_payload, signature_header
                )
            except Forbidden:
                continue
            matching_providers |= provider
        if not matching_providers:
            _logger.warning(
                "Rejected legacy Terminal event; signature matched no providers"
            )
            raise Forbidden()
        return matching_providers

    def _stripe_sd_resolve_legacy_webhook_provider(self, event):
        stripe_object = event.get("data", {}).get("object", {})
        reader_id = stripe_object.get("id")
        if not reader_id:
            return self if len(self) == 1 else self.browse()

        payment_method_sudo = (
            self.env["pos.payment.method"]
            .sudo()
            .search([("stripe_reader_id", "=", reader_id)], limit=1)
        )
        if not payment_method_sudo:
            _logger.warning("Received Terminal event for unknown reader: %s", reader_id)
            return self.browse()
        providers = self.filtered(
            lambda provider: provider.company_id == payment_method_sudo.company_id
        )
        if len(providers) != 1:
            _logger.warning(
                "Could not resolve one Stripe provider for reader %s", reader_id
            )
            return self.browse()
        return providers

    def _stripe_terminal_dispatch_webhook_event(self, event):
        self.ensure_one()
        if super()._stripe_terminal_dispatch_webhook_event(event):
            return True
        event_type = event.get("type")
        if event_type not in (
            "terminal.reader.action_succeeded",
            "terminal.reader.action_failed",
        ):
            return False

        stripe_object = event.get("data", {}).get("object", {})
        reader_id = stripe_object.get("id")
        if not reader_id:
            _logger.warning("Received Terminal event without reader ID")
            return True

        payment_method_sudo = (
            self.env["pos.payment.method"]
            .sudo()
            .search(
                [
                    ("stripe_reader_id", "=", reader_id),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
        )
        if not payment_method_sudo:
            _logger.warning("Received Terminal event for unknown reader: %s", reader_id)
            return True

        action = stripe_object.get("action", {})
        payment_intent_id = action.get("process_payment_intent", {}).get(
            "payment_intent"
        )
        if not payment_intent_id:
            _logger.warning("Received Terminal event without payment_intent_id")
            return True

        if event_type == "terminal.reader.action_succeeded":
            status = "succeeded"
            failure_message = ""
        else:
            status = "failed"
            failure_message = (
                action.get("failure_message", "")
                or stripe_object.get("last_error", {}).get("message", "")
                or _("Payment failed")
            )

        notification_data = {
            "payment_intent_id": payment_intent_id,
            "status": status,
            "failure_message": failure_message,
        }
        for pos_config in self._stripe_sd_find_pos_configs(payment_method_sudo):
            pos_config._notify("STRIPE_SD_PAYMENT_STATUS", notification_data)
        return True

    def _stripe_sd_find_pos_configs(self, payment_method_sudo):
        """Find POS configs with open sessions using the payment method."""
        self.ensure_one()
        pos_sessions = (
            self.env["pos.session"]
            .sudo()
            .search(
                [
                    ("state", "=", "opened"),
                    ("config_id.payment_method_ids", "in", payment_method_sudo.ids),
                ]
            )
        )
        return pos_sessions.mapped("config_id")
