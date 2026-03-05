# Testing pos_stripe_server_driven with a Simulated Reader

This guide describes how to manually test the module end-to-end using the Stripe CLI and
a simulated terminal reader, without needing real hardware.

## Prerequisites

- [Stripe CLI](https://docs.stripe.com/cli) installed and authenticated (`stripe login`)
- Odoo running locally on `http://localhost:8069`
- A Stripe account in **test mode** with the `payment_stripe` module configured
- The `pos_stripe_server_driven` module installed

## 1. Create a Terminal Location and Simulated Reader

Stripe requires a Location before you can create a reader.

```bash
# Create a location (only needed once)
stripe post /v1/terminal/locations \
  -d display_name="Test Store" \
  -d "address[line1]=123 Main St" \
  -d "address[city]=San Francisco" \
  -d "address[state]=CA" \
  -d "address[country]=US" \
  -d "address[postal_code]=94111"
```

Note the `id` from the response (e.g. `tml_xxx`), then create a simulated reader:

```bash
stripe post /v1/terminal/readers \
  -d registration_code=simulated-s710 \
  -d label="Simulated Reader 1" \
  -d location=tml_xxx
```

Note the reader `id` (e.g. `tmr_xxx`).

## 2. Start Webhook Forwarding

In a dedicated terminal, start the Stripe CLI webhook listener:

```bash
stripe listen \
  --events terminal.reader.action_succeeded,terminal.reader.action_failed \
  --forward-to http://localhost:8069/pos_stripe_server_driven/webhook
```

The CLI prints a webhook signing secret (`whsec_...`). Keep this for step 3.

> **Note:** The `terminal.reader.*` events must be explicitly listed — a wildcard
> subscription does not include them.

## 3. Configure Odoo

1. Go to **Point of Sale > Configuration > Payment Methods**
2. Create a new payment method with terminal type **Stripe (Server-driven)**
3. Select the simulated reader (`tmr_xxx`) from the **Stripe Reader** dropdown
4. Paste the `whsec_...` secret from step 2 into the **Webhook Signing Secret** field
5. Go to **Point of Sale > Configuration**, and assign the payment method to the
   relevant POS configuration

## 4. Test Scenarios

### 4a. Successful Payment

1. Open a POS session and add items to the order
2. Click **Payment** and select the Stripe payment method
3. Enter the amount and click **Send** — the POS should show "Waiting for card"
4. In another terminal, simulate a card tap:
   ```bash
   stripe post /v1/test_helpers/terminal/readers/tmr_xxx/present_payment_method
   ```
5. The webhook listener terminal should show the event being forwarded
6. The POS should update to "Capturing..." then show payment success
7. Verify the payment line shows a card brand and transaction ID

### 4b. Failed Payment (Declined Card)

1. Start a payment as in step 4a
2. Simulate a declined card:
   ```bash
   stripe post /v1/test_helpers/terminal/readers/tmr_xxx/present_payment_method \
     -d type=card_present \
     -d "card_present[number]=4000000000000002"
   ```
3. The POS should show an error dialog and the payment line should return to "retry"
   status

### 4c. Cancel Payment

1. Start a payment as in step 4a (POS shows "Waiting for card")
2. Click **Cancel** in the POS before simulating a card tap
3. Verify the POS returns to the payment screen and the payment line shows "retry"
   status

### 4d. Manual Status Check (Webhook Fallback)

This tests the "Check Status" button that appears when webhooks are delayed or not
working.

1. Stop the `stripe listen` process (to simulate webhook failure)
2. Start a payment and simulate a card tap as in step 4a
3. The POS will stay on "Waiting for card" since no webhook arrives
4. Click **Check Status** — the POS should poll Stripe directly and proceed to capture

### 4e. Capture Failure and Retry

1. Complete a payment up to the capture step (card tapped, webhook received)
2. Simulate a capture failure (e.g. by modifying the webhook secret to cause a Stripe
   error, or using network throttling)
3. The payment line should show "retry" status with capture failed
4. Clicking **Send** again should retry the capture without creating a new PaymentIntent
5. Deleting the payment line should void the authorized PaymentIntent on Stripe

## 5. Useful Debugging Commands

```bash
# Monitor all Stripe API requests in real time
stripe logs tail

# List readers to verify status
stripe get /v1/terminal/readers

# Check a specific PaymentIntent
stripe get /v1/payment_intents/pi_xxx

# Manually trigger a webhook event (for basic connectivity testing)
stripe trigger terminal.reader.action_succeeded

# Retrigger a webhook, in case an error was thrown and you want to retry
stripe events resend evt_xxxxxx
```

## 6. Automated Tests

The module includes automated unit tests that mock the Stripe API. Run them with:

```bash
docker compose run --rm odoo -- \
  -d odoo_test --test-enable --stop-after-init \
  -i pos_stripe_server_driven \
  --test-tags /pos_stripe_server_driven
```
