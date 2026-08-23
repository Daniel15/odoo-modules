This module creates a reconciliation model to automatically reconcile Stripe balance transactions (synced by `account_statement_import_online_stripe`) with invoices.

It is a glue module between `account_statement_import_online_stripe` and `account_reconcile_model_oca`, and requires both of those modules to be installed.
