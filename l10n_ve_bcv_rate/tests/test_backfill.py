# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import BcvCase

D = datetime.date

HISTORY = [
    {"date": "2026-11-12", "effective_date": "2026-11-12", "USD": 910.0},
    {"date": "2026-11-13", "effective_date": "2026-11-13", "USD": 911.6243},
    {"date": "2026-11-14", "effective_date": "2026-11-13", "USD": 911.6243},
    {"date": "2026-11-15", "effective_date": "2026-11-13", "USD": 911.6243},
    {"date": "2026-11-16", "effective_date": "2026-11-16", "USD": 914.0218, "EUR": 1004.0},
    {"date": "2026-11-17", "effective_date": "2026-11-17", "USD": 915.7476, "EUR": 1005.0},
]


@tagged("post_install", "-at_install")
class TestBackfill(BcvCase):

    def _wizard(self, date_from, date_to, companies=None):
        return self.env["bcv.rate.backfill"].create({
            "date_from": date_from,
            "date_to": date_to,
            "company_ids": [(6, 0, (companies or self.company_ves).ids)],
        })

    def test_backfill_one_rate_per_value_date(self):
        wizard = self._wizard(D(2026, 11, 13), D(2026, 11, 17),
                              self.company_ves | self.company_usd)
        with self.mock_api(history=HISTORY) as calls:
            action = wizard.action_backfill()
        self.assertEqual(calls, ["history.json"])  # a single request
        self.assertEqual(action["params"]["type"], "success")
        usd = self._rates(self.company_ves, "USD")
        self.assertEqual(sorted(usd.mapped("name")),
                         [D(2026, 11, 13), D(2026, 11, 16), D(2026, 11, 17)])
        self.assertAlmostEqual(
            self._rates(self.company_ves, "USD", D(2026, 11, 16)).rate, 1 / 914.0218, places=15)
        # EUR only exists on two of the dates: the others are skipped.
        self.assertEqual(len(self._rates(self.company_ves, "EUR")), 2)
        self.assertAlmostEqual(
            self._rates(self.company_usd, "VES", D(2026, 11, 17)).rate, 915.7476, places=9)
        # Running it again does not duplicate anything.
        with self.mock_api(history=HISTORY):
            self._wizard(D(2026, 11, 13), D(2026, 11, 17)).action_backfill()
        self.assertEqual(len(self._rates(self.company_ves, "USD")), 3)

    def test_days_before_history_window_are_fetched_per_day(self):
        days = {"2026-11-10": {"date": "2026-11-10", "effective_date": "2026-11-10",
                               "USD": 905.0}}
        wizard = self._wizard(D(2026, 11, 10), D(2026, 11, 12))
        with self.mock_api(history=HISTORY, days=days) as calls:
            wizard.action_backfill()
        self.assertEqual(calls, ["history.json", "history/2026-11-10.json",
                                 "history/2026-11-11.json"])
        self.assertEqual(sorted(self._rates(self.company_ves, "USD").mapped("name")),
                         [D(2026, 11, 10), D(2026, 11, 12)])

    def test_date_validation(self):
        with self.assertRaises(ValidationError):
            self._wizard(D(2021, 8, 1), D(2021, 9, 1))
        with self.assertRaises(ValidationError):
            self._wizard(D(2022, 1, 1), D(2027, 1, 10))  # > 1830 days
        with self.assertRaises(ValidationError):
            self._wizard(D(2026, 11, 10), D(2026, 11, 1))

    def test_network_failure(self):
        wizard = self._wizard(D(2026, 11, 13), D(2026, 11, 17))
        with self.mock_api(error="connection refused"), self.assertRaises(UserError):
            wizard.action_backfill()
        self.assertFalse(self._rates(self.company_ves))
