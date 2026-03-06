import {PosStore} from "@point_of_sale/app/store/pos_store";
import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";
import {filterUnconfiguredStripeSD} from "@pos_stripe_server_driven/app/utils.esm";

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

        const {unconfiguredNames} = filterUnconfiguredStripeSD(
            this.config.payment_method_ids
        );
        if (unconfiguredNames.length > 0) {
            this.notification.add(
                _t(
                    "Stripe payment method '%s' is disabled because no reader is configured.",
                    unconfiguredNames.join("', '")
                ),
                {type: "warning"}
            );
        }
    },
});
