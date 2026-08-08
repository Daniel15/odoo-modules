# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "POS Stripe (Server-driven)",
    "summary": "Integrate your POS with a Stripe terminal via"
    " server-driven integration",
    "version": "18.0.2.0.0",
    "category": "Sales/Point of Sale",
    "depends": ["point_of_sale", "payment_stripe_terminal_base"],
    "data": [
        "views/payment_provider_views.xml",
        "views/pos_payment_method_views.xml",
    ],
    "images": [
        "static/description/banner.png",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_stripe_server_driven/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_stripe_server_driven/static/src/app/utils.esm.js",
            "pos_stripe_server_driven/static/tests/unit/**/*",
        ],
    },
    "author": "Daniel Lo Nigro",
    "maintainers": ["Daniel15"],
    "website": "https://d.sb/odoo-modules",
    "license": "AGPL-3",
    "installable": True,
}
