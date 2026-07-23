# Daniel15 Odoo Modules
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/Daniel15/odoo-modules/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/Daniel15/odoo-modules/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/Daniel15/odoo-modules/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/Daniel15/odoo-modules/actions/workflows/test.yml?query=branch%3A18.0)
[![codecov](https://codecov.io/gh/Daniel15/odoo-modules/branch/18.0/graph/badge.svg)](https://codecov.io/gh/Daniel15/odoo-modules)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

My addons for Odoo.

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[payment_stripe_terminal_base](payment_stripe_terminal_base/) | 18.0.1.0.0 | <a href='https://github.com/Daniel15'><img src='https://github.com/Daniel15.png' width='32' height='32' style='border-radius:50%;' alt='Daniel15'/></a> | Provides reusable infrastructure for Stripe Terminal integrations
[pos_stripe_server_driven](pos_stripe_server_driven/) | 18.0.2.0.0 | <a href='https://github.com/Daniel15'><img src='https://github.com/Daniel15.png' width='32' height='32' style='border-radius:50%;' alt='Daniel15'/></a> | Integrate your POS with a Stripe terminal via server-driven integration
[survey_debrand](survey_debrand/) | 18.0.1.0.0 | <a href='https://github.com/Daniel15'><img src='https://github.com/Daniel15.png' width='32' height='32' style='border-radius:50%;' alt='Daniel15'/></a> | Remove Odoo branding from survey pages
[survey_question_list_all](survey_question_list_all/) | 18.0.1.0.0 | <a href='https://github.com/Daniel15'><img src='https://github.com/Daniel15.png' width='32' height='32' style='border-radius:50%;' alt='Daniel15'/></a> | List all questions in the survey form instead of only 40 per page
[survey_question_text_content](survey_question_text_content/) | 18.0.1.0.0 | <a href='https://github.com/Daniel15'><img src='https://github.com/Daniel15.png' width='32' height='32' style='border-radius:50%;' alt='Daniel15'/></a> | Add arbitrary rich text content to surveys

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Daniel Lo Nigro
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->

## Local Development

The repository includes an Odoo 18 and PostgreSQL Docker Compose environment. Addons
from this repository are mounted at `/mnt/extra-addons` in the Odoo container.

Start the development environment:

```bash
docker compose up -d
docker compose ps
```

Open Odoo at <http://localhost:8069>. The configured database filter expects a database
named `odoo_test`.

Follow the Odoo logs:

```bash
docker compose logs -f odoo
```

Stop the environment without deleting its data:

```bash
docker compose down
```

## Automated Tests

Start PostgreSQL and wait until it is ready:

```bash
docker compose up -d db
docker compose exec db pg_isready -U odoo
```

For the first run against a new `odoo_test` database, specify the addons and test tags
you want to run. Use comma-separated values to test multiple addons. Odoo installs
declared dependencies automatically:

```bash
ADDONS=addon_name
TEST_TAGS=/addon_name

docker compose run --rm odoo \
  --stop-after-init \
  --db-filter="^odoo_test$" \
  -d odoo_test \
  -i "$ADDONS" \
  --test-enable \
  --test-tags "$TEST_TAGS" \
  --log-level=test
```

For repeat runs after changing installed addons, upgrade the addons under test:

```bash
ADDONS=addon_name
TEST_TAGS=/addon_name

docker compose stop odoo
docker compose run --rm odoo \
  --stop-after-init \
  --db-filter="^odoo_test$" \
  -d odoo_test \
  -u "$ADDONS" \
  --test-enable \
  --test-tags "$TEST_TAGS" \
  --log-level=test
```

Run one test class by narrowing `TEST_TAGS`:

```bash
ADDONS=addon_name
TEST_TAGS=/addon_name:TestClassName

docker compose run --rm odoo \
  --stop-after-init \
  --db-filter="^odoo_test$" \
  -d odoo_test \
  -u "$ADDONS" \
  --test-enable \
  --test-tags "$TEST_TAGS" \
  --log-level=test
```

Run repository formatting, lint, XML, manifest, and documentation checks:

```bash
pre-commit run --all-files
```

Open an Odoo shell against the test database:

```bash
docker compose run --rm odoo shell --db-filter="^odoo_test$" -d odoo_test
```
