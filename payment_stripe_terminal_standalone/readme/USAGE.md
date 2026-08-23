1. Create and post a customer invoice in Odoo. Note its invoice number, for example
   `INV/2026/00010`.
2. On the Stripe Terminal reader, enter the invoice's full outstanding amount and enter
   the exact invoice number in **Internal note**. Do not add a tip.
3. Collect the payment. After Stripe confirms it, Odoo creates and posts the accounting
   payment and clears the invoice's outstanding balance.

The invoice must be posted and have an outstanding balance, and its currency and full
outstanding balance must match the Stripe payment. A missing or blank Internal note is
ignored; a payment that cannot be applied safely is retained for review rather than
partially posted.

Developers can refer to
[TESTING.md](https://github.com/Daniel15/odoo-modules/blob/18.0/payment_stripe_terminal_standalone/readme/TESTING.md)
for instructions on testing the module with a simulated Stripe reader.
