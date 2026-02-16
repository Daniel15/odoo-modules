#!/bin/sh
oca-gen-addons-table
oca-gen-addon-readme --org-name Daniel15 --repo-name odoo-modules --branch 18.0 --addons-dir .

# Strip OCA banner image from generated README files
find . -path '*/README.rst' -exec sed -i '/^.. image:: https:\/\/odoo-community.org\/readme-banner-image$/,/^$/d' {} \;
