# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Stripe Terminal Base",
    "summary": "Provides reusable infrastructure for Stripe Terminal integrations",
    "version": "18.0.1.0.0",
    "category": "Accounting/Payment Providers",
    "depends": ["payment_stripe"],
    "data": [
        "views/payment_provider_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "author": "Daniel Lo Nigro",
    "maintainers": ["Daniel15"],
    "website": "https://d.sb/odoo-modules",
    "license": "AGPL-3",
    "installable": True,
}
