# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class SurveyQuestion(models.Model):
    _inherit = "survey.question"

    question_type = fields.Selection(
        selection_add=[("text_content", "Text Content")],
        ondelete={"text_content": "set null"},
    )
    content_html = fields.Html(
        "Content",
        translate=True,
        sanitize=True,
        sanitize_overridable=True,
    )

    def validate_question(self, answer, comment=None):
        if self.question_type == "text_content":
            return {}
        return super().validate_question(answer, comment)
