# Testing payment_stripe_terminal_standalone with a Simulated Reader

This guide manually tests the logging-only standalone webhook flow with the Stripe CLI
and a simulated Terminal reader. It does not require physical reader hardware.

The simulated flow creates a card-present PaymentIntent through the Stripe API and sends
it to a simulated reader. This is not Stripe Standalone Mode itself, but it produces the
same `payment_intent.succeeded` event needed to test the module.

## Prerequisites

- [Stripe CLI](https://docs.stripe.com/cli) installed and authenticated with `stripe login`
- Odoo running locally on `http://localhost:8069`
- A Stripe account and Odoo Stripe provider configured in test mode
- The `payment_stripe_terminal_standalone` module installed

## 1. Create a Terminal Location and Simulated Reader

Stripe requires a Location before a reader can be created.

```bash
stripe post /v1/terminal/locations \
  -d display_name="Standalone Test Location" \
  -d "address[line1]=123 Main St" \
  -d "address[city]=San Francisco" \
  -d "address[state]=CA" \
  -d "address[country]=US" \
  -d "address[postal_code]=94111"
```

Note the Location `id` from the response, such as `tml_xxx`, and create a simulated
reader:

```bash
stripe post /v1/terminal/readers \
  -d registration_code=simulated-s710 \
  -d label="Standalone Simulated Reader" \
  -d location=tml_xxx
```

Note the reader `id`, such as `tmr_xxx`.

## 2. Start Webhook Forwarding

In **Invoicing > Configuration > Payment Providers**, open the test Stripe provider and
copy its **Stripe Terminal Webhook URL**.

In a dedicated terminal, start the Stripe CLI listener:

```bash
stripe listen \
  --events payment_intent.succeeded,terminal.reader.action_succeeded,terminal.reader.action_failed \
  --forward-to <stripe-terminal-webhook-url>
```

The CLI prints a webhook signing secret beginning with `whsec_`. Keep the listener
running and use that secret in the next step.

## 3. Configure Odoo

1. Open the test Stripe provider in **Invoicing > Configuration > Payment Providers**.
2. Paste the `whsec_...` value into **Terminal Webhook Secret**.
3. Leave **Stripe Terminal Webhook Endpoint ID** empty. Stripe CLI forwarding does not
   create an endpoint.
4. Confirm that the provider is in **Test Mode**.

When testing with a real Stripe webhook endpoint instead of `stripe listen`, click
**Update Terminal Webhook** after installing this module. Its enabled events must include
`payment_intent.succeeded`.

## 4. Test a Note-Bearing Payment

Create a PaymentIntent that explicitly sets `x_terminal_standalone_note`. Replace the
sample value with the exact invoice number you want represented in the audit record.

```bash
stripe post /v1/payment_intents \
  -d amount=1250 \
  -d currency=usd \
  -d "payment_method_types[]=card_present" \
  -d capture_method=automatic \
  -d "metadata[x_terminal_standalone_note]=INV/2026/0042"
```

The `metadata[x_terminal_standalone_note]` argument is required for this test. Note the
returned PaymentIntent `id`, such as `pi_xxx`, then send it to the simulated reader:

```bash
stripe post /v1/terminal/readers/tmr_xxx/process_payment_intent \
  -d payment_intent=pi_xxx
```

Simulate presenting a successful test card:

```bash
stripe post /v1/test_helpers/terminal/readers/tmr_xxx/present_payment_method
```

The listener should forward `payment_intent.succeeded` and Odoo should log a message
similar to:

```text
Logged Stripe Terminal standalone candidate pi_xxx with invoice note INV/2026/0042 ...
```

## 5. Verify the Audit Record

Open an Odoo shell:

```bash
docker compose run --rm odoo shell --db-filter="^odoo_test$" -d odoo_test
```

Query the PaymentIntent ID returned in step 4:

```python
audit = env["stripe.terminal.standalone.payment"].search(
    [("payment_intent_id", "=", "pi_xxx")]
)
audit.read(
    [
        "event_id",
        "payment_intent_id",
        "internal_note",
        "amount_minor",
        "amount",
        "currency_id",
        "state",
        "invoice_id",
        "payment_transaction_id",
    ]
)
```

Verify:

- Exactly one record exists.
- `internal_note` is `INV/2026/0042`.
- `state` is `logged`.
- `amount_minor` is `1250` and the currency is USD.
- `invoice_id` and `payment_transaction_id` are empty.
- No `account.payment` was created for this event.

## 6. Verify Missing-Note Events Are Ignored

Repeat the flow with a new PaymentIntent, but omit the metadata argument:

```bash
stripe post /v1/payment_intents \
  -d amount=1250 \
  -d currency=usd \
  -d "payment_method_types[]=card_present" \
  -d capture_method=automatic
```

Process the new `pi_xxx` on the simulated reader and present a payment method as in step
4. The webhook must return HTTP 200, but this query must return no records:

```python
env["stripe.terminal.standalone.payment"].search(
    [("payment_intent_id", "=", "pi_xxx")]
)
```

Empty and whitespace-only `x_terminal_standalone_note` values are ignored in the same
way.

## 7. Verify Duplicate Delivery

Find the event ID in the Stripe listener output or with `stripe events list`, then resend
it:

```bash
stripe events resend evt_xxx
```

The resend should return HTTP 200 and the PaymentIntent should still have exactly one
audit record.

## 8. Automated Tests

```bash
docker compose run --rm odoo -- \
  --stop-after-init \
  --db-filter="^odoo_test$" \
  -d odoo_test \
  -i payment_stripe_terminal_standalone \
  --test-enable \
  --test-tags /payment_stripe_terminal_standalone \
  --log-level=test
```

Use `-u payment_stripe_terminal_standalone` instead of
`-i payment_stripe_terminal_standalone` when the module is already installed.
