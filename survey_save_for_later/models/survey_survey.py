# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class Survey(models.Model):
    _inherit = "survey.survey"

    allow_save_for_later = fields.Boolean(
        string="Allow Save for Later",
        default=False,
        help="Allow users to save their survey progress and resume later. "
        "When enabled, a 'Save for Later' button will be shown alongside "
        "the Continue button during the survey.",
    )
