/* @odoo-module */

import {PaymentStripeServerDriven} from "@pos_stripe_server_driven/app/payment_stripe_server_driven";
import {register_payment_method} from "@point_of_sale/app/store/pos_store";

register_payment_method("stripe_server_driven", PaymentStripeServerDriven);
