# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

TERMINAL_WEBHOOK_EVENTS = [
    "terminal.reader.action_succeeded",
    "terminal.reader.action_failed",
]
TERMINAL_WEBHOOK_URL = "/payment/stripe/terminal/webhook"
WEBHOOK_AGE_TOLERANCE = 10 * 60  # seconds
