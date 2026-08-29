import {beforeEach, describe, expect, test} from "@odoo/hoot";
import {currencies, formatCurrency} from "@web/core/currency";
import {makeMockEnv, patchWithCleanup} from "@web/../tests/web_test_helpers";
import {getDisplayFormatPreview} from "@currency_format/views/fields/currency_display_format_field.esm";

describe.current.tags("headless");

beforeEach(async () => {
    await makeMockEnv();
    patchWithCleanup(currencies, {
        901: {
            digits: [69, 2],
            position: "before",
            symbol: "$",
            symbol_spacing: "no_space",
        },
        902: {
            digits: [69, 2],
            position: "before",
            symbol: "$",
            symbol_spacing: "space",
        },
        903: {
            digits: [69, 2],
            position: "after",
            symbol: "$",
            symbol_spacing: "no_space",
        },
        904: {
            digits: [69, 2],
            position: "after",
            symbol: "$",
            symbol_spacing: "space",
        },
    });
});

test("formats all symbol position and spacing combinations", () => {
    expect(formatCurrency(1.23, 901)).toBe("$1.23");
    expect(formatCurrency(1.23, 902)).toBe("$\u00a01.23");
    expect(formatCurrency(1.23, 903)).toBe("1.23$");
    expect(formatCurrency(1.23, 904)).toBe("1.23\u00a0$");
});

test("defaults to a space for currency data without symbol_spacing", () => {
    patchWithCleanup(currencies, {
        905: {
            digits: [69, 2],
            position: "before",
            symbol: "$",
        },
    });

    expect(formatCurrency(1.23, 905)).toBe("$\u00a01.23");
});

test("formats display options with the currency being edited", () => {
    expect(getDisplayFormatPreview("€", "before_no_space")).toBe("€123.45");
    expect(getDisplayFormatPreview("€", "before_space")).toBe("€\u00a0123.45");
    expect(getDisplayFormatPreview("€", "after_no_space")).toBe("123.45€");
    expect(getDisplayFormatPreview("€", "after_space")).toBe("123.45\u00a0€");
});

test("uses the currency rounding and decimal places in display options", () => {
    expect(getDisplayFormatPreview("¥", "before_no_space", 1, 0)).toBe("¥123");
    expect(getDisplayFormatPreview("¥", "before_no_space", 5, 0)).toBe("¥125");
    expect(getDisplayFormatPreview("$", "before_no_space", 0.1, 1)).toBe("$123.4");
    expect(getDisplayFormatPreview("$", "before_no_space", 0.05, 2)).toBe("$123.45");
    expect(getDisplayFormatPreview("د.ك", "after_space", 0.001, 3)).toBe(
        "123.456\u00a0د.ك"
    );
});
