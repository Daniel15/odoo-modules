# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http
from odoo.exceptions import ValidationError

from odoo.addons.survey.controllers.main import Survey

_logger = logging.getLogger(__name__)


class SurveySaveForLaterController(Survey):
    """Controller handling the 'Save for Later' functionality for surveys."""

    @http.route(
        "/survey/save_for_later/<string:survey_token>/<string:answer_token>",
        type="json",
        auth="public",
        website=True,
    )
    def survey_save_for_later(self, survey_token, answer_token, **post):
        """Save the current survey progress without validation.

        This endpoint allows users to save their survey progress at any point,
        even if mandatory questions have not been answered. The current answers
        are stored and a resume link is provided.

        If the user has provided an email address (via partner or email field),
        an email is sent with the resume link.

        :param survey_token: the survey's access token
        :param answer_token: the user_input's access token
        :param post: form data containing current answers
        :return: dictionary with success status and resume URL
        """
        access_data = self._get_access_data(
            survey_token, answer_token, ensure_token=True
        )
        if access_data["validity_code"] is not True:
            return {"error": access_data["validity_code"]}

        survey_sudo, answer_sudo = (
            access_data["survey_sudo"],
            access_data["answer_sudo"],
        )

        if not survey_sudo.allow_save_for_later:
            return {"error": "save_for_later_not_allowed"}

        if answer_sudo.state == "new":
            answer_sudo._mark_in_progress()

        self._save_current_answers(survey_sudo, answer_sudo, post)

        resume_url = answer_sudo.get_resume_url()
        email_sent = False

        if answer_sudo._get_save_for_later_email():
            try:
                email_sent = answer_sudo._send_save_for_later_email()
            except Exception:
                _logger.warning(
                    "Failed to send save-for-later email for user_input %s",
                    answer_sudo.id,
                    exc_info=True,
                )
                email_sent = False

        return {
            "success": True,
            "resume_url": resume_url,
            "email_sent": email_sent,
        }

    def _save_current_answers(self, survey_sudo, answer_sudo, post):
        """Save the current form data to the user input lines.

        This saves the answers without validation, allowing users to save
        progress even when mandatory questions are not answered.

        :param survey_sudo: the survey record (sudo)
        :param answer_sudo: the user_input record (sudo)
        :param post: the form data containing answers
        """
        for question in survey_sudo.question_ids:
            if str(question.id) not in post:
                continue

            answer_data = post.get(str(question.id))

            if answer_data is None or answer_data == "":
                if question.question_type not in ("numerical_box", "date"):
                    continue

            if isinstance(answer_data, list):
                for answer_value in answer_data:
                    self._save_question_answer(
                        question, answer_sudo, answer_value, post
                    )
            else:
                self._save_question_answer(question, answer_sudo, answer_data, post)

    def _save_question_answer(self, question, answer_sudo, answer_value, post):
        """Save a single question answer.

        :param question: the question record
        :param answer_sudo: the user_input record (sudo)
        :param answer_value: the answer value
        :param post: the full POST data to check for comments
        """
        comment_key = f"{question.id}_comment"
        comment = post.get(comment_key)

        try:
            answer_sudo._save_lines(
                question, answer_value, comment=comment, overwrite_existing=True
            )
        except (ValueError, ValidationError):
            _logger.warning(
                "Failed to save answer for question %s: %s", question.id, answer_value
            )
