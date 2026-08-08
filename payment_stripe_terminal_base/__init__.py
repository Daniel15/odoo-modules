import secrets

from . import controllers
from . import models


def post_init_hook(env):
    providers = env["payment.provider"].search(
        [("code", "=", "stripe"), ("stripe_terminal_webhook_route_token", "=", False)]
    )
    for provider in providers:
        provider.stripe_terminal_webhook_route_token = secrets.token_urlsafe(32)
