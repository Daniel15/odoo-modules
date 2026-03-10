# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    stripe_terminal_webhook_secret = fields.Char(
        help="Webhook signing secret for terminal events",
        groups="base.group_system",
        copy=False,
    )

    def action_stripe_sd_create_webhook(self):
        """Create a Stripe webhook for terminal events.

        :return: A feedback notification
        :rtype: dict
        """
        self.ensure_one()

        if self.stripe_terminal_webhook_secret:
            message = _("Your Stripe Webhook is already set up.")
            notification_type = "warning"
        elif not self.stripe_secret_key:
            message = _(
                "You cannot create a Stripe Webhook if your Stripe Secret"
                " Key is not set."
            )
            notification_type = "danger"
        else:
            from odoo.addons.payment_stripe import const as stripe_const

            from ..controllers.main import PosStripeServerDrivenController

            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            webhook_url = base_url + PosStripeServerDrivenController._webhook_url
            webhook = self._stripe_make_request(
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
