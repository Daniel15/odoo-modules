# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "WIP - Stripe Terminal Standalone",
    "summary": "Reconcile Stripe Terminal standalone payments with invoices",
    "version": "18.0.1.0.0",
    "category": "Accounting/Payment Providers",
    "depends": ["payment_stripe_terminal_base", "account_payment"],
    "data": [
        "security/stripe_terminal_standalone_security.xml",
        "security/ir.model.access.csv",
    ],
    "author": "Daniel Lo Nigro",
    "maintainers": ["Daniel15"],
    "website": "https://d.sb/odoo-modules",
    "license": "AGPL-3",
    "installable": True,
}
