# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.http import request

from odoo.addons.payment_stripe_terminal_base.const import TERMINAL_WEBHOOK_EVENTS


class PosStripeServerDrivenController(http.Controller):
    _webhook_url = "/pos_stripe_server_driven/webhook"

    @http.route(
        _webhook_url,
        type="http",
        methods=["POST"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def stripe_terminal_webhook(self):
        providers_sudo = (
            request.env["payment.provider"]
            .sudo()
            ._stripe_terminal_find_legacy_webhook_providers(
                request.httprequest.data,
                request.httprequest.headers.get("Stripe-Signature", ""),
            )
        )
        try:
            event = request.get_json_data()
        except Exception:
            raise BadRequest("Invalid JSON payload") from None
        if not isinstance(event, dict):
            raise BadRequest("Invalid JSON payload")

        if event.get("type") not in TERMINAL_WEBHOOK_EVENTS:
            return request.make_response("", status=200)
        provider_sudo = providers_sudo._stripe_sd_resolve_legacy_webhook_provider(event)
        if not provider_sudo:
            return request.make_response("", status=200)
        if provider_sudo._stripe_terminal_validate_webhook_event(event):
            provider_sudo._stripe_terminal_dispatch_webhook_event(event)

        return request.make_response("", status=200)
