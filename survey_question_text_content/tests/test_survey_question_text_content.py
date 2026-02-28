# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from lxml import etree

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
    def test_form_view_hides_irrelevant_tabs_and_groups(self):
        """The form view hides Description tab and non-relevant Options groups
        for text_content questions, leaving only Conditional display visible."""
        arch = self.env["survey.question"].get_view(view_type="form")["arch"]
        tree = etree.fromstring(arch)

        # Description tab should be hidden for text_content
        description_page = tree.xpath("//page[@name='survey_description']")[0]
        self.assertIn("text_content", description_page.get("invisible", ""))

        # Options tab should still be visible (no text_content in invisible)
        options_page = tree.xpath("//page[@name='options']")[0]
        self.assertNotIn("text_content", options_page.get("invisible", ""))

        # Within Options, these groups should be hidden for text_content
        # Use field (direct child) not .//field (descendant) to avoid
        # matching the outer wrapper <group> which contains all inner groups.
        answers_group = tree.xpath(
            "//page[@name='options']//group[field[@name='validation_required']]"
        )[0]
        self.assertIn("text_content", answers_group.get("invisible", ""))

        constraints_group = tree.xpath(
            "//page[@name='options']//group[field[@name='constr_mandatory']]"
        )[0]
        self.assertIn("text_content", constraints_group.get("invisible", ""))

        live_sessions_group = tree.xpath(
            "//page[@name='options']//group[field[@name='session_available']]"
        )[0]
        self.assertIn("text_content", live_sessions_group.get("invisible", ""))

        # Conditional display group should NOT be hidden for text_content
        conditional_group = tree.xpath(
            "//page[@name='options']//group[field[@name='triggering_answer_ids']]"
        )[0]
        self.assertNotIn("text_content", conditional_group.get("invisible", ""))

    @users("survey_manager")
    def test_included_in_predefined_questions(self):
        """text_content questions are included in predefined questions so they
        appear in the survey flow."""
        predefined = self.survey._prepare_user_input_predefined_questions()
        self.assertIn(self.question_text_content, predefined)
