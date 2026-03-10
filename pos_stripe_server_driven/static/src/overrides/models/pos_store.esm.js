import {PosStore} from "@point_of_sale/app/store/pos_store";
import {_t} from "@web/core/l10n/translation";
import {filterUnconfiguredStripePaymentMethods} from "@pos_stripe_server_driven/app/utils.esm";
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

        const {unconfiguredNames} = filterUnconfiguredStripePaymentMethods(
            this.config.payment_method_ids
        );
        if (unconfiguredNames.length === 1) {
            this.notification.add(
                _t(
                    "Stripe payment method '%s' is disabled because no reader is configured.",
                    unconfiguredNames[0]
                ),
                {type: "warning"}
            );
        } else if (unconfiguredNames.length > 1) {
            this.notification.add(
                _t(
                    "Stripe payment methods %s are disabled because no reader is configured.",
                    unconfiguredNames.map((n) => `'${n}'`).join(", ")
                ),
                {type: "warning"}
            );
        }
    },
});
