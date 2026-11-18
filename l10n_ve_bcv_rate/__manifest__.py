# Part of l10n_ve_bcv_rate. License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Venezuela - BCV Exchange Rates (BCV Today)",
    "summary": "Daily official Banco Central de Venezuela rates (USD, EUR, CNY, TRY, RUB) "
               "from the free BCV Today API. Tasa BCV automática.",
    "version": "16.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "BCV Today",
    "website": "https://bcv.today",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "wizard/bcv_rate_backfill_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": False,
}
