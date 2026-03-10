import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {filterUnconfiguredStripePaymentMethods} from "@pos_stripe_server_driven/app/utils.esm";
import {patch} from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        const {configured} = filterUnconfiguredStripePaymentMethods(
            this.payment_methods_from_config
        );
        this.payment_methods_from_config = configured;
    },

    deletePaymentLine(uuid) {
        const line = this.paymentLines.find((pl) => pl.uuid === uuid);
        if (
            line?.stripe_capture_failed &&
            line.get_payment_status() === "retry" &&
            line.payment_method_id.payment_terminal
        ) {
            line.set_payment_status("waitingCancel");
            line.payment_method_id.payment_terminal
                .send_payment_cancel(this.currentOrder, uuid)
                .then(() => {
                    this.currentOrder.remove_paymentline(line);
                    this.numberBuffer.reset();
                })
                .catch((error) => {
                    console.error("Failed to cancel Stripe payment:", error);
                    if (line) {
                        line.set_payment_status("retry");
                    }
                });
            return;
        }
        super.deletePaymentLine(uuid);
    },
});
