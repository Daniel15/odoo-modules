# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from lxml import etree

from odoo import tools
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.currency_format.defaults import (
    DEFAULT_SPACING_BY_CURRENCY,
    get_default_spacing_for_currency,
)
from odoo.addons.currency_format.hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestCurrencyFormat(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency = cls.env["res.currency"].create(
            {
                "name": "XTS",
                "symbol": "$",
                "rounding": 0.01,
                "position": "before",
            }
        )
        cls.env = cls.env(context={**cls.env.context, "lang": "en_US"})

    def test_display_format_updates_position_and_spacing(self):
        display_formats = self.currency._fields["display_format"].selection

        for display_format, _label in display_formats:
            with self.subTest(display_format=display_format):
                self.currency.display_format = display_format
                self.assertEqual(
                    (self.currency.position, self.currency.symbol_spacing),
                    tuple(display_format.split("_", 1)),
                )
                self.assertEqual(self.currency.display_format, display_format)

    def test_currency_form_uses_one_display_format_field(self):
        view = self.env.ref("currency_format.view_currency_form")
        arch = etree.fromstring(view.arch_db)
        display_format_fields = arch.xpath("//field[@name='display_format']")

        self.assertEqual(len(display_format_fields), 1)
        self.assertEqual(
            display_format_fields[0].get("widget"),
            "currency_display_format",
        )
        self.assertEqual(display_format_fields[0].get("required"), "1")
        self.assertEqual(
            len(arch.xpath("//field[@name='position'][@position='replace']")),
            1,
        )

    def test_python_formatters_support_all_display_formats(self):
        display_formats = self.currency._fields["display_format"].selection

        for display_format, _label in display_formats:
            with self.subTest(display_format=display_format):
                self.currency.display_format = display_format
                separator = (
                    "\N{NO-BREAK SPACE}"
                    if self.currency.symbol_spacing == "space"
                    else ""
                )
                if self.currency.position == "before":
                    expected = f"${separator}1.23"
                else:
                    expected = f"1.23{separator}$"
                self.assertEqual(
                    tools.format_amount(self.env, 1.23, self.currency),
                    expected,
                )
                self.assertEqual(
                    tools.formatLang(self.env, 1.23, currency_obj=self.currency),
                    expected,
                )
                self.assertEqual(self.currency.format(1.23), expected)

    def test_qweb_monetary_formatter_supports_no_space(self):
        self.currency.display_format = "before_no_space"

        formatted = self.env["ir.qweb.field.monetary"].value_to_html(
            1.23,
            {"display_currency": self.currency},
        )

        self.assertEqual(
            str(formatted),
            '$<span class="oe_currency_value">1.23</span>',
        )

    def test_currency_session_data_includes_symbol_spacing(self):
        self.currency.symbol_spacing = "no_space"

        currencies = self.env["ir.http"].get_currencies()

        self.assertEqual(currencies[self.currency.id]["symbol_spacing"], "no_space")

    def test_default_spacing_for_currency(self):
        self.assertEqual(get_default_spacing_for_currency("USD"), "no_space")
        self.assertEqual(get_default_spacing_for_currency("JPY"), "no_space")
        self.assertEqual(get_default_spacing_for_currency("EUR"), "space")
        self.assertEqual(get_default_spacing_for_currency("CHF"), "space")
        self.assertEqual(get_default_spacing_for_currency("XTS"), "space")

    def test_defaults_cover_all_base_currencies(self):
        currency_data = self.env["ir.model.data"].search(
            [("module", "=", "base"), ("model", "=", "res.currency")]
        )
        currency_codes = (
            self.env["res.currency"]
            .browse(currency_data.mapped("res_id"))
            .mapped("name")
        )

        self.assertSetEqual(set(currency_codes), set(DEFAULT_SPACING_BY_CURRENCY))

    def test_post_init_hook_sets_existing_currencies(self):
        usd = self.env.ref("base.USD")
        eur = self.env.ref("base.EUR")
        jpy = self.env.ref("base.JPY")
        usd.symbol_spacing = False
        eur.symbol_spacing = "no_space"
        jpy.symbol_spacing = False

        post_init_hook(self.env)

        self.assertEqual(usd.symbol_spacing, "no_space")
        self.assertEqual(eur.symbol_spacing, "no_space")
        self.assertEqual(jpy.symbol_spacing, "no_space")
