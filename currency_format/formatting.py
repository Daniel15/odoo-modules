# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

NON_BREAKING_SPACE = "\N{NO-BREAK SPACE}"


def apply_symbol_spacing(formatted, currency):
    if getattr(currency, "symbol_spacing", "space") != "no_space":
        # Adding a space - use Odoo's standard formatting
        return formatted

    # If we get here, the no_space option is selected. Find the space that
    # Odoo's standard currency formatter added, and strip it out.
    if currency.position == "before":
        separator_index = formatted.find(NON_BREAKING_SPACE)
    else:
        separator_index = formatted.rfind(NON_BREAKING_SPACE)

    if separator_index == -1:
        return formatted
    return formatted[:separator_index] + formatted[separator_index + 1 :]
