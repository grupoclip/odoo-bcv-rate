# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Pure-Python helpers: payload validation and Odoo rate math.

Nothing in this file imports Odoo, so it can be unit-tested on its own.

Conventions
-----------
* BCV Today publishes ``bolivares per 1 unit`` of USD, EUR, CNY, TRY and RUB.
  The bolivar itself (VES) is implicitly ``1``.
* Odoo stores ``res.currency.rate.rate`` as ``units of that currency per
  1 unit of the company currency``.

So, with ``bs[X]`` = bolivares per 1 X, the Odoo rate of a currency ``X`` for
a company whose currency is ``C`` is::

    rate(X) = bs[C] / bs[X]

Examples with USD = 916.6477 and EUR = 1007.3867 Bs:

* company in VES: rate(USD) = 1 / 916.6477 = 0.0010909...
                  rate(EUR) = 1 / 1007.3867
* company in USD: rate(VES) = 916.6477 / 1 = 916.6477
                  rate(EUR) = 916.6477 / 1007.3867 = 0.90992...

No rounding is applied: Odoo declares the ``rate`` field with ``digits=0``,
so PostgreSQL stores it as an unrounded NUMERIC and the value written is the
IEEE-754 double result of the division (15-17 significant digits).
"""
import datetime
import math

#: Foreign currencies published by BCV Today (bolivares per 1 unit).
API_CURRENCIES = ("USD", "EUR", "CNY", "TRY", "RUB")
#: ISO code of the bolivar. VEF (pre-2018 "bolivar fuerte") is accepted as an
#: alias when a database still uses it instead of VES.
BOLIVAR = "VES"
LEGACY_BOLIVAR = "VEF"
#: Every code the module can compute a rate for (bolivar included).
SUPPORTED_CODES = (BOLIVAR,) + API_CURRENCIES
#: First day with data in the BCV Today history.
FIRST_DATE = datetime.date(2021, 8, 2)
#: Maximum number of days the history endpoint returns / a backfill accepts.
MAX_BACKFILL_DAYS = 1830


class BcvDataError(ValueError):
    """The API answered, but the payload is not usable."""


def normalize_code(code):
    """Map the legacy VEF code onto VES; other codes are returned as-is."""
    return BOLIVAR if code == LEGACY_BOLIVAR else code


def parse_date(value):
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise BcvDataError("invalid date: %r" % (value,))


def parse_entry(payload):
    """Validate one API object (latest rate, or one history entry).

    Returns ``(effective_date, rates)`` where ``rates`` maps each currency
    code present in the payload (plus ``VES`` = 1.0) to bolivares per unit.
    Currencies whose value is missing, non-numeric, non-finite or <= 0 are
    left out, never guessed.
    """
    if not isinstance(payload, dict):
        raise BcvDataError("expected a JSON object, got %s" % type(payload).__name__)
    effective = payload.get("effective_date") or payload.get("date")
    effective_date = parse_date(effective)
    rates = {BOLIVAR: 1.0}
    for code in API_CURRENCIES:
        value = payload.get(code)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if math.isfinite(value) and value > 0:
            rates[code] = value
    if len(rates) == 1:
        raise BcvDataError("no usable rate in payload for %s" % effective_date)
    return effective_date, rates


def compute_odoo_rates(bs_per_unit, company_code, target_codes):
    """Compute Odoo ``res.currency.rate.rate`` values.

    :param dict bs_per_unit: code -> bolivares per 1 unit (``VES`` = 1).
    :param str company_code: ISO code of the company currency.
    :param iterable target_codes: codes to compute (VEF is treated as VES).
    :returns: ``(rates, missing)`` - ``rates`` maps each target code (as
        given) to its Odoo rate; ``missing`` lists the codes absent from the
        payload.
    :raises BcvDataError: when the company currency itself is not available.
    """
    company_value = bs_per_unit.get(normalize_code(company_code))
    if not company_value:
        raise BcvDataError("company currency %s not in payload" % company_code)
    rates, missing = {}, []
    for code in target_codes:
        value = bs_per_unit.get(normalize_code(code))
        if not value:
            missing.append(code)
            continue
        rates[code] = company_value / value
    return rates, missing


def select_history(entries, date_from, date_to):
    """Pick one entry per effective date within ``[date_from, date_to]``.

    History lists one entry per calendar day; weekends and holidays repeat
    the previous business day's rate with that day's ``effective_date``.
    Only the effective dates are kept (Odoo reuses the last rate on or before
    any date), so a Saturday never creates a duplicate rate.

    Returns a list of ``(effective_date, rates)`` sorted by date. Invalid
    entries are skipped.
    """
    by_date = {}
    for entry in entries or []:
        try:
            effective_date, rates = parse_entry(entry)
        except BcvDataError:
            continue
        if date_from <= effective_date <= date_to:
            # Keep the richest entry if a date is repeated.
            if len(rates) >= len(by_date.get(effective_date, {})):
                by_date[effective_date] = rates
    return sorted(by_date.items())


def rates_equal(a, b, rel_tol=1e-12):
    return math.isclose(a or 0.0, b or 0.0, rel_tol=rel_tol, abs_tol=0.0)
