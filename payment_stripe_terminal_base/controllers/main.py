# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import json
import logging

from werkzeug.exceptions import BadRequest, Forbidden

from odoo import http
from odoo.http import request

from ..const import TERMINAL_WEBHOOK_URL

_logger = logging.getLogger(__name__)


class StripeTerminalController(http.Controller):
    _webhook_url = TERMINAL_WEBHOOK_URL

    @http.route(
        f"{_webhook_url}/<string:route_token>",
        type="http",
        methods=["POST"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def stripe_terminal_webhook(self, route_token):
        provider_sudo = (
            request.env["payment.provider"]
            .sudo()
            .search(
                [
                    ("code", "=", "stripe"),
                    ("stripe_terminal_webhook_route_token", "=", route_token),
                ],
                limit=2,
            )
        )
        if len(provider_sudo) != 1:
            _logger.warning("Rejected Stripe Terminal webhook for unknown route")
            raise Forbidden()

        raw_payload = request.httprequest.data
        signature_header = request.httprequest.headers.get("Stripe-Signature", "")
        provider_sudo._stripe_terminal_verify_webhook_signature(
            raw_payload, signature_header
        )

        try:
            event = json.loads(raw_payload)
        except (TypeError, ValueError, UnicodeDecodeError):
            raise BadRequest("Invalid JSON payload") from None
        if not isinstance(event, dict):
            raise BadRequest("Invalid JSON payload")

        if provider_sudo._stripe_terminal_validate_webhook_event(event):
            provider_sudo._stripe_terminal_dispatch_webhook_event(event)

        return request.make_response("", status=200)
