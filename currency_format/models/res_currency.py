# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    symbol_spacing = fields.Selection(
        selection=[
            ("space", "Space"),
            ("no_space", "No Space"),
        ],
        help="Determines whether a non-breaking space separates the currency symbol "
        "and amount.",
    )
    # UI-only field, to make the editing experience a bit friendlier.
    # Computed from the `symbol_spacing` and `position` fields.
    display_format = fields.Selection(
        selection=[
            ("before_no_space", "Before Amount, No Space"),
            ("before_space", "Before Amount, With Space"),
            ("after_no_space", "After Amount, No Space"),
            ("after_space", "After Amount, With Space"),
        ],
        compute="_compute_display_format",
        inverse="_inverse_display_format",
    )

    @api.depends("position", "symbol_spacing")
    def _compute_display_format(self):
        for currency in self:
            currency.display_format = (
                f"{currency.position}_{currency.symbol_spacing}"
                if currency.symbol_spacing
                else False
            )

    def _inverse_display_format(self):
        for currency in self:
            position, symbol_spacing = currency.display_format.split("_", 1)
            currency.write(
                {
                    "position": position,
                    "symbol_spacing": symbol_spacing,
                }
            )

    def write(self, values):
        result = super().write(values)
        if "symbol_spacing" in values:
            self.env.registry.clear_cache()
        return result
