1. In **Invoicing > Payment Providers**, enable the Stripe payment provider.
2. In **Point of Sale > Configuration > Payment Methods**, add a Stripe payment method.
   - Integrate with: Select **Stripe (server-driven)**.
   - Stripe Reader ID: Select the correct terminal.
   - Click the "Generate your Webhook" button to configure a webhook.
3. In **Point of Sale > Configuration > Settings**, select the relevant Point of Sale, then select the payment method.

Note: If you have multiple Stripe terminals, you will need to create a separate payment method for each one.
