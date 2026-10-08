# Design

## Reversible, not Odoo's SQL

The instance manager runs every installed module's `data/neutralize.sql` first: its copies never go back to
production. Here a copy may be given back, so every change goes through a rule that records the value before
writing it.

Where Odoo deletes, the rule writes an inert value instead, and the copy's behaviour is the same:

| Odoo deletes | Here |
|---|---|
| `mail.web_push_vapid_*`, `mail.sfu_server_key` | value `''` (Odoo regenerates its own keys when a push is next sent) |
| push devices (`mail_partner_device` 17.0, `mail_push_device` 18.0–19.0) | `endpoint` set to an address that does not resolve |
| `cloud_storage_*` parameters | value `''` (no provider) |

Queued pushes (`mail_notification_web_push`, `mail_push`) are left alone: they are sent to a device's
endpoint, which no longer resolves.

## The EDI proxy parameter

14.0–16.0 read `account_edi_proxy_client.demo`, and a missing parameter means production
(`_get_demo_state`). An existing `prod` value is updated by a rule and recorded. A missing parameter is added
by an `Insert`, which restore deletes. The `Insert` runs only where the proxy table exists without `edi_mode`,
so 17.0+ never gets it. The check reports `edi-proxy-demo` when that era's parameter is missing or `prod`.

## Mail on 12.0–15.0

`mail_message.mail_server_id` of messages with a pending `mail_mail` (`outgoing`, `exception`) is cleared, and
the value is recorded. Odoo then picks the capture server, as for any other mail.
