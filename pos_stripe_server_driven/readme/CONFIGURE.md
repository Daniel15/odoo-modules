1. In **Invoicing > Payment Providers**, enable the Stripe payment provider.
   - Click the "Generate your Webhook" button next to **Terminal Webhook Secret** to configure a webhook for terminal events. This only needs to be done once, regardless of how many Stripe terminals you have.
2. In **Point of Sale > Configuration > Payment Methods**, add a Stripe payment method.
   - Integrate with: Select **Stripe (server-driven)**.
   - Stripe Reader ID: Select the correct terminal.
3. In **Point of Sale > Configuration > Settings**, select the relevant Point of Sale, then select the payment method.

Note: If you have multiple Stripe terminals, you will need to create a separate payment method for each one.
