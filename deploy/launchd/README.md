# Bot supervision (macOS / launchd)

The bot runs as a bare `python main.py` process supervised by a launchd
LaunchAgent. The agent starts the bot at login and restarts it on crash, so a
Mac reboot/sleep or an unhandled exception no longer silently kills the service.

Postgres and Redis run in `docker compose` (`restart: unless-stopped`) and are
reached over `127.0.0.1`. On boot the bot may crash-loop for a few seconds until
those containers are healthy — launchd retries every 10s (`ThrottleInterval`).

> **Prerequisite:** enable *Docker Desktop → Settings → General → Start Docker
> Desktop when you sign in*, otherwise the DB/Redis containers won't be up at
> login and the bot will keep restarting until you start Docker manually.

## Install

`com.unlock.vpnbot.plist` here is a template. Generate the real agent (fills the
DB credentials from `.env`) and load it:

```sh
UID=$(id -u)
mkdir -p ~/Library/Logs/unlock-vpnbot
DB_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-)
sed "s#postgresql+asyncpg://__DB_USER__:__DB_PASSWORD__@127.0.0.1:5432/vpn_bot#${DB_URL/postgres:5432/127.0.0.1:5432}#" \
  deploy/launchd/com.unlock.vpnbot.plist > ~/Library/LaunchAgents/com.unlock.vpnbot.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.unlock.vpnbot.plist
```

If `.env` already uses `127.0.0.1` for the DB, just hand-edit the two
placeholders instead of the `sed` rewrite.

## Manage

```sh
UID=$(id -u)
launchctl print gui/$UID/com.unlock.vpnbot     # status, pid, run count
launchctl kickstart -k gui/$UID/com.unlock.vpnbot   # restart now (apply code/.env changes)
launchctl bootout gui/$UID/com.unlock.vpnbot   # stop and unload
tail -f ~/Library/Logs/unlock-vpnbot/bot.err.log    # live logs (INFO -> stderr)
```

## Notes

- **Single instance only.** launchd guarantees one process per label. Do **not**
  also start the bot manually (`nohup python main.py`) — two long-poll instances
  cause Telegram `409 Conflict`. Use `kickstart -k` to restart.
- After editing `main.py`/handlers or `.env`, apply with `kickstart -k`.
- After editing the plist itself, `bootout` then `bootstrap` again.
