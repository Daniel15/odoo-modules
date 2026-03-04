/* @odoo-module */

import {AlertDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {PaymentInterface} from "@point_of_sale/app/payment/payment_interface";
import {_t} from "@web/core/l10n/translation";

export class PaymentStripeServerDriven extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.paymentLineResolvers = {};
    }

    pendingLine() {
        return this.pos.getPendingPaymentLine("stripe_server_driven");
    }

    // eslint-disable-next-line no-unused-vars
    async send_payment_request(uuid) {
        await super.send_payment_request(...arguments);
        const line = this.pos.get_order().get_selected_paymentline();

        // If capture previously failed, retry capture instead of creating a new intent
        if (line.stripe_capture_failed && line.stripe_payment_intent_id) {
            line.stripe_capture_failed = false;
            line.set_payment_status("waiting");
            const confirmationPromise = this._waitForPaymentConfirmation(line);
            await this._capturePayment(line);
            return await confirmationPromise;
        }

        line.set_payment_status("waiting");

        try {
            const result = await this.pos.data.silentCall(
                "pos.payment.method",
                "stripe_sd_create_and_process_payment",
                [[this.payment_method_id.id], line.amount]
            );

            if (result.error) {
                this._showError(result.error.data?.message || result.error.message);
                line.set_payment_status("retry");
                return false;
            }

            line.stripe_payment_intent_id = result.payment_intent_id;
            line.set_payment_status("waitingCard");

            // Wait for webhook notification or manual check
            return await this._waitForPaymentConfirmation(line);
        } catch (error) {
            console.error("Stripe server-driven payment error:", error);
            this._showError(error.data?.message || error.message || String(error));
            line.set_payment_status("retry");
            return false;
        }
    }

    _waitForPaymentConfirmation(line) {
        return new Promise((resolve) => {
            this.paymentLineResolvers[line.uuid] = resolve;
        });
    }

    async handlePaymentStatusNotification(data) {
        const line = this.pendingLine();
        if (!line) {
            return;
        }

        if (line.stripe_payment_intent_id !== data.payment_intent_id) {
            return;
        }

        if (data.status === "succeeded") {
            await this._capturePayment(line);
        } else {
            this._showError(
                data.failure_message || _t("Payment failed on the terminal.")
            );
            this._resolvePayment(line, false);
        }
    }

    async _capturePayment(line) {
        try {
            line.set_payment_status("waitingCapture");
            const result = await this.pos.data.silentCall(
                "pos.payment.method",
                "stripe_sd_capture_payment",
                [[this.payment_method_id.id], line.stripe_payment_intent_id]
            );

            if (result.error) {
                this._showError(result.error.data?.message || result.error.message);
                line.stripe_capture_failed = true;
                this._resolvePayment(line, false);
                return;
            }

            line.stripe_capture_failed = false;
            if (result.card_brand) {
                line.card_type = result.card_brand;
            }
            if (result.transaction_id) {
                line.transaction_id = result.transaction_id;
            }

            line.set_payment_status("done");
            this._resolvePayment(line, true);
        } catch (error) {
            console.error("Stripe capture error:", error);
            this._showError(
                error.data?.message || error.message || _t("Failed to capture payment")
            );
            line.stripe_capture_failed = true;
            this._resolvePayment(line, false);
        }
    }

    async checkPaymentStatus() {
        const line = this.pendingLine();
        if (!line || !line.stripe_payment_intent_id) {
            return;
        }

        try {
            const result = await this.pos.data.silentCall(
                "pos.payment.method",
                "stripe_sd_check_payment_status",
                [[this.payment_method_id.id], line.stripe_payment_intent_id]
            );

            if (result.error) {
                this._showError(result.error.data?.message || result.error.message);
                return;
            }

            if (result.status === "requires_capture") {
                await this._capturePayment(line);
            } else if (result.status === "canceled") {
                this._showError(_t("Payment was canceled."));
                this._resolvePayment(line, false);
            } else if (result.status === "requires_payment_method") {
                // Still waiting for the customer
                this._showError(
                    _t("Still waiting for payment on the terminal. Please try again.")
                );
            }
        } catch (error) {
            console.error("Stripe check status error:", error);
            this._showError(
                error.data?.message ||
                    error.message ||
                    _t("Failed to check payment status")
            );
        }
    }

    _resolvePayment(line, success) {
        const resolver = this.paymentLineResolvers[line.uuid];
        if (resolver) {
            delete this.paymentLineResolvers[line.uuid];
            resolver(success);
        } else {
            line.handle_payment_response(success);
        }
    }

    async send_payment_cancel(order, uuid) {
        await super.send_payment_cancel(...arguments);
        const line = order.payment_ids.find((pl) => pl.uuid === uuid);

        if (!line || !line.stripe_payment_intent_id) {
            return true;
        }

        try {
            // If capture failed, the reader is no longer active — just void the intent
            const rpcMethod = line.stripe_capture_failed
                ? "stripe_sd_void_authorized_payment"
                : "stripe_sd_cancel_payment";
            await this.pos.data.silentCall("pos.payment.method", rpcMethod, [
                [this.payment_method_id.id],
                line.stripe_payment_intent_id,
            ]);
            this._resolvePayment(line, false);
            line.set_payment_status("retry");
            return true;
        } catch (error) {
            console.error("Stripe cancel error:", error);
            this._showError(
                error.data?.message ||
                    error.message ||
                    _t(
                        "Failed to cancel payment. Please cancel manually on the terminal."
                    )
            );
            return false;
        }
    }

    _showError(msg, errorTitle) {
        const dialogTitle = errorTitle || _t("Stripe Error");
        this.env.services.dialog.add(AlertDialog, {
            title: dialogTitle,
            body: msg,
        });
    }
}
