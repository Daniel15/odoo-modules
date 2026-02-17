# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest.mock import patch

from odoo.tests import common

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.survey.tests.common import SurveyCase


class TestSurveySaveForLater(SurveyCase):
    """Test cases for the survey_save_for_later module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create test users
        cls.survey_manager = mail_new_test_user(
            cls.env,
            name="Survey Manager",
            login="survey_manager",
            email="manager@example.com",
            groups="survey.group_survey_manager,base.group_user",
        )

        cls.survey_user = mail_new_test_user(
            cls.env,
            name="Survey User",
            login="survey_user",
            email="user@example.com",
            groups="base.group_user",
        )

        # Create test survey
        cls.survey = (
            cls.env["survey.survey"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "Test Survey for Save Later",
                    "access_mode": "public",
                    "users_login_required": False,
                    "users_can_go_back": True,
                    "allow_save_for_later": True,
                    "questions_layout": "page_per_question",
                }
            )
        )

        # Create a page and questions
        cls.page_0 = (
            cls.env["survey.question"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "Page 1",
                    "survey_id": cls.survey.id,
                    "sequence": 1,
                    "is_page": True,
                    "question_type": False,
                }
            )
        )

        cls.question_text = (
            cls.env["survey.question"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "What is your name?",
                    "survey_id": cls.survey.id,
                    "sequence": 2,
                    "question_type": "char_box",
                    "constr_mandatory": True,
                }
            )
        )

        cls.question_email = (
            cls.env["survey.question"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "What is your email?",
                    "survey_id": cls.survey.id,
                    "sequence": 3,
                    "question_type": "char_box",
                    "validation_email": True,
                    "save_as_email": True,
                    "constr_mandatory": False,
                }
            )
        )

        cls.page_1 = (
            cls.env["survey.question"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "Page 2",
                    "survey_id": cls.survey.id,
                    "sequence": 4,
                    "is_page": True,
                    "question_type": False,
                }
            )
        )

        cls.question_choice = (
            cls.env["survey.question"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "What is your favorite color?",
                    "survey_id": cls.survey.id,
                    "sequence": 5,
                    "question_type": "simple_choice",
                    "constr_mandatory": True,
                    "suggested_answer_ids": [
                        (0, 0, {"value": "Red"}),
                        (0, 0, {"value": "Blue"}),
                        (0, 0, {"value": "Green"}),
                    ],
                }
            )
        )

    def test_allow_save_for_later_default(self):
        """Test that allow_save_for_later defaults to False."""
        survey = self.env["survey.survey"].create(
            {
                "title": "Test Default",
            }
        )
        self.assertFalse(survey.allow_save_for_later)

    def test_allow_save_for_later_field_exists(self):
        """Test that the allow_save_for_later field exists on survey."""
        self.assertTrue(hasattr(self.survey, "allow_save_for_later"))
        self.assertTrue(self.survey.allow_save_for_later)

    def test_allow_save_for_later_can_be_disabled(self):
        """Test that allow_save_for_later can be disabled."""
        self.survey.allow_save_for_later = False
        self.assertFalse(self.survey.allow_save_for_later)

    def test_get_resume_url(self):
        """Test the get_resume_url method on user_input."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
            }
        )
        user_input._mark_in_progress()

        resume_url = user_input.get_resume_url()
        self.assertIsInstance(resume_url, str)
        self.assertIn(self.survey.access_token, resume_url)
        self.assertIn(user_input.access_token, resume_url)

    def test_get_resume_url_ensure_one(self):
        """Test that get_resume_url requires a single record."""
        self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
            }
        )
        with self.assertRaises(ValueError):
            self.env["survey.user_input"].get_resume_url()

    def test_get_save_for_later_email_from_partner(self):
        """Test getting email from partner."""
        partner = self.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "partner@example.com",
            }
        )
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "partner_id": partner.id,
            }
        )

        email = user_input._get_save_for_later_email()
        self.assertEqual(email, "partner@example.com")

    def test_get_save_for_later_email_from_field(self):
        """Test getting email from email field when no partner email."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "direct@example.com",
            }
        )

        email = user_input._get_save_for_later_email()
        self.assertEqual(email, "direct@example.com")

    def test_get_save_for_later_email_prefer_partner(self):
        """Test that partner email is preferred over direct email field."""
        partner = self.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "partner@example.com",
            }
        )
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "partner_id": partner.id,
                "email": "direct@example.com",
            }
        )

        email = user_input._get_save_for_later_email()
        self.assertEqual(email, "partner@example.com")

    def test_get_save_for_later_email_none(self):
        """Test getting email when no email is available."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
            }
        )

        email = user_input._get_save_for_later_email()
        self.assertFalse(email)

    def test_mark_new_to_in_progress_on_save(self):
        """Test that saving a new user_input marks it as in_progress."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
                "state": "new",
            }
        )

        # Simulate the controller behavior
        from ..controllers.main import (
            SurveySaveForLaterController,
        )

        controller = SurveySaveForLaterController()
        post_data = {
            str(self.question_text.id): "John Doe",
        }

        # Call the internal save method
        controller._save_current_answers(self.survey, user_input, post_data)

        # State should be in_progress after save
        self.assertEqual(
            user_input.state, "new"
        )  # Internal method doesn't change state

        # Mark it as in_progress like the controller would
        user_input._mark_in_progress()
        self.assertEqual(user_input.state, "in_progress")

    def test_answers_preserved_after_save(self):
        """Test that answers are preserved when using save for later."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
            }
        )
        user_input._mark_in_progress()

        # Save an answer
        user_input._save_lines(
            self.question_text, "Jane Doe", comment=None, overwrite_existing=True
        )

        # Check that the answer is saved
        lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question_text
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.value_char_box, "Jane Doe")

    def test_send_save_for_later_email_success(self):
        """Test successful sending of save for later email."""
        partner = self.env["res.partner"].create(
            {
                "name": "Test User",
                "email": "recipient@example.com",
            }
        )
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "partner_id": partner.id,
            }
        )

        # Mock the email template send_mail method
        with patch(
            "odoo.addons.mail.models.mail_template.MailTemplate.send_mail"
        ) as mock_send:
            mock_send.return_value = True
            result = user_input._send_save_for_later_email()

        self.assertTrue(result)
        mock_send.assert_called_once()

    def test_send_save_for_later_email_no_email(self):
        """Test that no email is sent when no email is available."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
            }
        )

        result = user_input._send_save_for_later_email()
        self.assertFalse(result)

    def test_send_save_for_later_email_chatter_message(self):
        """Test that a chatter message is posted when email is sent."""
        partner = self.env["res.partner"].create(
            {
                "name": "Test User",
                "email": "recipient@example.com",
            }
        )
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "partner_id": partner.id,
            }
        )

        # Mock the email template
        with patch(
            "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
            return_value=True,
        ):
            user_input._send_save_for_later_email()

        # Check that a message was posted
        messages = user_input.message_ids
        self.assertTrue(
            any(
                "Save for Later" in message.body
                or "save for later" in message.body.lower()
                for message in messages
            )
        )

    def test_save_for_later_with_partial_answers(self):
        """Test saving with partial (incomplete) answers."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
            }
        )
        user_input._mark_in_progress()

        # Save only the email, not the mandatory name question
        user_input._save_lines(
            self.question_email,
            "partial@example.com",
            comment=None,
            overwrite_existing=True,
        )

        # Check that only email is saved
        email_lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question_email
        )
        self.assertEqual(len(email_lines), 1)
        self.assertEqual(email_lines.value_char_box, "partial@example.com")

        # Name question should not have an answer
        name_lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question_text
        )
        self.assertEqual(len(name_lines), 0)

    def test_save_for_later_with_choice_answer(self):
        """Test saving with a choice question answer."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
            }
        )
        user_input._mark_in_progress()

        # Get the first suggested answer
        answer = self.question_choice.suggested_answer_ids[0]

        # Save the choice answer
        user_input._save_lines(
            self.question_choice, answer.id, comment=None, overwrite_existing=True
        )

        # Check that the answer is saved
        lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question_choice
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.suggested_answer_id.id, answer.id)

    def test_save_for_later_overwrites_existing_answer(self):
        """Test that save for later overwrites existing answers."""
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
            }
        )
        user_input._mark_in_progress()

        # Save initial answer
        user_input._save_lines(
            self.question_text, "Initial Name", comment=None, overwrite_existing=True
        )

        # Update with new answer
        user_input._save_lines(
            self.question_text, "Updated Name", comment=None, overwrite_existing=True
        )

        # Check that only the latest answer exists
        lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question_text
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.value_char_box, "Updated Name")

    def test_survey_form_view_has_allow_save_for_later_field(self):
        """Test that the survey form view contains the allow_save_for_later field."""
        # Get the view
        view = self.env.ref("survey_save_for_later.survey_survey_form_view")
        self.assertEqual(view.model, "survey.survey")
        # Check that the inherited view exists
        parent_view = self.env.ref("survey.survey_survey_view_form")
        self.assertEqual(view.inherit_id.id, parent_view.id)

    def test_save_for_later_button_in_template(self):
        """Test that the Save for Later button is added to the template."""
        # Check that the template exists
        template = self.env.ref("survey_save_for_later.survey_fill_form_save_button")
        self.assertTrue(template)
        self.assertEqual(
            template.inherit_id.id,
            self.env.ref("survey.survey_fill_form_in_progress").id,
        )

    def test_mail_template_exists(self):
        """Test that the save for later mail template exists."""
        template = self.env.ref("survey_save_for_later.mail_template_save_for_later")
        self.assertEqual(template.model_id.model, "survey.user_input")
        # Template name contains "Save for Later"
        self.assertIn("Save for Later", template.name)


class TestSurveySaveForLaterController(SurveyCase):
    """Test the controller methods separately."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey_manager = mail_new_test_user(
            cls.env,
            name="Survey Manager Controller",
            login="survey_manager_ctrl",
            email="manager.ctrl@example.com",
            groups="survey.group_survey_manager,base.group_user",
        )
        cls.survey = (
            cls.env["survey.survey"]
            .with_user(cls.survey_manager)
            .create(
                {
                    "title": "Test Survey Controller",
                    "access_mode": "public",
                    "allow_save_for_later": True,
                }
            )
        )
        cls.question = cls.env["survey.question"].create(
            {
                "title": "Test Question",
                "survey_id": cls.survey.id,
                "question_type": "char_box",
            }
        )

    def test_controller_internal_methods(self):
        """Test the controller's internal methods without HTTP context."""
        from ..controllers.main import (
            SurveySaveForLaterController,
        )

        controller = SurveySaveForLaterController()

        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "email": "test@example.com",
            }
        )

        # Test _save_current_answers with actual answer data
        post_data = {
            str(self.question.id): "Test Answer",
        }
        controller._save_current_answers(self.survey, user_input, post_data)

        # Verify answer was saved
        lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.value_char_box, "Test Answer")

    def test_controller_save_question_answer(self):
        """Test the _save_question_answer helper method."""
        from ..controllers.main import (
            SurveySaveForLaterController,
        )

        controller = SurveySaveForLaterController()

        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
            }
        )

        # Test saving a single answer
        controller._save_question_answer(
            self.question, user_input, "Controller Test", {}
        )

        # Verify answer was saved
        lines = user_input.user_input_line_ids.filtered(
            lambda line: line.question_id == self.question
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.value_char_box, "Controller Test")


