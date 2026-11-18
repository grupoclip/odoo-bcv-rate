# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import json
import logging
import urllib.error
import urllib.request

from odoo import api, models

_logger = logging.getLogger(__name__)

MODULE_VERSION = "20.0.1.0.0"
API_BASE = "https://bcv.today/api/v1"
USER_AGENT = "odoo-l10n_ve_bcv_rate/%s (+https://bcv.today)" % MODULE_VERSION
TIMEOUT = 20  # seconds


class BcvFetchError(Exception):
    """Network/HTTP/JSON problem while talking to BCV Today."""


class BcvTodayClient(models.AbstractModel):
    """Thin HTTP client for the free BCV Today API (no authentication).

    Every network access goes through :meth:`_fetch_json`, which the tests
    patch, so nothing else in the module performs I/O.
    """

    _name = "bcv.today.client"
    _description = "BCV Today API client"

    @api.model
    def _fetch_json(self, path):
        url = "%s/%s" % (API_BASE, path.lstrip("/"))
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            raise BcvFetchError("HTTP %s for %s" % (error.code, url)) from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise BcvFetchError("%s: %s" % (url, error)) from error
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError as error:
            raise BcvFetchError("invalid JSON from %s" % url) from error

    @api.model
    def fetch_latest(self):
        """Latest published rates (``rate.json``)."""
        return self._fetch_json("rate.json")

    @api.model
    def fetch_history(self):
        """Up to 1830 daily entries, oldest first (``history.json``)."""
        data = self._fetch_json("history.json")
        if not isinstance(data, list):
            raise BcvFetchError("history.json: expected a list")
        return data

    @api.model
    def fetch_day(self, day):
        """Rates for one calendar day (``history/YYYY-MM-DD.json``)."""
        return self._fetch_json("history/%s.json" % day.strftime("%Y-%m-%d"))
