This technical module provides reusable Stripe Terminal webhook, API, and payment
provider infrastructure. It is intended to be installed as a dependency of a complete
Stripe Terminal integration rather than used directly.

Do not uninstall this module while any Terminal consumer module (such as `pos_stripe_server_driven`) depends on it.

The Stripe provider form exposes actions to create and update a provider-bound Terminal
webhook.
