# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    bcv_auto_update = fields.Boolean(related="company_id.bcv_auto_update", readonly=False)
    bcv_interval = fields.Selection(related="company_id.bcv_interval", readonly=False)
    bcv_currency_ids = fields.Many2many(related="company_id.bcv_currency_ids", readonly=False)
    bcv_available_currency_ids = fields.Many2many(
        "res.currency",
        string="Available BCV currencies",
        compute="_compute_bcv_available_currency_ids",
    )
    bcv_company_supported = fields.Boolean(
        string="Company currency published by the BCV",
        compute="_compute_bcv_available_currency_ids",
    )
    bcv_last_sync = fields.Datetime(related="company_id.bcv_last_sync")
    bcv_last_effective_date = fields.Date(related="company_id.bcv_last_effective_date")
    bcv_last_status = fields.Char(related="company_id.bcv_last_status")

    @api.depends("company_id", "company_id.currency_id")
    def _compute_bcv_available_currency_ids(self):
        for settings in self:
            company = settings.company_id
            settings.bcv_company_supported = bool(company._bcv_company_code())
            settings.bcv_available_currency_ids = company._bcv_available_currencies()

    def action_bcv_update_now(self):
        self.ensure_one()
        company = self.company_id._bcv_rate_company()
        company._bcv_check_manager()
        ok, message = company.bcv_update_rates()[company]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("BCV rates"),
                "message": message,
                "type": "success" if ok else "warning",
                "sticky": not ok,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
