# odoo-bcv-rate — Tasa BCV automática para Odoo

Odoo module **`l10n_ve_bcv_rate`**: keeps each company's currency rates updated with the
official **Banco Central de Venezuela** rate (USD, EUR, CNY, TRY, RUB) from the free
[BCV Today API](https://bcv.today). No API key, no extra Python packages.

**Instalar desde la tienda de Odoo / Install from the Odoo Apps Store (free):**
[apps.odoo.com/apps/modules/20.0/l10n_ve_bcv_rate](https://apps.odoo.com/apps/modules/20.0/l10n_ve_bcv_rate)


| Branch | Odoo | Python |
|---|---|---|
| `16.0` | [16.0](https://apps.odoo.com/apps/modules/16.0/l10n_ve_bcv_rate) Community / Enterprise | 3.8+ |
| `17.0` | [17.0](https://apps.odoo.com/apps/modules/17.0/l10n_ve_bcv_rate) Community / Enterprise | 3.10+ |
| `18.0` | [18.0](https://apps.odoo.com/apps/modules/18.0/l10n_ve_bcv_rate) Community / Enterprise | 3.10+ |
| `19.0` | [19.0](https://apps.odoo.com/apps/modules/19.0/l10n_ve_bcv_rate) Community / Enterprise | 3.10+ |
| `20.0` | [20.0](https://apps.odoo.com/apps/modules/20.0/l10n_ve_bcv_rate) Community / Enterprise | 3.12+ |

Works on Odoo.sh and on-premise. **Not available on Odoo Online** (SaaS), which does not
allow third-party modules. Standalone: it does not use Enterprise's `currency_rate_live`.

## Instalación / Install

1. Copy `l10n_ve_bcv_rate/` into your addons path (or add this repository, on the branch
   matching your Odoo version, as a submodule in Odoo.sh).
2. Update the apps list and install **Venezuela - BCV Exchange Rates (BCV Today)**.
3. *Settings › Invoicing/Accounting › Currencies › BCV exchange rates*: enable
   **Automatic BCV rates**, optionally choose currencies and interval, press **Update now**.
4. Optional: **Load history** backfills past value dates (from 2021-08-02, up to 1830 days
   per run, one request to `history.json`).

The server needs outbound HTTPS to `bcv.today`.

## Cómo se calcula / Rate math

BCV publishes **bolivars per 1 unit** of each currency. Odoo stores
`res.currency.rate.rate` as **units of that currency per 1 unit of the company currency**.
With `Bs(X)` = bolivars per 1 X (and `Bs(VES)` = 1):

```
rate(X) = Bs(company currency) / Bs(X)
```

With USD = 916.6477 Bs and EUR = 1007.3867 Bs:

| Company currency | Currency | Stored `rate` | Shown as |
|---|---|---|---|
| VES | USD | 1 / 916.6477 = 0.0010909317 | 916.6477 VES per USD |
| VES | EUR | 1 / 1007.3867 = 0.0009926672 | 1007.3867 VES per EUR |
| USD | VES | 916.6477 | 0.00109093 USD per VES |
| USD | EUR | 916.6477 / 1007.3867 = 0.9099263 | 1.0990 USD per EUR |

Any company currency among VES, USD, EUR, CNY, TRY, RUB works (cross rates through the
bolivar). Other company currencies are skipped with a clear status message. The bolivar is
the currency with code `VES`; databases still using the legacy `VEF` code are accepted
when `VES` is not active.

**Rounding:** none. Odoo declares `rate` with `digits=0` (unrounded `NUMERIC`), so the full
double-precision result of the division is stored; `1 / rate` gives back the BCV value
(e.g. 916.6477000000001). Amounts are rounded only by the currency's own rounding when
converting.

**Dates:** each rate is dated with the API's `effective_date` (BCV *fecha valor*). Running
the update twice for the same value date updates the existing record instead of creating a
duplicate. Weekends/holidays need no record: Odoo uses the latest rate on or before a date.
A currency missing from the API that day is skipped (logged and shown in the status).

## Scheduled action

*BCV Today: update currency rates* runs daily at **03:30 UTC = 23:30 America/Caracas**
(UTC-4, no DST). The BCV publishes the next value date's rate in the afternoon/evening
and BCV Today has it by ~22:30 Caracas, so the rate is in Odoo before its value date
starts. You may run it more often (Settings › Technical › Scheduled Actions): repeated
runs are idempotent. It does nothing until a company enables automatic rates. One API
request serves all companies; each company is processed in its own savepoint; network
or data errors are logged, stored in the status message and the previous rate is kept,
so the cron never fails. Branch companies (17.0+) share their parent's rates, as Odoo
requires.

## Security

Only *Accounting / Administrator* (`account.group_account_manager`) and *Settings*
(`base.group_system`) users can change the settings, press *Update now* or run the
backfill wizard.

## Tests

```
odoo-bin -d test_db -i account,l10n_ve_bcv_rate --test-enable \
  --test-tags /l10n_ve_bcv_rate --stop-after-init
```

The HTTP call is mocked (`bcv.today.client._fetch_json`); tests cover VES and USD
companies, cross rates, idempotent same-date updates, missing currencies, backfill and
network failure. The pure math lives in `models/bcv_math.py` (no Odoo import).

## Relacionado / Related

Otras formas de usar los mismos datos / other ways to use the same data:

- **Todas las integraciones / All integrations:** <https://bcv.today/integraciones/>
  (English: <https://bcv.today/en/integrations/>)
- **Librería Python / Python library** `bcv` (`pip install bcv`, CLI `bcv`):
  <https://pypi.org/project/bcv/>
- **Servidor MCP / MCP server** for AI assistants (Streamable HTTP, no auth):
  `https://mcp.bcv.today/mcp`, setup at <https://bcv.today/en/api/#mcp-server>

## Fuente y licencia / Source and license

**Fuente: Banco Central de Venezuela, vía BCV Today** — <https://bcv.today>. Data is
published under **CC BY 4.0**: keep the attribution when redistributing it. BCV Today is
an independent, unofficial service, not affiliated with the Banco Central de Venezuela.

Module code: **LGPL-3** (see `LICENSE`).
