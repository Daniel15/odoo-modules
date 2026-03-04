This module integrates the Odoo Point of Sale with Stripe Terminal using the **server-driven** integration. Unlike the built-in `pos_stripe` module which uses Stripe's JavaScript Terminal SDK (requiring the card reader to be on the same LAN as the browser), this module communicates with the reader through Stripe's server-to-server API.

This means the terminal reader can be on any network — it only needs an internet connection to communicate with Stripe's servers. This is especially useful with the Stripe Reader S710 and Verifone V660p terminals, as these have cellular connectivity.

**Supported hardware:** Stripe Terminal readers that support the server-driven integration. This includes the WisePOS E, Stripe Reader S700/S710, and Verifone smart readers.

**Payment flow:**

1. Cashier initiates payment in POS
2. Odoo server creates a PaymentIntent and hands it off to the reader via Stripe API
3. Customer taps/inserts card on reader
4. Stripe sends a webhook notification to Odoo, which notifies the POS frontend
5. Server captures the payment and POS shows success

**Features:**

- No LAN requirement between POS and card reader
- Webhook-based real-time payment status updates
- Manual "Check Status" fallback if webhooks fail
- Card brand and transaction ID displayed on payment
- Supports regional payment methods (eftpos in Australia, Interac in Canada)
