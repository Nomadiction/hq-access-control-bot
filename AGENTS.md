# Agent Guidance

Keep guidance lean: add a rule only when it is not obvious from the code.

## Quality gate

Run before finishing any change. CI runs the same checks on Python 3.12 and 3.14.

```bash
ruff format --check .
ruff check .
pytest -q
```

## Boundaries

- This repository is public. Real Telegram IDs, usernames and project names stay in `data/` and
  never reach code, tests, docs or commit messages. Tests use made-up data.
- Tests run offline through the real dispatcher with `RecordingSession` from `tests/support.py`.
  Never start the bot from a checkout that has a real `.env`.
- A new test must be seen failing with the rule it protects broken.

## Layout rules

- `hq_access_bot/whitelist/` imports nothing from aiogram. Telegram types stop in
  `hq_access_bot/handlers/` and are converted by `telegram_mapping.py`.
- Every change to the access list goes through `WhitelistStore.transaction()`. Make network calls
  after the block exits, because the lock is held inside it.
- Messages shown to Telegram users live in `hq_access_bot/texts.py` and `bot_profile.py` and are in
  Russian. Everything else is in English.
- The JSON keys of `whitelist.json` (`project`, `members`, `id`, `username`, `in`, `name`) are the
  on-disk format of live data. Changing them needs a migration.

## Commits

`<type>(<scope>): <lowercase sentence>`, for example
`fix(api): a line goes back into stock once and only when picked`.

One line only: no body and no trailers, including AI attribution. One logical change per commit,
straight to `main`.
