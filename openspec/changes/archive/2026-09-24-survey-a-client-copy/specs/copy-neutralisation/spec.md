# Spec Delta

## ADDED Requirements

### Requirement: Each rule declares how serious what it guards is

Every rule of the neutralisation catalogue SHALL declare a severity: `critical`, `high`, `medium`, `low` or
`info`. The severity is how much harm the thing the rule turns off could do from a copy. Whatever reports
what a copy can act on SHALL rank it by that severity, and SHALL NOT invent its own.

The declared severities are:

| Severity | Rules |
|---|---|
| **critical** | Tax and EDI submissions, and payment providers in production mode |
| **high** | Crons, queued jobs, delivery carriers, webhooks, OAuth and calendar synchronisation |
| **medium** | IAP accounts, mail templates bound to a server, the base URL and website domain |
| **low** or **info** | Identity flags, such as the `database.is_neutralized` banner or the uuid |

#### Scenario: A survey of a production copy

- **WHEN** a copy has an active cron and a tax integration in production mode
- **THEN** the tax integration's finding is critical and the cron's is high, as the catalogue declares
