# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import datetime
import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .bcv_client import BcvFetchError
from .bcv_math import (
    API_CURRENCIES,
    BOLIVAR,
    LEGACY_BOLIVAR,
    SUPPORTED_CODES,
    BcvDataError,
    compute_odoo_rates,
    normalize_code,
    parse_entry,
    rates_equal,
)

_logger = logging.getLogger(__name__)

#: Venezuela has used UTC-4 all year round since 2016 (no DST).
CARACAS_UTC_OFFSET = datetime.timedelta(hours=-4)


def caracas_today():
    return (datetime.datetime.now(datetime.timezone.utc) + CARACAS_UTC_OFFSET).date()


class ResCompany(models.Model):
    _inherit = "res.company"

    bcv_auto_update = fields.Boolean(
        string="Automatic BCV rates",
        help="Update this company's currency rates every day with the official "
        "Banco Central de Venezuela rate published by BCV Today.",
    )
    bcv_interval = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        string="BCV update interval",
        default="daily",
        required=True,
    )
    bcv_next_update = fields.Date(
        string="Next BCV update",
        copy=False,
        help="Weekly/monthly intervals only: first day on which the scheduled "
        "action updates the rates again. Empty means on its next run.",
    )
    bcv_currency_ids = fields.Many2many(
        "res.currency",
        "res_company_bcv_currency_rel",
        "company_id",
        "currency_id",
        string="Currencies updated from BCV",
        help="Leave empty to update every active currency published by the BCV "
        "(USD, EUR, CNY, TRY, RUB, and the bolivar when the company currency "
        "is not the bolivar).",
    )
    bcv_last_sync = fields.Datetime(string="Last BCV update", readonly=True, copy=False)
    bcv_last_effective_date = fields.Date(
        string="Last BCV value date", readonly=True, copy=False
    )
    bcv_last_status = fields.Char(string="Last BCV result", readonly=True, copy=False)

    def write(self, vals):
        # A new schedule starts on the next cron run; saving the settings
        # again with the same values does not reset it.
        rescheduled = self.filtered(
            lambda c: any(
                key in vals and c[key] != vals[key]
                for key in ("bcv_auto_update", "bcv_interval")
            )
        )
        res = super().write(vals)
        if rescheduled and "bcv_next_update" not in vals:
            super(ResCompany, rescheduled).write({"bcv_next_update": False})
        return res

    # ------------------------------------------------------------------
    # Currency selection
    # ------------------------------------------------------------------
    def _bcv_rate_company(self):
        """Company that owns the rates (branches share their root's rates)."""
        self.ensure_one()
        return self.root_id or self

    def _bcv_company_code(self):
        """BCV code of the company currency, or False when not supported."""
        self.ensure_one()
        code = normalize_code(self.currency_id.name)
        return code if code in SUPPORTED_CODES else False

    def _bcv_bolivar_currency(self):
        """The bolivar record to write rates on (VES, or legacy VEF)."""
        self.ensure_one()
        if self.currency_id.name in (BOLIVAR, LEGACY_BOLIVAR):
            return self.currency_id
        Currency = self.env["res.currency"]
        ves = Currency.search([("name", "=", BOLIVAR)], limit=1)
        if ves:
            return ves
        return Currency.search([("name", "=", LEGACY_BOLIVAR)], limit=1)

    def _bcv_available_currencies(self):
        """Active currencies this company can receive BCV rates for."""
        self.ensure_one()
        if not self._bcv_company_code():
            return self.env["res.currency"]
        currencies = self.env["res.currency"].search([("name", "in", API_CURRENCIES)])
        currencies |= self._bcv_bolivar_currency()
        return currencies - self.currency_id

    def _bcv_target_currencies(self):
        self.ensure_one()
        available = self._bcv_available_currencies()
        if self.bcv_currency_ids:
            return self.bcv_currency_ids & available
        return available

    # ------------------------------------------------------------------
    # Writing rates
    # ------------------------------------------------------------------
    def _bcv_apply_entry(self, effective_date, bs_rates):
        """Create/update one rate per target currency dated ``effective_date``.

        :param bs_rates: bolivares per unit, as returned by ``parse_entry``.
        :returns: dict with ``created``, ``updated``, ``unchanged`` counts and
            the list of ``missing`` currency codes.
        :raises BcvDataError: the company currency is not supported.
        """
        self.ensure_one()
        company_code = self._bcv_company_code()
        if not company_code:
            raise BcvDataError(
                self.env._(
                    "The company currency %(currency)s is not published by the BCV; "
                    "nothing was updated.",
                    currency=self.currency_id.name,
                )
            )
        targets = self._bcv_target_currencies()
        if not targets:
            raise BcvDataError(
                self.env._(
                    "No active currency to update: activate VES, USD, EUR, CNY, TRY or "
                    "RUB in the currencies list."
                )
            )
        rates, missing = compute_odoo_rates(bs_rates, company_code, targets.mapped("name"))
        Rate = self.env["res.currency.rate"].sudo()
        existing = {
            rate.currency_id.id: rate
            for rate in Rate.search(
                [
                    ("company_id", "=", self.id),
                    ("name", "=", effective_date),
                    ("currency_id", "in", targets.ids),
                ]
            )
        }
        result = {"created": 0, "updated": 0, "unchanged": 0, "missing": missing}
        to_create = []
        for currency in targets:
            if currency.name not in rates:
                _logger.info(
                    "BCV Today: no %s rate for %s, skipped (company %s)",
                    currency.name, effective_date, self.name,
                )
                continue
            value = rates[currency.name]
            record = existing.get(currency.id)
            if not record:
                to_create.append(
                    {
                        "name": effective_date,
                        "currency_id": currency.id,
                        "company_id": self.id,
                        "rate": value,
                    }
                )
            elif rates_equal(record.rate, value):
                result["unchanged"] += 1
            else:
                record.write({"rate": value})
                result["updated"] += 1
        if to_create:
            Rate.create(to_create)
            result["created"] = len(to_create)
        return result

    def _bcv_result_message(self, effective_date, result):
        message = self.env._(
            "BCV rates of %(date)s: %(created)s created, %(updated)s updated, "
            "%(unchanged)s unchanged.",
            date=effective_date,
            created=result["created"],
            updated=result["updated"],
            unchanged=result["unchanged"],
        )
        if result["missing"]:
            message += " " + self.env._(
                "Not published that day: %(codes)s.", codes=", ".join(result["missing"])
            )
        return message

    def _bcv_check_manager(self):
        if self.env.su or self.env.user.has_group("account.group_account_manager") \
                or self.env.user.has_group("base.group_system"):
            return
        raise AccessError(
            self.env._("Only accounting managers can update or load BCV rates.")
        )

    def bcv_update_rates(self):
        """Fetch the latest BCV rates once and apply them to every company.

        Never raises on network or data problems: the previous rates stay in
        place and the reason is stored in ``bcv_last_status`` and logged.

        :returns: dict ``{company: (ok, message)}``.
        """
        now = fields.Datetime.now()
        messages = {}
        try:
            payload = self.env["bcv.today.client"].fetch_latest()
            effective_date, bs_rates = parse_entry(payload)
        except (BcvFetchError, BcvDataError) as error:
            _logger.warning("BCV Today: update failed, previous rates kept: %s", error)
            message = self.env._(
                "BCV Today could not be read (%(error)s). Previous rates were kept.",
                error=error,
            )
            for company in self:
                messages[company] = (False, message)
            self.sudo().write({"bcv_last_sync": now, "bcv_last_status": message})
            return messages

        for company in self:
            ok = True
            values = {"bcv_last_sync": now}
            try:
                with self.env.cr.savepoint():
                    result = company._bcv_apply_entry(effective_date, bs_rates)
                values["bcv_last_effective_date"] = effective_date
                message = company._bcv_result_message(effective_date, result)
            except BcvDataError as error:
                ok = False
                message = str(error)
                _logger.warning("BCV Today: company %s skipped: %s", company.name, error)
            except Exception as error:  # never break the cron queue
                ok = False
                _logger.exception("BCV Today: company %s failed", company.name)
                message = self.env._(
                    "Unexpected error, previous rates were kept: %(error)s", error=error
                )
            values["bcv_last_status"] = message
            company.sudo().write(values)
            messages[company] = (ok, message)
        return messages

    @api.model
    def _cron_bcv_update_rates(self):
        """Scheduled action: update every company that enabled BCV rates."""
        today = caracas_today()
        companies = self.sudo().search(
            [("bcv_auto_update", "=", True), ("parent_id", "=", False)]
        )
        due = companies.filtered(
            lambda c: not c.bcv_next_update or c.bcv_next_update <= today
        )
        if not due:
            return
        try:
            results = due.bcv_update_rates()
        except Exception:  # last-resort guard: never break the cron queue
            _logger.exception("BCV Today: scheduled update failed")
            return
        for company, (ok, __) in results.items():
            if ok and company.bcv_interval in ("weekly", "monthly"):
                delta = relativedelta(weeks=1) if company.bcv_interval == "weekly" \
                    else relativedelta(months=1)
                company.write({"bcv_next_update": today + delta})
