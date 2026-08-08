# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import MagicMock, patch

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

    @mute_logger("odoo.addons.pos_stripe_server_driven.models.pos_payment_method")
    def test_api_exception_returns_empty_list(self):
        """An exception from the Stripe API returns an empty list."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        with self._mock_stripe_request(
            side_effect=ConnectionError("Network unreachable")
        ):
            result = self.payment_method_model._get_stripe_readers()
        self.assertEqual(result, [])

    @mute_logger("odoo.addons.pos_stripe_server_driven.models.pos_payment_method")
    def test_error_response_returns_empty_list(self):
        """An error in the Stripe response returns an empty list."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        mock_response = {
            "error": {
                "message": "Invalid API Key provided",
                "type": "authentication_error",
            }
        }
        with self._mock_stripe_request(return_value=mock_response):
            result = self.payment_method_model._get_stripe_readers()
        self.assertEqual(result, [])

    @mute_logger("odoo.addons.pos_stripe_server_driven.models.pos_payment_method")
    def test_empty_response_returns_empty_list(self):
        """A None/empty response from Stripe returns an empty list."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        with self._mock_stripe_request(return_value=None):
            result = self.payment_method_model._get_stripe_readers()
        self.assertEqual(result, [])

    @mute_logger("odoo.addons.pos_stripe_server_driven.models.pos_payment_method")
    def test_error_without_message_returns_empty_list(self):
        """An error response without a message field returns an empty list."""
        if not self.provider:
            self.skipTest("No Stripe provider configured")
        mock_response = {"error": {"type": "api_error"}}
        with self._mock_stripe_request(return_value=mock_response):
            result = self.payment_method_model._get_stripe_readers()
        self.assertEqual(result, [])


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
        """UserError raised before any API call when no reader is configured."""
        self._skip_if_no_provider()
        # Clear the reader ID
        self.env.cr.execute(
            "UPDATE pos_payment_method SET stripe_reader_id = NULL WHERE id = %s",
            (self.payment_method.id,),
        )
        self.payment_method.invalidate_recordset()

        with self._mock_stripe_request() as mock_req:
            with self.assertRaises(UserError):
                self.payment_method.stripe_sd_create_and_process_payment(10.00)
            # No Stripe API calls should have been made
            mock_req.assert_not_called()

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

    def test_check_payment_status_returns_authorization_details(self):
        self._skip_if_no_provider()
        response = {
            "id": "pi_status",
            "status": "requires_capture",
            "latest_charge": {
                "id": "ch_status",
                "payment_method_details": {
                    "type": "card_present",
                    "card_present": {"brand": "visa"},
                },
            },
        }
        with self._mock_stripe_request(return_value=response) as mock_req:
            result = self.payment_method.stripe_sd_check_payment_status("pi_status")

        mock_req.assert_called_once_with("payment_intents/pi_status", method="GET")
        self.assertEqual(
            result,
            {
                "status": "requires_capture",
                "card_brand": "visa",
                "transaction_id": "ch_status",
            },
        )

    def test_check_payment_status_error_is_reported(self):
        self._skip_if_no_provider()
        with self._mock_stripe_request(
            return_value={"error": {"message": "Status unavailable"}}
        ):
            with self.assertRaisesRegex(UserError, "Status unavailable"):
                self.payment_method.stripe_sd_check_payment_status("pi_status")

    def test_capture_payment_returns_card_details(self):
        self._skip_if_no_provider()
        response = {
            "id": "pi_capture",
            "status": "succeeded",
            "latest_charge": {
                "id": "ch_capture",
                "payment_method_details": {
                    "type": "card_present",
                    "card_present": {"brand": "mastercard"},
                },
            },
        }
        with self._mock_stripe_request(return_value=response) as mock_req:
            result = self.payment_method.stripe_sd_capture_payment("pi_capture")

        mock_req.assert_called_once_with("payment_intents/pi_capture/capture")
        self.assertEqual(
            result,
            {"card_brand": "mastercard", "transaction_id": "ch_capture"},
        )

    def test_capture_payment_error_is_reported(self):
        self._skip_if_no_provider()
        with self._mock_stripe_request(
            return_value={"error": {"message": "Capture failed"}}
        ):
            with self.assertRaisesRegex(UserError, "Capture failed"):
                self.payment_method.stripe_sd_capture_payment("pi_capture")

    def test_cancel_payment_cancels_reader_and_intent(self):
        self._skip_if_no_provider()
        with self._mock_stripe_request(
            side_effect=[{}, {"id": "pi_cancel", "status": "canceled"}]
        ) as mock_req:
            result = self.payment_method.stripe_sd_cancel_payment("pi_cancel")

        self.assertTrue(result)
        self.assertEqual(
            [call.args[0] for call in mock_req.call_args_list],
            [
                "terminal/readers/tmr_test123/cancel_action",
                "payment_intents/pi_cancel/cancel",
            ],
        )

    def test_cancel_payment_tolerates_completed_intent(self):
        self._skip_if_no_provider()
        with self._mock_stripe_request(
            side_effect=[
                {},
                {"error": {"code": "payment_intent_unexpected_state"}},
            ]
        ):
            self.assertTrue(
                self.payment_method.stripe_sd_cancel_payment("pi_completed")
            )


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
        return self.provider._stripe_sd_find_pos_configs(payment_method)

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

    def test_reader_event_dispatches_pos_notification(self):
        self._skip_if_no_provider()
        pos_config = MagicMock()
        event = {
            "id": "evt_reader_success",
            "type": "terminal.reader.action_succeeded",
            "data": {
                "object": {
                    "id": "tmr_webhook_test",
                    "action": {
                        "process_payment_intent": {"payment_intent": "pi_reader_test"}
                    },
                }
            },
        }
        with patch.object(
            type(self.provider),
            "_stripe_sd_find_pos_configs",
            return_value=[pos_config],
        ):
            handled = self.provider._stripe_terminal_dispatch_webhook_event(event)

        self.assertTrue(handled)
        pos_config._notify.assert_called_once_with(
            "STRIPE_SD_PAYMENT_STATUS",
            {
                "payment_intent_id": "pi_reader_test",
                "status": "succeeded",
                "failure_message": "",
            },
        )

    def test_reader_failure_notifies_every_open_pos(self):
        self._skip_if_no_provider()
        pos_configs = [MagicMock(), MagicMock()]
        event = {
            "id": "evt_reader_failure",
            "type": "terminal.reader.action_failed",
            "data": {
                "object": {
                    "id": "tmr_webhook_test",
                    "action": {
                        "failure_message": "Card was declined",
                        "process_payment_intent": {
                            "payment_intent": "pi_reader_failed"
                        },
                    },
                }
            },
        }
        with patch.object(
            type(self.provider),
            "_stripe_sd_find_pos_configs",
            return_value=pos_configs,
        ):
            handled = self.provider._stripe_terminal_dispatch_webhook_event(event)

        self.assertTrue(handled)
        for pos_config in pos_configs:
            pos_config._notify.assert_called_once_with(
                "STRIPE_SD_PAYMENT_STATUS",
                {
                    "payment_intent_id": "pi_reader_failed",
                    "status": "failed",
                    "failure_message": "Card was declined",
                },
            )

    def test_unrelated_terminal_event_is_not_handled(self):
        self._skip_if_no_provider()
        self.assertFalse(
            self.provider._stripe_terminal_dispatch_webhook_event(
                {"id": "evt_other", "type": "unhandled.event"}
            )
        )

    def test_duplicate_legacy_secrets_resolve_provider_from_reader_company(self):
        self._skip_if_no_provider()
        other_company = self.env["res.company"].create({"name": "Other Company"})
        other_provider = self.provider.copy(
            {
                "name": "Other Company Stripe",
                "company_id": other_company.id,
                "journal_id": False,
                "state": "disabled",
            }
        )
        providers = self.provider | other_provider
        payment_method = MagicMock(company_id=other_company)
        event = {
            "type": "terminal.reader.action_succeeded",
            "data": {"object": {"id": "tmr_other_company"}},
        }
        with patch.object(
            type(self.env["pos.payment.method"]),
            "search",
            return_value=payment_method,
        ):
            resolved_provider = providers._stripe_sd_resolve_legacy_webhook_provider(
                event
            )
        self.assertEqual(resolved_provider, other_provider)
