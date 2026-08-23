# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Stripe PaymentIntent Reconciliation",
    "summary": "Reconcile Stripe balance transactions with invoices",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "depends": [
        "account_statement_import_online_stripe",
        "account_reconcile_model_oca",
    ],
    "data": ["data/account_reconcile_model.xml"],
    "author": "Daniel Lo Nigro",
    "maintainers": ["Daniel15"],
    "website": "https://d.sb/odoo-modules",
    "license": "AGPL-3",
    "installable": True,
    "auto_install": True,
}
