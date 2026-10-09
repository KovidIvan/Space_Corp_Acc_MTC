# Dev B B8 completion

## Delivered

- Added authenticated `/stats` and `/api/stats` with total calls, intent and urgency breakdowns, handled/unhandled counts, and an explicitly estimated five minutes saved per handled call.
- Added retention and default-off `store_audio` settings to the existing versioned AgentConfig editor. The retention worker runs once at startup and every 24 hours; expired completed calls and their chat records are removed, with an audit event.
- Added a confirmed delete-all action that removes calls and related chat records while preserving the audit log. Demo fixtures are not re-seeded after an explicit or retention purge.
- Added `/audit` and `/api/audit`, displaying recent events and checking the persisted hash chain.
- Added an offline guard test proving a non-allowlisted URL is rejected before reaching the HTTP transport.

## Validation

- `python -m pytest -q`: 130 passed, 7 skipped; one upstream Starlette/httpx deprecation warning.
- `python -m ruff check app tests`: passed.
- `python -m compileall -q app tests`: passed.

## Limits

The project does not currently capture or persist raw audio; `store_audio` is only persisted as a configuration preference and defaults to off. The five-minute savings number is a displayed estimate, not a measured benchmark. B7's runtime working-hours integration remains with Dev A.
