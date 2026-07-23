# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        UPDATE payment_provider
           SET stripe_terminal_legacy_webhook_secret = stripe_terminal_webhook_secret
         WHERE code = 'stripe'
           AND stripe_terminal_webhook_endpoint_id IS NULL
           AND stripe_terminal_webhook_secret IS NOT NULL
           AND stripe_terminal_legacy_webhook_secret IS NULL
        """
    )

    old_view = env.ref(
        "pos_stripe_server_driven.payment_provider_view_form_stripe_sd",
        raise_if_not_found=False,
    )
    if old_view:
        old_view.unlink()
