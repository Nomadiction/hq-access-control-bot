# HQ Access Control Bot

A Telegram bot that controls entry to private project work groups. It receives a join request,
checks the person against that group's access list and immediately approves or declines it.
Admins are notified of every decision.

The messages the bot sends to Telegram users are in Russian.

## How it works

1. An invite link that requires join requests is created in the group.
2. A user opens the link and files a request, and Telegram sends the bot an event.
3. The bot looks the person up in the group's access list:
   - listed: the request is approved and the person gets a welcome message;
   - not listed: the request is declined and admins see who tried to enter and where.
4. If the person later leaves the group or is removed, the bot takes them off the list.

A group that is not in the list declines everyone.

## Requirements

- Python 3.12 or newer.
- A bot created with [@BotFather](https://t.me/BotFather).
- Supergroups only: basic groups have no join requests.
- In every group the bot must be an administrator with the right to invite users. Without
  admin rights Telegram does not send the bot join requests or membership changes.

## Getting started

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
venv/bin/python -m hq_access_bot
```

On Windows, create `.env` and run `run.bat`.

Only one copy of the bot can run per token, otherwise Telegram returns error 409. A second
launch from the same folder is refused at startup.

### Running on a server

A sample systemd unit is in [deploy/hqbot.service](deploy/hqbot.service). It assumes the
directory `/opt/hq-access-bot` and the user `hqbot`.

```bash
sudo cp deploy/hqbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hqbot
journalctl -u hqbot -f
```

Keep the `data/` directory across updates and when moving to another server.

## Configuration

Values come from environment variables, then from the `.env` file in the project root.

| Variable           | Required | Default | Purpose                                 |
|--------------------|----------|---------|-----------------------------------------|
| `BOT_TOKEN`        | yes      | none    | Bot token.                              |
| `SUPPORT_USERNAME` | yes      | none    | Support contact shown to users.         |
| `ADMIN_IDS`        | no       | empty   | Comma-separated Telegram IDs of admins. |

Without `ADMIN_IDS` the bot runs, but admin commands and notifications are unavailable.
Restart the bot after changing the configuration.

## Commands

Available to everyone:

| Command           | Action                               |
|-------------------|--------------------------------------|
| `/start`          | Show help. Admins get the control panel in a private chat. |
| `/help`           | Show help.                           |
| `/me`             | Show your numeric ID.                |
| `/id`             | Show the `chat_id` of the current chat. |
| `/clear`          | Clear up to 1000 recent messages in your chat with the bot. |

Admins only, in a private chat with the bot:

| Command                                       | Action                                |
|-----------------------------------------------|---------------------------------------|
| `/add <project\|chat_id> <@user\|id> [...]`    | Add members.                          |
| `/remove <project\|chat_id> <@user\|id> [...]` | Remove members.                       |
| `/delgroup <project\|chat_id>`                 | Remove a group from the list.         |
| `/reload`                                     | Sync the list with Telegram, show it. |
| `/status`                                     | Uptime, group and member counts.      |

The control panel does the same work with buttons: it shows groups, members and the bot's status,
adds and removes members, deletes a group after a confirmation, syncs the list with Telegram and
clears the chat. Its buttons change one message in place instead of adding new ones.

The bot description and command menus are set at startup.

## Access list

The file is `data/whitelist.json`, keyed by the group's `chat_id`:

```json
{
  "-1001234567890": {
    "project": "Alpha",
    "members": [
      {"id": 123456789, "username": "ivan", "in": true, "name": "Ivan"},
      {"username": "pending_user"}
    ]
  }
}
```

| Field      | Meaning                                                  |
|------------|----------------------------------------------------------|
| `id`       | Numeric Telegram ID, the primary and reliable identifier. |
| `username` | Username without `@`, in lowercase.                      |
| `in`       | `true` if the person has already been in the group.      |
| `name`     | Display name, helps identify people without a username.  |

Every member needs at least an `id` or a `username`. A group with `"inactive": true` keeps its
list while the bot is not in that group.

What the bot maintains by itself:

- When added to a supergroup, it creates an empty record and notifies admins.
- A person added by username is bound to their numeric ID on entry.
- Once a record has an ID, only the ID counts: someone who takes over a freed username gets
  no access.
- People who leave or are removed are taken off the list.
- If the bot is removed from a group, the list is kept and comes back when the bot returns.
  `/delgroup` deletes it for good.
- A new group title becomes the project name.
- Admins are warned when someone outside the list enters a group, for example through a plain
  invite link.

The file is re-read for every request, so manual edits apply without a restart. If the file
is missing or corrupted, the bot refuses to start, and while running it neither decides on
requests nor overwrites the file, and alerts admins instead. The file is created empty only on
the very first start, recognised by the absence of `data/access.log`.

When two groups share a name, commands ask for the `chat_id`. Usernames in `/add` and
`/remove` may be separated by spaces or commas.

## Data and logs

The `data/` directory is created at startup and is not stored in git.

| File             | Contents                                                       |
|------------------|----------------------------------------------------------------|
| `whitelist.json` | The access list.                                               |
| `access.log`     | Audit of requests and list changes. Rotated at 1 MB, 3 archives. |
| `hqbot.lock`     | Lock against a second launch.                                  |

Telegram keeps updates received while the bot is off for 24 hours, and the bot processes them
at startup. Older requests have to be filed again.

## Troubleshooting

| Symptom                                | Cause and fix                                       |
|----------------------------------------|-----------------------------------------------------|
| `TelegramConflictError` / 409          | A second copy is running with the same token.       |
| `BOT_TOKEN is empty`                   | `.env` is missing or does not set the value.        |
| `whitelist.json is missing or corrupted` | Fix the file by hand or restore it from a backup. |
| Requests are not processed             | The bot needs admin rights with Invite Users.       |
| Declined although the person is listed | Check `/reload`. Adding by numeric ID is more reliable. |

A person who files a join request is told the decision by direct message even without
pressing Start, because Telegram allows that for 5 minutes while the request is open. Requests
older than that, for example after downtime, are still decided, but without the message. A
decision Telegram rejects or that fails repeatedly is reported to admins, who then handle the
request by hand.

If the token leaks, revoke it with `/revoke` at @BotFather and update `.env`.

## Project layout

```text
hq_access_bot/
├── app.py            application assembly and polling startup
├── config.py         settings and data paths
├── errors.py         base type for fatal failures
├── texts.py          all bot messages
├── audit_log.py      access audit
├── notifier.py       direct message delivery
├── telegram_retry.py retries for Telegram calls that must not be lost
├── history_cleaner.py chat history cleanup
├── services.py       handler dependencies
├── bot_profile.py    bot description and menus
├── instance_lock.py  guard against a second instance
├── handlers/         Telegram event and command handlers
└── whitelist/        list model, file format and storage
tests/                tests through the real dispatcher, offline
deploy/               sample systemd unit
```

## Development

```bash
pip install -r requirements-dev.txt
ruff format .
ruff check .
pytest
```

## License

[MIT](LICENSE)
