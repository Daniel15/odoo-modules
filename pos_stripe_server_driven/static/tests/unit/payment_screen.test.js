import {describe, expect, test} from "@odoo/hoot";
import {filterUnconfiguredStripeSD} from "@pos_stripe_server_driven/app/utils.esm";

describe("filterUnconfiguredStripeSD", () => {
    test("keeps non-Stripe payment methods unchanged", () => {
        const methods = [
            {name: "Cash", use_payment_terminal: false, stripe_reader_id: false},
            {name: "Bank", use_payment_terminal: "adyen", stripe_reader_id: false},
        ];
        const {configured, unconfiguredNames} = filterUnconfiguredStripeSD(methods);
        expect(configured).toHaveLength(2);
        expect(unconfiguredNames).toHaveLength(0);
    });

    test("keeps Stripe SD methods with a reader configured", () => {
        const methods = [
            {
                name: "Stripe Terminal",
                use_payment_terminal: "stripe_server_driven",
                stripe_reader_id: "tmr_abc123",
            },
        ];
        const {configured, unconfiguredNames} = filterUnconfiguredStripeSD(methods);
        expect(configured).toHaveLength(1);
        expect(configured[0].name).toBe("Stripe Terminal");
        expect(unconfiguredNames).toHaveLength(0);
    });

    test("filters out Stripe SD methods without a reader", () => {
        const methods = [
            {
                name: "Stripe No Reader",
                use_payment_terminal: "stripe_server_driven",
                stripe_reader_id: false,
            },
        ];
        const {configured, unconfiguredNames} = filterUnconfiguredStripeSD(methods);
        expect(configured).toHaveLength(0);
        expect(unconfiguredNames).toEqual(["Stripe No Reader"]);
    });

    test("filters mixed payment methods correctly", () => {
        const methods = [
            {name: "Cash", use_payment_terminal: false, stripe_reader_id: false},
            {
                name: "Stripe With Reader",
                use_payment_terminal: "stripe_server_driven",
                stripe_reader_id: "tmr_abc123",
            },
            {
                name: "Stripe No Reader",
                use_payment_terminal: "stripe_server_driven",
                stripe_reader_id: false,
            },
            {name: "Bank", use_payment_terminal: "adyen", stripe_reader_id: false},
        ];
        const {configured, unconfiguredNames} = filterUnconfiguredStripeSD(methods);
        expect(configured).toHaveLength(3);
        expect(configured.map((m) => m.name)).toEqual([
            "Cash",
            "Stripe With Reader",
            "Bank",
        ]);
        expect(unconfiguredNames).toEqual(["Stripe No Reader"]);
    });

    test("reports multiple unconfigured methods", () => {
        const methods = [
            {
                name: "Terminal A",
                use_payment_terminal: "stripe_server_driven",
                stripe_reader_id: false,
            },
            {
                name: "Terminal B",
                use_payment_terminal: "stripe_server_driven",
                stripe_reader_id: false,
            },
        ];
        const {configured, unconfiguredNames} = filterUnconfiguredStripeSD(methods);
        expect(configured).toHaveLength(0);
        expect(unconfiguredNames).toEqual(["Terminal A", "Terminal B"]);
    });

    test("handles empty input", () => {
        const {configured, unconfiguredNames} = filterUnconfiguredStripeSD([]);
        expect(configured).toHaveLength(0);
        expect(unconfiguredNames).toHaveLength(0);
    });
});
