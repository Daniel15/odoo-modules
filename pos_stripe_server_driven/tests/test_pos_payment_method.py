# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestPosPaymentMethodStripeReaders(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.payment_method_model = cls.env["pos.payment.method"]
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )

    def _mock_stripe_request(self, return_value=None, side_effect=None):
        return patch.object(
            type(self.provider),
            "_stripe_make_request",
            return_value=return_value,
            side_effect=side_effect,
        )

    def test_no_provider_returns_empty(self):
        """When no Stripe provider exists, returns empty list without error."""
        with patch.object(
            type(self.env["payment.provider"]),
            "search",
            return_value=self.env["payment.provider"],
        ):
            result = self.payment_method_model._get_stripe_readers()
        self.assertEqual(result, [])

    def test_success_returns_readers(self):
        """Successful API call returns reader selection list."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        mock_response = {
            "data": [
                {"id": "tmr_abc123", "label": "Front Counter"},
                {"id": "tmr_def456", "label": "Back Office"},
            ]
        }
        with self._mock_stripe_request(return_value=mock_response):
            result = self.payment_method_model._get_stripe_readers()
        self.assertEqual(
            result,
            [
                ("tmr_abc123", "Front Counter (tmr_abc123)"),
                ("tmr_def456", "Back Office (tmr_def456)"),
            ],
        )

    def test_api_exception_raises_user_error(self):
        """An exception from the Stripe API raises UserError."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        with self._mock_stripe_request(
            side_effect=ConnectionError("Network unreachable")
        ):
            with self.assertRaises(UserError) as ctx:
                self.payment_method_model._get_stripe_readers()
        self.assertIn("Network unreachable", str(ctx.exception))

    def test_error_response_raises_user_error(self):
        """An error in the Stripe response raises UserError with the message."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        mock_response = {
            "error": {
                "message": "Invalid API Key provided",
                "type": "authentication_error",
            }
        }
        with self._mock_stripe_request(return_value=mock_response):
            with self.assertRaises(UserError) as ctx:
                self.payment_method_model._get_stripe_readers()
        self.assertIn("Invalid API Key provided", str(ctx.exception))

    def test_empty_response_raises_user_error(self):
        """A None/empty response from Stripe raises UserError."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        with self._mock_stripe_request(return_value=None):
            with self.assertRaises(UserError) as ctx:
                self.payment_method_model._get_stripe_readers()
        self.assertIn("Empty response", str(ctx.exception))

    def test_error_without_message_raises_user_error(self):
        """An error response without a message field uses fallback text."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        mock_response = {"error": {"type": "api_error"}}
        with self._mock_stripe_request(return_value=mock_response):
            with self.assertRaises(UserError) as ctx:
                self.payment_method_model._get_stripe_readers()
        self.assertIn("Unknown error", str(ctx.exception))


class TestPosPaymentMethodCreateWebhook(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return
        journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Stripe Terminal Test",
                "journal_id": journal.id if journal else False,
                "use_payment_terminal": "stripe_server_driven",
            }
        )

    def _skip_if_no_provider(self):
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _mock_stripe_request(self, return_value=None):
        return patch.object(
            type(self.provider),
            "_stripe_make_request",
            return_value=return_value,
        )

    def test_create_webhook_success(self):
        """Successfully creates a webhook and saves the secret."""
        self._skip_if_no_provider()
        self.payment_method.stripe_terminal_webhook_secret = False
        mock_response = {"secret": "whsec_test123"}
        with (
            self._mock_stripe_request(return_value=mock_response) as mock_req,
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
        ):
            result = self.payment_method.action_stripe_sd_create_webhook()
            mock_req.assert_called_once()
            call_args = mock_req.call_args
            self.assertEqual(call_args[0][0], "webhook_endpoints")
            payload = call_args[1]["payload"]
            self.assertIn("/pos_stripe_server_driven/webhook", payload["url"])
            self.assertEqual(
                payload["enabled_events[]"],
                [
                    "terminal.reader.action_succeeded",
                    "terminal.reader.action_failed",
                ],
            )
        self.assertEqual(
            self.payment_method.stripe_terminal_webhook_secret, "whsec_test123"
        )
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "info")

    def test_create_webhook_already_set(self):
        """Returns warning when webhook secret is already configured."""
        self._skip_if_no_provider()
        self.payment_method.stripe_terminal_webhook_secret = "whsec_existing"
        with self._mock_stripe_request() as mock_req:
            result = self.payment_method.action_stripe_sd_create_webhook()
            mock_req.assert_not_called()
        self.assertEqual(result["params"]["type"], "warning")
        # Secret unchanged
        self.assertEqual(
            self.payment_method.stripe_terminal_webhook_secret, "whsec_existing"
        )

    @mute_logger("odoo.addons.pos_stripe_server_driven.models.pos_payment_method")
    def test_create_webhook_stripe_error(self):
        """Returns error when Stripe returns an error creating the webhook."""
        self._skip_if_no_provider()
        self.payment_method.stripe_terminal_webhook_secret = False
        mock_response = {"error": {"message": "Invalid API key"}}
        with (
            self._mock_stripe_request(return_value=mock_response),
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
        ):
            result = self.payment_method.action_stripe_sd_create_webhook()
        self.assertEqual(result["params"]["type"], "danger")
        self.assertFalse(self.payment_method.stripe_terminal_webhook_secret)

    @mute_logger("odoo.addons.pos_stripe_server_driven.models.pos_payment_method")
    def test_create_webhook_missing_secret_in_response(self):
        """Returns error when Stripe response has no secret."""
        self._skip_if_no_provider()
        self.payment_method.stripe_terminal_webhook_secret = False
        mock_response = {"id": "we_123"}  # No "secret" key
        with (
            self._mock_stripe_request(return_value=mock_response),
            patch.object(type(self.provider), "stripe_secret_key", new="sk_test_fake"),
        ):
            result = self.payment_method.action_stripe_sd_create_webhook()
        self.assertEqual(result["params"]["type"], "danger")
        self.assertFalse(self.payment_method.stripe_terminal_webhook_secret)

    def test_create_webhook_no_secret_key(self):
        """Returns error when Stripe secret key is not set on the provider."""
        self._skip_if_no_provider()
        self.payment_method.stripe_terminal_webhook_secret = False
        with patch.object(
            type(self.provider),
            "stripe_secret_key",
            new_callable=lambda: property(lambda _self: ""),
        ):
            result = self.payment_method.action_stripe_sd_create_webhook()
        self.assertEqual(result["params"]["type"], "danger")


class TestStripePaymentFlow(TransactionCase):
    """Tests for the core payment flow methods."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return
        journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Stripe Terminal Flow Test",
                "journal_id": journal.id if journal else False,
                "use_payment_terminal": "stripe_server_driven",
                "stripe_reader_id": False,
            }
        )
        # Set reader ID directly in DB to bypass selection constraint
        cls.env.cr.execute(
            "UPDATE pos_payment_method SET stripe_reader_id = %s WHERE id = %s",
            ("tmr_test123", cls.payment_method.id),
        )
        cls.payment_method.invalidate_recordset()
        # Grant POS user group
        cls.env.user.groups_id += cls.env.ref("point_of_sale.group_pos_user")

    def _skip_if_no_provider(self):
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _mock_stripe_request(self, side_effect=None, return_value=None):
        return patch.object(
            type(self.provider),
            "_stripe_make_request",
            side_effect=side_effect,
            return_value=return_value,
        )

    def test_create_and_process_payment_success(self):
        """Successful payment creates intent and hands off to reader."""
        self._skip_if_no_provider()
        intent_response = {"id": "pi_test_123", "status": "requires_payment_method"}
        reader_response = {
            "action": {"status": "in_progress", "type": "process_payment_intent"}
        }

        with self._mock_stripe_request(
            side_effect=[intent_response, reader_response]
        ) as mock_req:
            result = self.payment_method.stripe_sd_create_and_process_payment(10.00)

        self.assertEqual(result["payment_intent_id"], "pi_test_123")
        self.assertEqual(result["status"], "in_progress")

        # Verify PaymentIntent creation params
        intent_call = mock_req.call_args_list[0]
        self.assertEqual(intent_call[0][0], "payment_intents")
        params = dict(intent_call[0][1])
        self.assertEqual(params["capture_method"], "manual")
        self.assertEqual(params["payment_method_types[]"], "card_present")

        # Verify reader handoff
        reader_call = mock_req.call_args_list[1]
        self.assertIn("terminal/readers/tmr_test123/", reader_call[0][0])

    def test_create_and_process_payment_intent_error(self):
        """UserError raised when PaymentIntent creation fails."""
        self._skip_if_no_provider()
        error_response = {"error": {"message": "Insufficient funds"}}

        with self._mock_stripe_request(return_value=error_response):
            with self.assertRaises(UserError) as ctx:
                self.payment_method.stripe_sd_create_and_process_payment(10.00)
        self.assertIn("Insufficient funds", str(ctx.exception))

    def test_create_and_process_payment_reader_error_cancels_intent(self):
        """When reader handoff fails, the PaymentIntent is cancelled."""
        self._skip_if_no_provider()
        intent_response = {"id": "pi_test_456"}
        reader_error = {"error": {"message": "Reader is busy"}}
        cancel_response = {"id": "pi_test_456", "status": "canceled"}

        with self._mock_stripe_request(
            side_effect=[intent_response, reader_error, cancel_response]
        ) as mock_req:
            with self.assertRaises(UserError) as ctx:
                self.payment_method.stripe_sd_create_and_process_payment(10.00)

        self.assertIn("Reader is busy", str(ctx.exception))
        # Verify intent was cancelled
        cancel_call = mock_req.call_args_list[2]
        self.assertIn("payment_intents/pi_test_456/cancel", cancel_call[0][0])

    def test_create_and_process_payment_no_reader(self):
        """UserError raised when no reader is configured."""
        self._skip_if_no_provider()
        # Clear the reader ID
        self.env.cr.execute(
            "UPDATE pos_payment_method SET stripe_reader_id = NULL WHERE id = %s",
            (self.payment_method.id,),
        )
        self.payment_method.invalidate_recordset()

        intent_response = {"id": "pi_test_no_reader"}
        with self._mock_stripe_request(return_value=intent_response):
            with self.assertRaises(UserError):
                self.payment_method.stripe_sd_create_and_process_payment(10.00)

        # Restore reader for other tests
        self.env.cr.execute(
            "UPDATE pos_payment_method SET stripe_reader_id = %s WHERE id = %s",
            ("tmr_test123", self.payment_method.id),
        )
        self.payment_method.invalidate_recordset()

    def test_create_and_process_payment_access_error(self):
        """Non-POS users cannot process payments."""
        self._skip_if_no_provider()
        with patch.object(type(self.env.user), "has_group", return_value=False):
            with self.assertRaises(AccessError):
                self.payment_method.stripe_sd_create_and_process_payment(10.00)


