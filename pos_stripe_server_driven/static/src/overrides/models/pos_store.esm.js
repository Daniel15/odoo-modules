/* @odoo-module */

import {PosStore} from "@point_of_sale/app/store/pos_store";
import {patch} from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("STRIPE_SD_PAYMENT_STATUS", (data) => {
            const pendingLine = this.getPendingPaymentLine("stripe_server_driven");
            if (pendingLine) {
                pendingLine.payment_method_id.payment_terminal.handlePaymentStatusNotification(
                    data
                );
            }
        });
    },
});
