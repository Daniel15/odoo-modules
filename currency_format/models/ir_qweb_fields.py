# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, models

from ..formatting import apply_symbol_spacing


class MonetaryConverter(models.AbstractModel):
    _inherit = "ir.qweb.field.monetary"

    @api.model
    def value_to_html(self, value, options):
        formatted = super().value_to_html(value, options)
        return apply_symbol_spacing(formatted, options["display_currency"])
