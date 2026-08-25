1. Create and post a customer invoice in Odoo. Note its invoice number, for example
   `INV/2026/00010`.
2. On the Stripe Terminal reader, enter the amount to charge the customer. This can be
   either the full amount, or a smaller amount if you want to split the payment across
   multiple cards. Do not add a tip.
3. In the **Internal Note** field, enter the exact invoice number.
4. Collect the payment. After Stripe confirms it, Odoo creates and posts the accounting
   payment and applies it to the invoice.
5. If a balance remains, repeat with another card until the invoice is fully paid.

Each payment has a separate Stripe PaymentIntent, Odoo payment transaction, and accounting
payment, all associated with the same invoice. The invoice must be posted and
have an outstanding balance, and its currency must match the Stripe payment. Payments
above the outstanding balance are retained for review. A missing or blank Internal note
is ignored; a payment that cannot be applied safely is retained for review rather than
posted.

Developers can refer to
[TESTING.md](https://github.com/Daniel15/odoo-modules/blob/18.0/payment_stripe_terminal_standalone/readme/TESTING.md)
for instructions on testing the module with a simulated Stripe reader.
