# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import datetime
from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.bcv_client import BcvFetchError

USD = 916.6477
EUR = 1007.38665582
LATEST = {
    "USD": USD,
    "EUR": EUR,
    "CNY": 137.52328442,
    "TRY": 18.21021713,
    "RUB": 11.17192733,
    "updated_at": "2026-11-18T02:01:03.699523+00:00",
    "effective_date": "2026-11-18",
    "date": "2026-11-18",
}
VALUE_DATE = datetime.date(2026, 11, 18)


class BcvCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Isolate from companies of the test database that may have it enabled.
        cls.env["res.company"].search([]).write({"bcv_auto_update": False})
        Currency = cls.env["res.currency"].with_context(active_test=False)
        cls.cur = {}
        for code in ("VES", "USD", "EUR", "CNY", "TRY", "RUB", "COP"):
            currency = Currency.search([("name", "=", code)], limit=1)
            currency.active = True
            cls.cur[code] = currency
        cls.cur["VEF"] = Currency.search([("name", "=", "VEF")], limit=1)
        cls.cur["VEF"].active = False
        cls.company_ves = cls._make_company("BCV Bs company", "VES")
        cls.company_usd = cls._make_company("BCV USD company", "USD")

    @classmethod
    def _make_company(cls, name, code):
        return cls.env["res.company"].create({"name": name, "currency_id": cls.cur[code].id})

    def _rates(self, company, code=None, date=None):
        domain = [("company_id", "=", company.id)]
        if code:
            domain.append(("currency_id", "=", self.cur[code].id))
        if date:
            domain.append(("name", "=", date))
        return self.env["res.currency.rate"].search(domain)

    @contextmanager
    def mock_api(self, latest=None, history=None, days=None, error=None):
        """Patch the single network entry point of the module.

        ``days`` maps 'YYYY-MM-DD' to the payload of history/{date}.json.
        """
        calls = []

        def fake_fetch(model, path):
            calls.append(path)
            if error:
                raise BcvFetchError(error)
            if path == "rate.json":
                return dict(LATEST if latest is None else latest)
            if path == "history.json":
                return list(history or [])
            if path.startswith("history/") and days is not None:
                key = path[len("history/"):-len(".json")]
                if key in days:
                    return days[key]
            raise BcvFetchError("HTTP 404 for %s" % path)

        Client = type(self.env["bcv.today.client"])
        with patch.object(Client, "_fetch_json", autospec=True, side_effect=fake_fetch):
            yield calls