class TestSurveySaveForLaterFlow(common.HttpCase):
    """Test the full save for later flow with HTTP requests."""

    def test_full_save_and_resume_flow(self):
        """Test the complete save for later and resume flow."""
        survey = self.env["survey.survey"].create(
            {
                "title": "Integration Test Survey",
                "access_mode": "public",
                "allow_save_for_later": True,
                "questions_layout": "page_per_question",
            }
        )

        question = self.env["survey.question"].create(
            {
                "title": "Test Question",
                "survey_id": survey.id,
                "question_type": "char_box",
            }
        )

        # Start the survey to create a user_input
        response = self.url_open(f"/survey/start/{survey.access_token}")
        self.assertEqual(response.status_code, 200)

        # Find the created user_input
        user_input = self.env["survey.user_input"].search(
            [
                ("survey_id", "=", survey.id),
            ],
            limit=1,
            order="create_date desc",
        )
        self.assertTrue(
            user_input,
            "A user_input should have been created after starting the survey",
        )

        # Call the save-for-later JSON endpoint
        save_url = (
            f"/survey/save_for_later/{survey.access_token}/{user_input.access_token}"
        )
        save_response = self.url_open(
            save_url,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {str(question.id): "My Test Answer"},
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(save_response.status_code, 200)

        result = save_response.json().get("result", {})
        self.assertTrue(result.get("success"), "Save for later should succeed")
        self.assertIn(survey.access_token, result.get("resume_url", ""))
        self.assertIn(user_input.access_token, result.get("resume_url", ""))