class TestStripeVoidAuthorizedPayment(TransactionCase):
    """Tests for stripe_sd_void_authorized_payment."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return
        journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Stripe Terminal Void Test",
                "journal_id": journal.id if journal else False,
                "use_payment_terminal": "stripe_server_driven",
            }
        )
        cls.env.user.groups_id += cls.env.ref("point_of_sale.group_pos_user")

    def _skip_if_no_provider(self):
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _mock_stripe_request(self, return_value=None):
        return patch.object(
            type(self.provider),
            "_stripe_make_request",
            return_value=return_value,
        )

    def test_void_success(self):
        """Successfully voids an authorized PaymentIntent."""
        self._skip_if_no_provider()
        cancel_response = {"id": "pi_test_789", "status": "canceled"}

        with self._mock_stripe_request(return_value=cancel_response) as mock_req:
            result = self.payment_method.stripe_sd_void_authorized_payment(
                "pi_test_789"
            )

        self.assertTrue(result)
        mock_req.assert_called_once()
        self.assertIn("payment_intents/pi_test_789/cancel", mock_req.call_args[0][0])

    def test_void_already_cancelled(self):
        """Voiding an already-cancelled intent succeeds gracefully."""
        self._skip_if_no_provider()
        error_response = {
            "error": {
                "code": "payment_intent_unexpected_state",
                "message": "already canceled",
            }
        }

        with self._mock_stripe_request(return_value=error_response):
            result = self.payment_method.stripe_sd_void_authorized_payment(
                "pi_test_cancelled"
            )

        self.assertTrue(result)

    def test_void_other_error_raises(self):
        """Other Stripe errors when voiding raise UserError."""
        self._skip_if_no_provider()
        error_response = {
            "error": {
                "code": "resource_missing",
                "message": "No such payment intent",
            }
        }

        with self._mock_stripe_request(return_value=error_response):
            with self.assertRaises(UserError) as ctx:
                self.payment_method.stripe_sd_void_authorized_payment("pi_missing")
        self.assertIn("No such payment intent", str(ctx.exception))

    def test_void_no_reader_cancel(self):
        """Void does not call cancel_action on the reader."""
        self._skip_if_no_provider()
        cancel_response = {"id": "pi_test_void", "status": "canceled"}

        with self._mock_stripe_request(return_value=cancel_response) as mock_req:
            self.payment_method.stripe_sd_void_authorized_payment("pi_test_void")

        # Only one call — the intent cancel. No reader cancel_action call.
        mock_req.assert_called_once()
        self.assertNotIn("terminal/readers", mock_req.call_args[0][0])


class TestWebhookFindPosConfigs(TransactionCase):
    """Tests for _find_pos_configs returning multiple configs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env["payment.provider"].search(
            [("code", "=", "stripe"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        if not cls.provider:
            return

        journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.env.company.id)],
            limit=1,
        )
        cls.payment_method = cls.env["pos.payment.method"].create(
            {
                "name": "Stripe Terminal Webhook Test",
                "journal_id": journal.id if journal else False,
                "use_payment_terminal": "stripe_server_driven",
                "stripe_terminal_webhook_secret": "whsec_test",
            }
        )
        cls.env.cr.execute(
            "UPDATE pos_payment_method SET stripe_reader_id = %s WHERE id = %s",
            ("tmr_webhook_test", cls.payment_method.id),
        )
        cls.payment_method.invalidate_recordset()

        # Create two POS configs sharing the same payment method
        cls.pos_config_1 = cls.env["pos.config"].create(
            {
                "name": "Station 1",
                "payment_method_ids": [(4, cls.payment_method.id)],
            }
        )
        cls.pos_config_2 = cls.env["pos.config"].create(
            {
                "name": "Station 2",
                "payment_method_ids": [(4, cls.payment_method.id)],
            }
        )

    def _skip_if_no_provider(self):
        if not self.provider:
            self.skipTest("No Stripe provider configured")

    def _call_find_pos_configs(self, payment_method):
        """Call _find_pos_configs with request.env mocked to self.env."""
        from unittest.mock import MagicMock

        from ..controllers.main import PosStripeServerDrivenController

        controller = PosStripeServerDrivenController()
        mock_request = MagicMock()
        mock_request.env = self.env
        with patch(
            "odoo.addons.pos_stripe_server_driven.controllers.main.request",
            mock_request,
        ):
            return controller._find_pos_configs(payment_method)

    def _open_session(self, config):
        """Open a POS session and transition it to 'opened' state."""
        config.open_ui()
        session = config.current_session_id
        session.set_opening_control(0, None)
        return session

    def test_find_pos_configs_returns_all_open_sessions(self):
        """All open sessions' configs are returned, not just the first."""
        self._skip_if_no_provider()

        # Open sessions for both configs
        self._open_session(self.pos_config_1)
        self._open_session(self.pos_config_2)

        try:
            configs = self._call_find_pos_configs(self.payment_method)
            self.assertIn(self.pos_config_1, configs)
            self.assertIn(self.pos_config_2, configs)
            self.assertEqual(len(configs), 2)
        finally:
            # Clean up sessions
            for config in (self.pos_config_1, self.pos_config_2):
                session = config.current_session_id
                if session and session.state == "opened":
                    session.close_session_from_ui()

    def test_find_pos_configs_excludes_closed_sessions(self):
        """Closed sessions are not included in the result."""
        self._skip_if_no_provider()

        self._open_session(self.pos_config_1)
        try:
            configs = self._call_find_pos_configs(self.payment_method)
            self.assertIn(self.pos_config_1, configs)
            self.assertNotIn(self.pos_config_2, configs)
        finally:
            session = self.pos_config_1.current_session_id
            if session and session.state == "opened":
                session.close_session_from_ui()

    def test_find_pos_configs_empty_when_no_sessions(self):
        """Returns empty recordset when no sessions are open."""
        self._skip_if_no_provider()
        configs = self._call_find_pos_configs(self.payment_method)
        self.assertFalse(configs)
