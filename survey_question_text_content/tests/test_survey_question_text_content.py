# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import users

from odoo.addons.survey.tests.common import TestSurveyCommon


class TestSurveyQuestionTextContent(TestSurveyCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.question_text_content = (
            cls.env["survey.question"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "Info Block",
                    "survey_id": cls.survey.id,
                    "sequence": 4,
                    "question_type": "text_content",
                    "content_html": "<p>Important information.</p>",
                }
            )
        )

    @users("survey_manager")
    def test_question_type_exists(self):
        """The text_content question type is available in the selection."""
        question_type_values = dict(
            self.env["survey.question"]._fields["question_type"].selection
        )
        self.assertIn("text_content", question_type_values)

    @users("survey_manager")
    def test_content_html_stored(self):
        """The content_html field stores rich text content."""
        self.assertIn(
            "Important information.",
            self.question_text_content.content_html,
        )

    @users("survey_manager")
    def test_validate_question_returns_no_errors(self):
        """Validation always passes for text_content questions."""
        # Even with constr_mandatory, validation should return no errors
        self.question_text_content.constr_mandatory = True
        result = self.question_text_content.validate_question("")
        self.assertEqual(result, {})

        result = self.question_text_content.validate_question(None)
        self.assertEqual(result, {})

    @users("survey_manager")
    def test_save_lines_skipped(self):
        """No answer lines are created for text_content questions."""
        user_input = self._add_answer(self.survey, self.customer)
        result = user_input._save_lines(self.question_text_content, "")
        self.assertFalse(result)
        answer_lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question_text_content
        )
        self.assertEqual(len(answer_lines), 0)

    @users("survey_manager")
    def test_is_not_page(self):
        """A text_content question is not treated as a page/section."""
        self.assertFalse(self.question_text_content.is_page)

    @users("survey_manager")
    def test_included_in_predefined_questions(self):
        """text_content questions are included in predefined questions so they
        appear in the survey flow."""
        predefined = self.survey._prepare_user_input_predefined_questions()
        self.assertIn(self.question_text_content, predefined)
