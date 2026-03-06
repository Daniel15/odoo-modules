## Payment flow

1. Cashier initiates payment in POS
2. Odoo server creates a PaymentIntent and hands it off to the reader via Stripe API
3. Customer taps/inserts card on reader
4. Stripe sends a webhook notification to Odoo, which notifies the POS frontend
5. Server captures the payment and POS shows success

Note: If you are a developer and want to work on this module, refer to [TESTING.md](./TESTING.md) for instructions on how to test it with a simulated Stripe reader.
