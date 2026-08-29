# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Currency Symbol Spacing",
    "summary": "Configure currency symbol position and spacing",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "depends": ["web"],
    "data": [
        "views/res_currency_views.xml",
    ],
    "images": [
        "static/description/banner.png",
    ],
    "assets": {
        # This is messy, but unfortunately there's no way to patch the formatCurrency
        # module without replacing the entire file. Odoo's patch() function only works
        # for classes and objects, not for standalone functions.
        #
        # The actual changes are in `currency.esm.js.patch` so they can be easily
        # reapplied to future Odoo versions.
        "web._assets_core": [
            (
                "replace",
                "web/static/src/core/currency.js",
                "currency_format/static/src/core/currency.esm.js",
            ),
        ],
        "web.assets_frontend": [
            (
                "replace",
                "web/static/src/core/currency.js",
                "currency_format/static/src/core/currency.esm.js",
            ),
        ],
        "web.assets_backend": [
            "currency_format/static/src/views/fields/currency_display_format_field.esm.js",
            "currency_format/static/src/views/fields/monetary_field.xml",
        ],
        "web.assets_unit_tests": [
            "currency_format/static/tests/core/currency.test.js",
        ],
    },
    "post_load": "post_load",
    "post_init_hook": "post_init_hook",
    "author": "Daniel Lo Nigro",
    "maintainers": ["Daniel15"],
    "website": "https://d.sb/odoo-modules",
    "license": "AGPL-3",
    "installable": True,
}
