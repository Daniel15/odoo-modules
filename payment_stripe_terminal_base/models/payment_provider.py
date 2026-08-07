# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging
import secrets

import werkzeug
from werkzeug.exceptions import Forbidden

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_stripe import const as stripe_const

from ..const import (
    TERMINAL_WEBHOOK_EVENTS,
    TERMINAL_WEBHOOK_URL,
    WEBHOOK_AGE_TOLERANCE,
)
from ..webhook_signature import WebhookSignatureError, verify_webhook_signature

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    stripe_terminal_webhook_secret = fields.Char(
        help=(
            "Webhook signing secret for Stripe Terminal events. For local testing, "
            "paste the secret printed by `stripe listen`."
        ),
        groups="base.group_system",
        copy=False,
    )
    stripe_terminal_webhook_endpoint_id = fields.Char(
        string="Stripe Terminal Webhook Endpoint ID",
        help=(
            "Stripe assigns this ID when the webhook is created through the API. It "
            "is not required when forwarding events with the Stripe CLI."
        ),
        groups="base.group_system",
        copy=False,
        readonly=True,
    )
    stripe_terminal_webhook_route_token = fields.Char(
        help="Random token that routes Terminal webhooks to this provider",
        groups="base.group_system",
        copy=False,
        readonly=True,
    )
    stripe_terminal_webhook_url = fields.Char(
        string="Stripe Terminal Webhook URL",
        compute="_compute_stripe_terminal_webhook_url",
        help="Provider-bound URL to use for this Stripe Terminal webhook.",
        groups="base.group_system",
    )

    _sql_constraints = [
        (
            "stripe_terminal_webhook_route_token_unique",
            "unique(stripe_terminal_webhook_route_token)",
            "The Stripe Terminal webhook route token must be unique.",
        ),
    ]

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            if values.get("code") == "stripe" and not values.get(
                "stripe_terminal_webhook_route_token"
            ):
                values["stripe_terminal_webhook_route_token"] = secrets.token_urlsafe(
                    32
                )
        return super().create(values_list)

    def _stripe_terminal_ensure_webhook_route_token(self):
        self.ensure_one()
        if not self.stripe_terminal_webhook_route_token:
            self.stripe_terminal_webhook_route_token = secrets.token_urlsafe(32)
        return self.stripe_terminal_webhook_route_token

    @api.depends("stripe_terminal_webhook_route_token")
    def _compute_stripe_terminal_webhook_url(self):
        for provider in self:
            route_token = provider.stripe_terminal_webhook_route_token
            provider.stripe_terminal_webhook_url = (
                route_token
                and werkzeug.urls.url_join(
                    provider.get_base_url(),
                    f"{TERMINAL_WEBHOOK_URL}/{werkzeug.urls.url_quote(route_token)}",
                )
            )

    def _stripe_terminal_get_webhook_url(self):
        self.ensure_one()
        route_token = werkzeug.urls.url_quote(
            self._stripe_terminal_ensure_webhook_route_token()
        )
        return werkzeug.urls.url_join(
            self.get_base_url(), f"{TERMINAL_WEBHOOK_URL}/{route_token}"
        )

    def _stripe_terminal_get_webhook_events(self):
        self.ensure_one()
        return list(TERMINAL_WEBHOOK_EVENTS)

    def _stripe_terminal_get_webhook_payload(self, include_api_version=False):
        self.ensure_one()
        payload = {
            "url": self._stripe_terminal_get_webhook_url(),
            "enabled_events[]": self._stripe_terminal_get_webhook_events(),
        }
        if include_api_version:
            payload["api_version"] = stripe_const.API_VERSION
        return payload

    def action_stripe_terminal_create_webhook(self):
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM payment_provider WHERE id = %s FOR UPDATE", [self.id]
        )
        self.invalidate_recordset(
            [
                "stripe_terminal_webhook_endpoint_id",
                "stripe_terminal_webhook_route_token",
                "stripe_terminal_webhook_secret",
            ]
        )
        if self.stripe_terminal_webhook_endpoint_id:
            return self._stripe_terminal_webhook_notification(
                _("Your Stripe Terminal webhook is already set up."), "warning"
            )
        if not self.stripe_secret_key:
            return self._stripe_terminal_webhook_notification(
                _(
                    "You cannot create a Stripe Terminal webhook if your Stripe "
                    "Secret Key is not set."
                ),
                "danger",
            )

        route_token = self._stripe_terminal_ensure_webhook_route_token()
        webhook = self._stripe_make_request(
            "webhook_endpoints",
            payload=self._stripe_terminal_get_webhook_payload(include_api_version=True),
            idempotency_key=f"odoo-terminal-webhook-{self.id}-{route_token}",
        )
        error = webhook.get("error")
        endpoint_id = webhook.get("id")
        secret = webhook.get("secret")
        if error or not endpoint_id or not secret:
            raise ValidationError(
                _(
                    "Stripe returned an invalid response while creating the Terminal "
                    "webhook: %s",
                    error or webhook,
                )
            )

        self.write(
            {
                "stripe_terminal_webhook_endpoint_id": endpoint_id,
                "stripe_terminal_webhook_secret": secret,
            }
        )
        return self._stripe_terminal_webhook_notification(
            _("Your Stripe Terminal webhook was successfully set up!"), "info"
        )

    def action_stripe_terminal_update_webhook(self):
        self.ensure_one()
        if not self.stripe_terminal_webhook_endpoint_id:
            return self._stripe_terminal_webhook_notification(
                _("Create the Stripe Terminal webhook before updating it."), "warning"
            )
        if not self.stripe_secret_key:
            return self._stripe_terminal_webhook_notification(
                _(
                    "You cannot update the Stripe Terminal webhook if your Stripe "
                    "Secret Key is not set."
                ),
                "danger",
            )

        endpoint_id = werkzeug.urls.url_quote(self.stripe_terminal_webhook_endpoint_id)
        webhook = self._stripe_make_request(
            f"webhook_endpoints/{endpoint_id}",
            payload=self._stripe_terminal_get_webhook_payload(),
        )
        if webhook.get("error"):
            raise ValidationError(
                _(
                    "Stripe returned an invalid response while updating the Terminal "
                    "webhook: %s",
                    webhook["error"],
                )
            )
        return self._stripe_terminal_webhook_notification(
            _("Your Stripe Terminal webhook was successfully updated!"), "info"
        )

    def _stripe_terminal_webhook_notification(self, message, notification_type):
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

    def _stripe_terminal_verify_webhook_signature(
        self, raw_payload, signature_header, webhook_secret=None
    ):
        self.ensure_one()
        webhook_secret = webhook_secret or self.stripe_terminal_webhook_secret
        try:
            return verify_webhook_signature(
                raw_payload,
                signature_header,
                webhook_secret,
                WEBHOOK_AGE_TOLERANCE,
            )
        except WebhookSignatureError as error:
            _logger.warning("Rejected Stripe Terminal webhook signature: %s", error)
            raise Forbidden() from None

    def _stripe_terminal_validate_webhook_event(self, event):
        self.ensure_one()
        if self.state not in ("enabled", "test"):
            _logger.warning(
                "Ignored Stripe Terminal event %s for disabled provider",
                event.get("id"),
            )
            return False
        if event.get("account"):
            _logger.warning(
                "Ignored Stripe Terminal Connect event %s; Connect is unsupported",
                event.get("id"),
            )
            return False

        expected_livemode = {"enabled": True, "test": False}.get(self.state)
        if (
            expected_livemode is not None
            and event.get("livemode") is not expected_livemode
        ):
            _logger.warning(
                "Ignored Stripe Terminal event %s due to provider mode mismatch",
                event.get("id"),
            )
            return False
        return True

    def _stripe_terminal_dispatch_webhook_event(self, event):
        self.ensure_one()
        _logger.info(
            "Stripe Terminal event received: type=%s id=%s",
            event.get("type"),
            event.get("id"),
        )
        return False

    def _stripe_terminal_retrieve_payment_intent(self, payment_intent_id):
        self.ensure_one()
        payment_intent_id = werkzeug.urls.url_quote(payment_intent_id)
        return self._stripe_make_request(
            f"payment_intents/{payment_intent_id}", method="GET"
        )

    def _stripe_terminal_retrieve_charge(self, charge_id):
        self.ensure_one()
        charge_id = werkzeug.urls.url_quote(charge_id)
        return self._stripe_make_request(f"charges/{charge_id}", method="GET")

    def _stripe_terminal_retrieve_refund(self, refund_id):
        self.ensure_one()
        refund_id = werkzeug.urls.url_quote(refund_id)
        return self._stripe_make_request(f"refunds/{refund_id}", method="GET")

    def _stripe_terminal_extract_card_present_details(self, payment_intent):
        self.ensure_one()
        latest_charge = payment_intent.get("latest_charge") or {}
        if isinstance(latest_charge, str):
            charge_id = latest_charge
            charge = self._stripe_terminal_retrieve_charge(charge_id)
        else:
            charge = latest_charge
            charge_id = charge.get("id", "")

        if not isinstance(charge, dict) or charge.get("error"):
            return {
                "charge_id": charge_id,
                "payment_method_type": "",
                "card_brand": "",
                "reader_id": "",
                "location_id": "",
            }

        payment_method_details = charge.get("payment_method_details", {})
        payment_method_type = payment_method_details.get("type", "")
        if payment_method_type not in ("card_present", "interac_present"):
            present_details = {}
        else:
            present_details = payment_method_details.get(payment_method_type, {})
        return {
            "charge_id": charge_id,
            "payment_method_type": payment_method_type,
            "card_brand": present_details.get("brand", ""),
            "reader_id": present_details.get("reader", ""),
            "location_id": present_details.get("location", ""),
        }

    def _stripe_terminal_to_minor_currency_units(self, amount, currency):
        self.ensure_one()
        return payment_utils.to_minor_currency_units(
            amount,
            currency,
            arbitrary_decimal_number=stripe_const.CURRENCY_DECIMALS.get(currency.name),
        )

    def _stripe_terminal_to_major_currency_units(self, amount, currency):
        self.ensure_one()
        return payment_utils.to_major_currency_units(
            amount,
            currency,
            arbitrary_decimal_number=stripe_const.CURRENCY_DECIMALS.get(currency.name),
        )
