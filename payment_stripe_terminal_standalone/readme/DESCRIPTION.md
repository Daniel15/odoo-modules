[Stripe Terminal standalone mode](https://docs.stripe.com/terminal/payments/standalone-mode)
lets businesses accept in-person payments on a compatible smart reader without building
or operating a point-of-sale system.

This module connects standalone payments to Odoo without initiating payments or
controlling the reader. Enter the invoice number of a posted customer invoice in the
reader's **Internal note** field. After Stripe reports a successful payment, the module
matches the note to the invoice and applies the payment through Odoo's standard payment
and accounting workflow.

**Supported readers:** Stripe Reader S700/S710 and Verifone V660p, as documented by
Stripe for standalone mode.

**Features:**

- Accept payments on Stripe terminals and use them to mark Odoo invoices as paid, without dealing with complex integrations.
- Processes validated, successful payments immediately through a webhook.

Partial payments, nonzero tips, refunds, and payments for more than one invoice are not
currently supported.
