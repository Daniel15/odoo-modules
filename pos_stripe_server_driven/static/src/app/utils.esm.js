/**
 * Filter out Stripe server-driven payment methods that have no reader configured.
 *
 * @param {Array} paymentMethods - list of payment method records
 * @returns {{configured: Array, unconfiguredNames: string[]}}
 */
export function filterUnconfiguredStripePaymentMethods(paymentMethods) {
    const configured = [];
    const unconfiguredNames = [];
    for (const pm of paymentMethods) {
        if (
            pm.use_payment_terminal === "stripe_server_driven" &&
            !pm.stripe_reader_id
        ) {
            unconfiguredNames.push(pm.name);
        } else {
            configured.push(pm);
        }
    }
    return {configured, unconfiguredNames};
}
