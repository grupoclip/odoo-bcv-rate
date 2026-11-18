# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import datetime
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..models.bcv_client import BcvFetchError
from ..models.bcv_math import (
    FIRST_DATE,
    MAX_BACKFILL_DAYS,
    BcvDataError,
    parse_entry,
    select_history,
)
from ..models.res_company import caracas_today

_logger = logging.getLogger(__name__)

#: Days older than the rolling window of history.json are fetched one by one
#: from history/{date}.json; this caps how many such requests one run makes.
MAX_DAY_REQUESTS = 400


class BcvRateBackfill(models.TransientModel):
    _name = "bcv.rate.backfill"
    _description = "Load historical BCV rates"

    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: caracas_today() - datetime.timedelta(days=30),
    )
    date_to = fields.Date(string="To", required=True, default=lambda self: caracas_today())
    company_ids = fields.Many2many(
        "res.company",
        string="Companies",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from < FIRST_DATE:
                raise ValidationError(
                    _(
                        "BCV Today has data from %(date)s onwards.", date=FIRST_DATE
                    )
                )
            if wizard.date_to < wizard.date_from:
                raise ValidationError(
                    _("The end date must be on or after the start date.")
                )
            if (wizard.date_to - wizard.date_from).days + 1 > MAX_BACKFILL_DAYS:
                raise ValidationError(
                    _(
                        "Load at most %(days)s days at a time.", days=MAX_BACKFILL_DAYS
                    )
                )

    def _bcv_collect_entries(self):
        """Return ``[(effective_date, bs_rates)]`` for the wizard's range.

        ``history.json`` is fetched once. Only the days that fall before its
        rolling window (it holds the latest 1830 days) are requested one by
        one from ``history/{date}.json``.
        """
        self.ensure_one()
        client = self.env["bcv.today.client"]
        history = client.fetch_history()
        dates = []
        for entry in history:
            try:
                dates.append(parse_entry(entry)[0])
            except BcvDataError:
                continue
        window_start = min(dates) if dates else self.date_to + datetime.timedelta(days=1)
        extra = []
        if self.date_from < window_start:
            last = min(self.date_to, window_start - datetime.timedelta(days=1))
            count = (last - self.date_from).days + 1
            if count > MAX_DAY_REQUESTS:
                raise UserError(
                    _(
                        "Dates before %(date)s are loaded one day at a time; choose a "
                        "range with at most %(count)s such days.",
                        date=window_start,
                        count=MAX_DAY_REQUESTS,
                    )
                )
            day = self.date_from
            while day <= last:
                try:
                    extra.append(client.fetch_day(day))
                except BcvFetchError as error:
                    _logger.info("BCV Today: no data for %s (%s)", day, error)
                day += datetime.timedelta(days=1)
        return select_history(history + extra, self.date_from, self.date_to)

    def action_backfill(self):
        self.ensure_one()
        self.env["res.company"]._bcv_check_manager()
        try:
            entries = self._bcv_collect_entries()
        except BcvFetchError as error:
            raise UserError(
                _("BCV Today could not be read: %(error)s", error=error)
            ) from error
        if not entries:
            raise UserError(_("BCV Today has no rates in the selected range."))

        lines = []
        for company in self.company_ids:
            totals = {"created": 0, "updated": 0, "unchanged": 0, "missing": 0}
            try:
                with self.env.cr.savepoint():
                    for effective_date, bs_rates in entries:
                        result = company._bcv_apply_entry(effective_date, bs_rates)
                        for key in ("created", "updated", "unchanged"):
                            totals[key] += result[key]
                        totals["missing"] += len(result["missing"])
            except BcvDataError as error:
                lines.append("%s: %s" % (company.name, error))
                continue
            lines.append(
                _(
                    "%(company)s: %(days)s value dates, %(created)s rates created, "
                    "%(updated)s updated, %(unchanged)s unchanged, %(missing)s "
                    "currency/day pairs not published.",
                    company=company.name,
                    days=len(entries),
                    **totals
                )
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("BCV history loaded"),
                "message": "\n".join(lines),
                "type": "success",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
