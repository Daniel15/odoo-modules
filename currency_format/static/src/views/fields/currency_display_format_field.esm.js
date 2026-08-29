import {
    SelectionField,
    selectionField,
} from "@web/views/fields/selection/selection_field";
import {formatCurrency} from "@web/core/currency";
import {registry} from "@web/core/registry";

function getPreviewAmount(rounding, decimalPlaces) {
    if (decimalPlaces === 0) {
        return 123;
    }
    const fraction = "45678901234567890".slice(0, decimalPlaces);
    const amount = Number(`123.${fraction}`);
    return Math.round(amount / rounding) * rounding;
}

export function getDisplayFormatPreview(
    symbol,
    displayFormat,
    rounding = 0.01,
    decimalPlaces = 2
) {
    const separatorIndex = displayFormat.indexOf("_");
    const position = displayFormat.slice(0, separatorIndex);
    const symbolSpacing = displayFormat.slice(separatorIndex + 1);
    return formatCurrency(getPreviewAmount(rounding, decimalPlaces), undefined, {
        currency: {
            digits: [69, decimalPlaces],
            position,
            symbol: symbol || "$",
            symbol_spacing: symbolSpacing,
        },
    });
}

export class CurrencyDisplayFormatField extends SelectionField {
    get options() {
        return super.options.map(([displayFormat]) => [
            displayFormat,
            getDisplayFormatPreview(
                this.props.record.data.symbol,
                displayFormat,
                this.props.record.data.rounding,
                this.props.record.data.decimal_places
            ),
        ]);
    }
}

export const currencyDisplayFormatField = {
    ...selectionField,
    component: CurrencyDisplayFormatField,
};

registry.category("fields").add("currency_display_format", currencyDisplayFormatField);
