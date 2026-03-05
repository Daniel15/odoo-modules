# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

import werkzeug

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    stripe_reader_id = fields.Selection(
        selection="_get_stripe_readers",
        string="Stripe Reader",
        help="The Stripe terminal reader ID (tmr_xxx)",
        copy=False,
    )
    stripe_terminal_webhook_secret = fields.Char(
        help="Webhook signing secret for terminal events",
        copy=False,
    )

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [
            ("stripe_server_driven", "Stripe (Server-driven)")
        ]

    @api.model
    def _get_stripe_readers(self):
        stripe_provider = self.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        if not stripe_provider:
            return []
        try:
            result = stripe_provider._stripe_make_request(
                "terminal/readers", method="GET"
            )
        except Exception as e:
            raise UserError(_("Failed to fetch Stripe readers: %s", e)) from e
        if not result or result.get("error"):
            error_msg = (
                result.get("error", {}).get("message", _("Unknown error"))
                if result
                else _("Empty response")
            )
            raise UserError(_("Failed to fetch Stripe readers: %s", error_msg))
        readers = result.get("data", [])
        return [(r["id"], f"{r.get('label', '')} ({r['id']})") for r in readers]

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ["stripe_reader_id"]
        return params

    @api.constrains("stripe_reader_id")
    def _check_stripe_reader_id(self):
        for payment_method in self:
            if not payment_method.stripe_reader_id:
                continue
            existing = self.search(
                [
                    ("id", "!=", payment_method.id),
                    ("stripe_reader_id", "=", payment_method.stripe_reader_id),
                ],
                limit=1,
            )
            if existing:
                raise ValidationError(
                    _(
                        "Reader %(reader)s is already used on payment method"
                        " %(payment_method)s.",
                        reader=payment_method.stripe_reader_id,
                        payment_method=existing.display_name,
                    )
                )

    def _get_stripe_payment_provider(self):
        stripe_payment_provider = self.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        if not stripe_payment_provider:
            raise UserError(
                _(
                    "Stripe payment provider for company %s is missing",
                    self.env.company.name,
                )
            )
        return stripe_payment_provider

    def _stripe_calculate_amount(self, amount):
        currency = self.journal_id.currency_id or self.company_id.currency_id
        return int(round(amount / currency.rounding))

    def action_stripe_sd_create_webhook(self):
        """Create a Stripe webhook for terminal events.

        :return: A feedback notification
        :rtype: dict
        """
        self.ensure_one()

        if self.stripe_terminal_webhook_secret:
            message = _("Your Stripe Webhook is already set up.")
            notification_type = "warning"
        else:
            provider = self._get_stripe_payment_provider()
            if not provider.stripe_secret_key:
                message = _(
                    "You cannot create a Stripe Webhook if your Stripe Secret"
                    " Key is not set."
                )
                notification_type = "danger"
            else:
                from odoo.addons.payment_stripe import const as stripe_const

                from ..controllers.main import (
                    PosStripeServerDrivenController,
                )

                base_url = (
                    self.env["ir.config_parameter"].sudo().get_param("web.base.url")
                )
                webhook_url = base_url + PosStripeServerDrivenController._webhook_url
                webhook = provider._stripe_make_request(
                    "webhook_endpoints",
                    payload={
                        "url": webhook_url,
                        "enabled_events[]": [
                            "terminal.reader.action_succeeded",
                            "terminal.reader.action_failed",
                        ],
                        "api_version": stripe_const.API_VERSION,
                    },
                )
                error = webhook.get("error")
                secret = webhook.get("secret")
                if error or not secret:
                    _logger.error(
                        "Error creating Stripe webhook endpoint: %s",
                        error or webhook,
                    )
                    message = _(
                        "Stripe returned an error while creating the webhook."
                        " Please check your Stripe configuration and logs."
                    )
                    notification_type = "danger"
                else:
                    self.stripe_terminal_webhook_secret = secret
                    message = _("Your Stripe Webhook was successfully set up!")
                    notification_type = "info"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": message,
                "sticky": False,
                "type": notification_type,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_stripe_sd_provider_settings(self):
        self.ensure_one()
        res_id = self._get_stripe_payment_provider().id
        return {
            "name": _("Stripe"),
            "res_model": "payment.provider",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_id": res_id,
        }

    def stripe_sd_create_and_process_payment(self, amount):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Do not have access to process Stripe payments"))

        currency = self.journal_id.currency_id or self.company_id.currency_id
        provider = self.sudo()._get_stripe_payment_provider()

        # Create PaymentIntent
        params = [
            ("currency", currency.name.lower()),
            ("amount", self._stripe_calculate_amount(amount)),
            ("payment_method_types[]", "card_present"),
            ("capture_method", "manual"),
        ]

        # Regional handling
        if currency.name == "AUD" and self.company_id.country_code == "AU":
            params.append(
                (
                    "payment_method_options[card_present][capture_method]",
                    "manual_preferred",
                )
            )
        elif currency.name == "CAD" and self.company_id.country_code == "CA":
            params.append(("payment_method_types[]", "interac_present"))

        intent_result = provider._stripe_make_request("payment_intents", params)

        if intent_result.get("error"):
            raise UserError(
                intent_result["error"].get("message", _("Failed to create payment"))
            )

        payment_intent_id = intent_result["id"]

        # Hand off to reader
        if not self.stripe_reader_id:
            raise UserError(
                _(
                    "No Stripe reader is configured for this payment method. "
                    "Please select a reader before processing payments."
                )
            )
        quoted_reader = werkzeug.urls.url_quote(self.stripe_reader_id)
        reader_endpoint = f"terminal/readers/{quoted_reader}/process_payment_intent"
        process_result = provider._stripe_make_request(
            reader_endpoint,
            {"payment_intent": payment_intent_id},
        )

        if process_result.get("error"):
            # Cancel the intent if reader handoff fails
            quoted_id = werkzeug.urls.url_quote(payment_intent_id)
            cancel_endpoint = f"payment_intents/{quoted_id}/cancel"
            provider._stripe_make_request(cancel_endpoint)
            raise UserError(
                process_result["error"].get(
                    "message", _("Failed to process payment on reader")
                )
            )

        return {
            "payment_intent_id": payment_intent_id,
            "status": process_result.get("action", {}).get("status", "in_progress"),
        }

    def _extract_stripe_card_details(self, result):
        """Extract card brand and transaction ID from a Stripe PaymentIntent.

        Fetches the latest charge to get card_present details.

        :param result: A Stripe PaymentIntent response dict
        :return: dict with card_brand and transaction_id
        """
        card_brand = ""
        transaction_id = ""
        charges = result.get("latest_charge")
        if isinstance(charges, str):
            charge_result = (
                self.sudo()
                ._get_stripe_payment_provider()
                ._stripe_make_request(
                    f"charges/{werkzeug.urls.url_quote(charges)}",
                    method="GET",
                )
            )
            if not charge_result.get("error"):
                card_details = charge_result.get("payment_method_details", {}).get(
                    "card_present", {}
                )
                card_brand = card_details.get("brand", "")
                transaction_id = charge_result.get("id", "")
        return {"card_brand": card_brand, "transaction_id": transaction_id}

    def stripe_sd_check_payment_status(self, payment_intent_id):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Do not have access to check Stripe payment status"))

        quoted_id = werkzeug.urls.url_quote(payment_intent_id)
        endpoint = f"payment_intents/{quoted_id}"
        result = (
            self.sudo()
            ._get_stripe_payment_provider()
            ._stripe_make_request(endpoint, method="GET")
        )

        if result.get("error"):
            raise UserError(
                result["error"].get("message", _("Failed to check payment status"))
            )

        status = result.get("status", "unknown")
        card_details = (
            self._extract_stripe_card_details(result)
            if status == "requires_capture"
            else {"card_brand": "", "transaction_id": ""}
        )

        return {
            "status": status,
            **card_details,
        }

    def stripe_sd_capture_payment(self, payment_intent_id):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Do not have access to capture Stripe payments"))

        quoted_id = werkzeug.urls.url_quote(payment_intent_id)
        endpoint = f"payment_intents/{quoted_id}/capture"
        result = (
            self.sudo()._get_stripe_payment_provider()._stripe_make_request(endpoint)
        )

        if result.get("error"):
            raise UserError(
                result["error"].get("message", _("Failed to capture payment"))
            )

        return self._extract_stripe_card_details(result)

    def stripe_sd_void_authorized_payment(self, payment_intent_id):
        """Cancel an authorized PaymentIntent without cancelling the reader action.

        Used when a capture has failed and the user wants to discard the
        payment line, so only the intent needs to be voided.
        """
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Do not have access to void Stripe payments"))

        provider = self.sudo()._get_stripe_payment_provider()
        quoted_id = werkzeug.urls.url_quote(payment_intent_id)
        cancel_endpoint = f"payment_intents/{quoted_id}/cancel"
        result = provider._stripe_make_request(cancel_endpoint)

        if result.get("error"):
            if result["error"].get("code") != "payment_intent_unexpected_state":
                raise UserError(
                    result["error"].get("message", _("Failed to void payment"))
                )

        return True

    def stripe_sd_cancel_payment(self, payment_intent_id):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("Do not have access to cancel Stripe payments"))

        provider = self.sudo()._get_stripe_payment_provider()

        # Cancel the action on the reader
        if not self.stripe_reader_id:
            raise UserError(
                _("Stripe reader is not configured for this payment method.")
            )
        quoted_reader = werkzeug.urls.url_quote(self.stripe_reader_id)
        reader_endpoint = f"terminal/readers/{quoted_reader}/cancel_action"
        try:
            provider._stripe_make_request(reader_endpoint)
        except (UserError, ValidationError):
            _logger.warning(
                "Failed to cancel action on reader %s", self.stripe_reader_id
            )

        # Cancel the payment intent
        quoted_id = werkzeug.urls.url_quote(payment_intent_id)
        cancel_endpoint = f"payment_intents/{quoted_id}/cancel"
        result = provider._stripe_make_request(cancel_endpoint)

        if result.get("error"):
            # If already canceled, that's fine
            if result["error"].get("code") != "payment_intent_unexpected_state":
                raise UserError(
                    result["error"].get("message", _("Failed to cancel payment"))
                )

        return True
