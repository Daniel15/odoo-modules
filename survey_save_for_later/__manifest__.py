# Copyright 2026 Daniel Lo Nigro
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Survey Save for Later",
    "summary": "Allow users to save survey progress and resume later",
    "version": "18.0.1.0.0",
    "category": "Survey",
    "depends": ["survey", "mail"],
    "data": [
        "data/mail_template_data.xml",
        "views/survey_survey_views.xml",
        "views/survey_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "survey_save_for_later/static/src/js/survey_save_for_later.esm.js",
        ],
    },
    "author": "Daniel Lo Nigro",
    "maintainers": ["Daniel15"],
    "website": "https://d.sb/odoo-modules",
    "license": "AGPL-3",
    "installable": True,
}
