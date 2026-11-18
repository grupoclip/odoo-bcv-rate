# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import datetime

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import EUR, LATEST, USD, VALUE_DATE, BcvCase


@tagged("post_install", "-at_install")
class TestUpdate(BcvCase):

    def test_company_in_bolivars(self):
        with self.mock_api():
            ok, message = self.company_ves.bcv_update_rates()[self.company_ves]
        self.assertTrue(ok, message)
        usd = self._rates(self.company_ves, "USD")
        self.assertEqual(len(usd), 1)
        self.assertEqual(usd.name, VALUE_DATE)
        self.assertAlmostEqual(usd.rate, 1 / 916.6477, places=15)
        rate_in_company = usd.with_company(self.company_ves)
        self.assertAlmostEqual(rate_in_company.inverse_company_rate, 916.6477, places=6)
        self.assertAlmostEqual(self._rates(self.company_ves, "EUR").rate, 1 / EUR, places=15)
        # Every active BCV currency but the company's own one.
        self.assertEqual(
            set(self._rates(self.company_ves).mapped("currency_id.name")),
            {"USD", "EUR", "CNY", "TRY", "RUB"},
        )
        amount = self.cur["USD"]._convert(100.0, self.cur["VES"], self.company_ves, VALUE_DATE)
        self.assertAlmostEqual(amount, 91664.77, places=2)
        self.assertEqual(self.company_ves.bcv_last_effective_date, VALUE_DATE)
        self.assertTrue(self.company_ves.bcv_last_sync)

    def test_company_in_dollars(self):
        with self.mock_api():
            ok, message = self.company_usd.bcv_update_rates()[self.company_usd]
        self.assertTrue(ok, message)
        self.assertAlmostEqual(self._rates(self.company_usd, "VES").rate, 916.6477, places=9)
        self.assertAlmostEqual(self._rates(self.company_usd, "EUR").rate, USD / EUR, places=15)
        self.assertFalse(self._rates(self.company_usd, "USD"))
        amount = self.cur["USD"]._convert(10.0, self.cur["VES"], self.company_usd, VALUE_DATE)
        self.assertAlmostEqual(amount, 9166.48, places=2)

    def test_cross_rates_company_in_euros(self):
        company = self._make_company("BCV EUR company", "EUR")
        with self.mock_api():
            ok, _message = company.bcv_update_rates()[company]
        self.assertTrue(ok)
        self.assertAlmostEqual(self._rates(company, "USD").rate, EUR / USD, places=15)
        self.assertAlmostEqual(self._rates(company, "VES").rate, EUR, places=9)

    def test_unsupported_company_currency(self):
        company = self._make_company("BCV COP company", "COP")
        with self.mock_api():
            ok, message = company.bcv_update_rates()[company]
        self.assertFalse(ok)
        self.assertIn("COP", message)
        self.assertFalse(self._rates(company))
        self.assertEqual(company.bcv_last_status, message)

    def test_same_date_is_updated_not_duplicated(self):
        with self.mock_api():
            self.company_ves.bcv_update_rates()
            ok, message = self.company_ves.bcv_update_rates()[self.company_ves]
        self.assertTrue(ok)
        self.assertIn("0 created", message)
        self.assertEqual(len(self._rates(self.company_ves, "USD")), 1)
        corrected = dict(LATEST, USD=917.0)
        with self.mock_api(latest=corrected):
            self.company_ves.bcv_update_rates()
        usd = self._rates(self.company_ves, "USD")
        self.assertEqual(len(usd), 1)
        self.assertAlmostEqual(usd.rate, 1 / 917.0, places=15)

    def test_missing_currency_is_skipped(self):
        payload = dict(LATEST)
        del payload["CNY"]
        with self.mock_api(latest=payload):
            ok, message = self.company_ves.bcv_update_rates()[self.company_ves]
        self.assertTrue(ok)
        self.assertIn("CNY", message)
        self.assertFalse(self._rates(self.company_ves, "CNY"))
        self.assertTrue(self._rates(self.company_ves, "USD"))

    def test_selected_currencies_only(self):
        self.company_ves.bcv_currency_ids = self.cur["USD"]
        with self.mock_api():
            self.company_ves.bcv_update_rates()
        self.assertEqual(self._rates(self.company_ves).currency_id, self.cur["USD"])

    def test_no_target_currency(self):
        self.company_usd.bcv_currency_ids = self.cur["COP"]  # not a BCV currency
        with self.mock_api():
            ok, message = self.company_usd.bcv_update_rates()[self.company_usd]
        self.assertFalse(ok)
        self.assertIn("VES", message)
        self.assertFalse(self._rates(self.company_usd))

    def test_legacy_vef_bolivar(self):
        self.company_ves.currency_id = self.cur["EUR"]  # VES must be unused to deactivate it
        self.cur["VES"].active = False
        self.cur["VEF"].active = True
        with self.mock_api():
            ok, _message = self.company_usd.bcv_update_rates()[self.company_usd]
        self.assertTrue(ok)
        self.assertAlmostEqual(self._rates(self.company_usd, "VEF").rate, 916.6477, places=9)

    def test_network_failure_keeps_previous_rate(self):
        previous = self.env["res.currency.rate"].create({
            "name": VALUE_DATE - datetime.timedelta(days=1),
            "currency_id": self.cur["USD"].id,
            "company_id": self.company_ves.id,
            "rate": 1 / 915.7476,
        })
        self.company_ves.bcv_auto_update = True
        with self.mock_api(error="timed out"):
            self.env["res.company"]._cron_bcv_update_rates()  # must not raise
        self.assertEqual(self._rates(self.company_ves, "USD"), previous)
        self.assertIn("timed out", self.company_ves.bcv_last_status)

    def test_cron_updates_enabled_companies_only(self):
        self.company_ves.bcv_auto_update = True
        with self.mock_api() as calls:
            self.env["res.company"]._cron_bcv_update_rates()
        self.assertEqual(calls, ["rate.json"])  # one request for all companies
        self.assertTrue(self._rates(self.company_ves))
        self.assertFalse(self._rates(self.company_usd))
        self.assertFalse(self.company_ves.bcv_next_update)  # daily: every run

    def test_cron_weekly_interval(self):
        self.company_ves.write({"bcv_auto_update": True, "bcv_interval": "weekly"})
        with self.mock_api():
            self.env["res.company"]._cron_bcv_update_rates()
        self.assertTrue(self.company_ves.bcv_next_update)
        with self.mock_api() as calls:
            self.env["res.company"]._cron_bcv_update_rates()
        self.assertEqual(calls, [])  # not due yet

    def test_update_now_button(self):
        settings = self.env["res.config.settings"].with_company(self.company_ves).create({})
        self.assertTrue(settings.bcv_company_supported)
        self.assertEqual(
            set(settings.bcv_available_currency_ids.mapped("name")),
            {"USD", "EUR", "CNY", "TRY", "RUB"},
        )
        with self.mock_api():
            action = settings.action_bcv_update_now()
        self.assertEqual(action["params"]["type"], "success")
        self.assertTrue(self._rates(self.company_ves, "USD"))

    def test_only_managers(self):
        user = new_test_user(self.env, login="bcv_basic_user", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.env["res.company"].with_user(user)._bcv_check_manager()
