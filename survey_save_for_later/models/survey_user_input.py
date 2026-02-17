# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import html_escape


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    def get_resume_url(self):
        """Get the full URL to resume this survey participation.

        :return: URL to resume the survey from where the user left off
        :rtype: str
        """
        self.ensure_one()
        base_url = self.survey_id.get_base_url()
        return f"{base_url}/survey/{self.survey_id.access_token}/{self.access_token}"

    def _get_save_for_later_email(self):
        """Get the email address to send the save-for-later email to.

        First tries to get the email from the linked partner, then from the
        email field on the user_input itself.

        :return: email address or None
        :rtype: str or None
        """
        self.ensure_one()
        if self.partner_id and self.partner_id.email:
            return self.partner_id.email
        return self.email

    def _send_save_for_later_email(self):
        """Send an email with the resume link and post a message to the chatter.

        The email contains a link that allows the user to resume their survey
        from where they left off. A message is also posted to the chatter
        to record that the email was sent.

        :return: True if email was sent successfully, False otherwise
        :raises UserError: if the email template is not found
        """
        self.ensure_one()
        email = self._get_save_for_later_email()
        if not email:
            return False

        template = self.env.ref(
            "survey_save_for_later.mail_template_save_for_later",
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_("Save for Later email template not found."))

        template.send_mail(self.id, email_layout_xmlid="mail.mail_notification_light")

        self.message_post(
            body=Markup(
                _(
                    "A 'Save for Later' email has been sent to <b>%s</b> "
                    "with a link to resume the survey."
                )
            )
            % html_escape(email)
        )
        return True
