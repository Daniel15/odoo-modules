# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models, tools


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @tools.ormcache()
    def get_currencies(self):
        currencies = super().get_currencies()
        records = self.env["res.currency"].browse(currencies)
        symbol_spacings = {record.id: record.symbol_spacing for record in records}
        return {
            currency_id: {
                **values,
                "symbol_spacing": symbol_spacings[currency_id],
            }
            for currency_id, values in currencies.items()
        }
