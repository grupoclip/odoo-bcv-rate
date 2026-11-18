# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import bcv_math
from .common import EUR, LATEST, USD


@tagged("post_install", "-at_install")
class TestRateMath(TransactionCase):
    """Pure functions, no database access."""

    def test_parse_entry(self):
        effective_date, rates = bcv_math.parse_entry(LATEST)
        self.assertEqual(effective_date, datetime.date(2026, 11, 18))
        self.assertEqual(rates["VES"], 1.0)
        self.assertEqual(rates["USD"], USD)
        self.assertEqual(set(rates), {"VES", "USD", "EUR", "CNY", "TRY", "RUB"})

    def test_parse_entry_rejects_bad_values(self):
        _date, rates = bcv_math.parse_entry(
            {"effective_date": "2026-01-02", "USD": 10.0, "EUR": -1, "CNY": "3", "TRY": True,
             "RUB": float("nan")}
        )
        self.assertEqual(set(rates), {"VES", "USD"})
        with self.assertRaises(bcv_math.BcvDataError):
            bcv_math.parse_entry({"effective_date": "2026-01-02"})
        with self.assertRaises(bcv_math.BcvDataError):
            bcv_math.parse_entry({"effective_date": "02/01/2026", "USD": 1})
        with self.assertRaises(bcv_math.BcvDataError):
            bcv_math.parse_entry(["USD", 1])

    def test_company_in_bolivars(self):
        _date, bs = bcv_math.parse_entry(LATEST)
        rates, missing = bcv_math.compute_odoo_rates(bs, "VES", ["USD", "EUR"])
        self.assertEqual(missing, [])
        self.assertAlmostEqual(rates["USD"], 1 / 916.6477, places=15)
        self.assertAlmostEqual(1 / rates["USD"], 916.6477, places=9)
        self.assertAlmostEqual(1 / rates["EUR"], EUR, places=9)

    def test_company_in_legacy_vef(self):
        _date, bs = bcv_math.parse_entry(LATEST)
        rates, _missing = bcv_math.compute_odoo_rates(bs, "VEF", ["USD"])
        self.assertAlmostEqual(rates["USD"], 1 / USD, places=15)

    def test_company_in_dollars(self):
        _date, bs = bcv_math.parse_entry(LATEST)
        rates, _missing = bcv_math.compute_odoo_rates(bs, "USD", ["VES", "EUR"])
        self.assertAlmostEqual(rates["VES"], 916.6477, places=9)
        self.assertAlmostEqual(rates["EUR"], USD / EUR, places=15)
        self.assertAlmostEqual(rates["EUR"], 0.909926, places=6)

    def test_cross_rates_other_company_currency(self):
        _date, bs = bcv_math.parse_entry(LATEST)
        rates, _missing = bcv_math.compute_odoo_rates(bs, "EUR", ["USD", "VES", "CNY"])
        self.assertAlmostEqual(rates["USD"], EUR / USD, places=15)
        self.assertAlmostEqual(rates["VES"], EUR, places=9)
        self.assertAlmostEqual(rates["CNY"], EUR / 137.52328442, places=12)

    def test_missing_currency_and_unsupported_company(self):
        rates, missing = bcv_math.compute_odoo_rates({"VES": 1.0, "USD": USD}, "VES", ["USD", "EUR"])
        self.assertEqual(list(rates), ["USD"])
        self.assertEqual(missing, ["EUR"])
        with self.assertRaises(bcv_math.BcvDataError):
            bcv_math.compute_odoo_rates({"VES": 1.0, "USD": USD}, "COP", ["USD"])

    def test_select_history_uses_value_dates(self):
        entries = [
            {"date": "2026-11-13", "effective_date": "2026-11-13", "USD": 911.6243},
            {"date": "2026-11-14", "effective_date": "2026-11-13", "USD": 911.6243},
            {"date": "2026-11-15", "effective_date": "2026-11-13", "USD": 911.6243},
            {"date": "2026-11-16", "effective_date": "2026-11-16", "USD": 914.0218},
            {"date": "2026-11-17", "effective_date": "2026-11-17", "USD": 915.7476},
            {"broken": True},
        ]
        selected = bcv_math.select_history(
            entries, datetime.date(2026, 11, 13), datetime.date(2026, 11, 16)
        )
        self.assertEqual([d for d, _r in selected],
                         [datetime.date(2026, 11, 13), datetime.date(2026, 11, 16)])
