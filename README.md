# Discord World Clock Bot

A simple Discord bot that posts a live-updating embed showing the current times across selected time zones. Admins can configure the channel, add/remove time zones, and start/stop updates via slash commands.

## ✨ Features
- Live-updating embedded "World Clocks" message (updates every minute).
- Per-server configuration saved to disk.
- Slash commands (`/clock ...`) for setup and customization.
- Works with IANA time zone names (e.g., `America/New_York`) and common city aliases (`New York`, `London`, `Tokyo`, etc.).
- DST handled automatically.

## 🧰 Prereqs
- Python 3.10+
- A Discord account with permission to add a bot to your server.
- (Windows) `tzdata` included via `requirements.txt`

## 🚀 Setup
1. **Create a Discord Application & Bot**
   - Go to https://discord.com/developers/applications → **New Application**.
   - Add a **Bot** → **Reset Token** and copy it.
   - Under **Privileged Gateway Intents**, you don't need any for this bot. (Leave off unless you add features.)
   - Under **OAuth2 → URL Generator**:
     - Scopes: `bot` and `applications.commands`
     - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History` (optional: `Manage Messages`)
   - Copy the generated invite link and add the bot to your server.

2. **Clone/Download this project**
   - Place files in a folder, e.g., `discord-world-clock`.

3. **Configure environment**
   - Copy `.env.example` → `.env` and set `DISCORD_TOKEN` to your bot token.

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

6. **Register slash commands (first run)**
   - After the bot starts, it syncs commands automatically. You may need to wait up to a minute for Discord to display them.

## 🕹️ Commands (Admin only)
All commands are under `/clock`:

- `/clock setchannel channel:#general`  
  Sets the channel where the clock embed will live.

- `/clock add tz:Europe/Paris`  
  Adds a time zone (accepts IANA names or city aliases like `Paris`, `New York`).

- `/clock remove tz:Europe/Paris`  
  Removes a time zone by IANA name or alias.

- `/clock list`  
  Shows current configured time zones.

- `/clock start`  
  Starts the live-updating clock (creates or reuses an embed message).

- `/clock stop`  
  Stops the updates (does not delete the message).

- `/clock refresh`  
  Forces an immediate refresh of the embed.

## 🧭 Notes
- Time zones are validated against `pytz.all_timezones`. Aliases are mapped in code.
- The bot stores data in `data/config.json`. Delete it to reset configs (or edit carefully).

## 🔒 Security
- Never commit your real `.env` (token) to git.
