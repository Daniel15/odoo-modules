# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import models


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    def _save_lines(self, question, answer, comment=None, overwrite_existing=True):
        if question.question_type == "text_content":
            return self.env["survey.user_input.line"]
        return super()._save_lines(question, answer, comment, overwrite_existing)
