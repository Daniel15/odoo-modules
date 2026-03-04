/* @odoo-module */

import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {patch} from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
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
                });
            return;
        }
        super.deletePaymentLine(uuid);
    },
});
