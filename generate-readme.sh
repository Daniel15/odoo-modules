#!/bin/sh
oca-gen-addons-table
oca-gen-addon-readme --org-name Daniel15 --repo-name odoo-modules --branch 18.0 --addons-dir .

# Strip OCA banner image from generated README files
find . -path './docker' -prune -o -path '*/README.rst' -exec sed -i '/^.. image:: https:\/\/odoo-community.org\/readme-banner-image$/,/^$/d' {} \;

# Strip OCA banner image from generated index.html files
find . -path './docker' -prune -o -path '*/static/description/index.html' -exec sed -i '/<a class="reference external image-reference" href="https:\/\/odoo-community.org\/get-involved/,/<\/a>/d' {} \;
