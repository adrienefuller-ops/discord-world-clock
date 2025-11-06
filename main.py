# --- Keep-Alive Web Server for Render Free Plan ---
from flask import Flask
import threading
import os

app = Flask('')

@app.route('/')
def home():
    return "World Clock Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 10000))  # Render provides PORT env var
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run).start()
# --- End Keep-Alive Section ---
import os
import json
from datetime import datetime
import asyncio
import pytz

import discord
from discord.ext import tasks
from discord import app_commands
from dotenv import load_dotenv

# ---------- Config & Storage ----------

DATA_DIR = "data"
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULT_TIMEZONES_ENV = os.getenv("DEFAULT_TIMEZONES", "")
DEFAULT_TIMEZONES = [tz.strip() for tz in DEFAULT_TIMEZONES_ENV.split(",") if tz.strip()] or [
    "America/New_York",
    "Europe/London",
    "Europe/Paris",
    "Asia/Tokyo",
    "Australia/Sydney",
]

ALIASES = {
    # Common aliases → IANA tz names
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "boston": "America/New_York",
    "et": "America/New_York",
    "eastern": "America/New_York",
    "chicago": "America/Chicago",
    "ct": "America/Chicago",
    "central": "America/Chicago",
    "denver": "America/Denver",
    "mt": "America/Denver",
    "mountain": "America/Denver",
    "phoenix": "America/Phoenix",
    "la": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "london": "Europe/London",
    "uk": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid",
    "rome": "Europe/Rome",
    "warsaw": "Europe/Warsaw",
    "tokyo": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
    "utc": "UTC",
    "gmt": "Etc/GMT",
}

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

def load_config():
    ensure_dirs()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def guild_cfg(cfg, guild_id: int):
    gid = str(guild_id)
    if gid not in cfg:
        cfg[gid] = {
            "channel_id": None,
            "message_id": None,
            "timezones": DEFAULT_TIMEZONES.copy(),
            "running": False,
        }
    return cfg[gid]

def normalize_tz(input_tz: str) -> str | None:
    if not input_tz:
        return None
    key = input_tz.strip().lower()
    # alias lookup
    if key in ALIASES:
        return ALIASES[key]
    # direct IANA name if valid
    if input_tz in pytz.all_timezones:
        return input_tz
    # try Title-case alias (e.g., "New York")
    if key.title() in ALIASES:
        return ALIASES[key.title()]
    return None

# ---------- Discord Bot ----------

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found. Set it in .env")

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

UPDATE_INTERVAL = 60  # seconds

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    # Sync commands globally
    try:
        await tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    updater.start()

async def render_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    embed = discord.Embed(title="🕒 World Clocks", description="", color=0x2ecc71)
    now_utc = datetime.utcnow()
    # Build fields
    for tzname in cfg["timezones"][:25]:  # Discord limit for fields
        try:
            tz = pytz.timezone(tzname)
            local = pytz.utc.localize(now_utc).astimezone(tz)
            disp = local.strftime("%a %b %d • %I:%M %p")
            embed.add_field(name=tzname, value=disp, inline=True)
        except Exception:
            # Skip invalid
            continue
    embed.set_footer(text="Updates every minute • Times account for DST where applicable")
    return embed

async def ensure_message(guild: discord.Guild, cfg: dict) -> tuple[discord.TextChannel | None, discord.Message | None]:
    channel_id = cfg.get("channel_id")
    if not channel_id:
        return None, None
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return None, None

    message_id = cfg.get("message_id")
    message = None
    if message_id:
        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            message = None

    if message is None:
        # create new message
        embed = await render_embed(guild, cfg)
        try:
            message = await channel.send(embed=embed)
            cfg["message_id"] = message.id
            save_config(CONFIG)
        except discord.Forbidden:
            return channel, None
    return channel, message

@tasks.loop(seconds=UPDATE_INTERVAL)
async def updater():
    # Periodically refresh all running guilds
    for guild in bot.guilds:
        try:
            cfg = guild_cfg(CONFIG, guild.id)
            if not cfg.get("running"):
                continue
            channel, message = await ensure_message(guild, cfg)
            if channel is None or message is None:
                continue
            embed = await render_embed(guild, cfg)
            await message.edit(embed=embed)
        except Exception as e:
            # Don't crash the loop for a single guild
            print(f"[Updater] Guild {guild.id} error: {e}")

# ---------- Slash Commands ----------

def admin_check(interaction: discord.Interaction) -> bool:
    # Require Manage Guild permission to use admin commands
    perms = interaction.user.guild_permissions
    return perms.manage_guild

@tree.command(name="clock", description="World clock controls")
@app_commands.describe(
    action="Subcommand: setchannel/add/remove/list/start/stop/refresh",
    tz="Time zone (IANA) or city alias",
    channel="Target text channel for the clock message"
)
async def clock(interaction: discord.Interaction, action: str, tz: str | None = None, channel: discord.TextChannel | None = None):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission to use this command.", ephemeral=True)

    cfg = guild_cfg(CONFIG, interaction.guild_id)

    if action.lower() == "setchannel":
        if channel is None:
            return await interaction.followup.send("Please provide a channel, e.g., `/clock action:setchannel channel:#general`", ephemeral=True)
        cfg["channel_id"] = channel.id
        cfg["message_id"] = None  # force recreate
        save_config(CONFIG)
        return await interaction.followup.send(f"Clock channel set to {channel.mention}.", ephemeral=True)

    elif action.lower() == "add":
        if not tz:
            return await interaction.followup.send("Provide a time zone or city alias to add.", ephemeral=True)
        real = normalize_tz(tz)
        if not real:
            return await interaction.followup.send(f"`{tz}` is not a known time zone or alias.", ephemeral=True)
        if real in cfg["timezones"]:
            return await interaction.followup.send(f"`{real}` is already in the list.", ephemeral=True)
        cfg["timezones"].append(real)
        save_config(CONFIG)
        return await interaction.followup.send(f"Added `{real}`.", ephemeral=True)

    elif action.lower() == "remove":
        if not tz:
            return await interaction.followup.send("Provide a time zone or alias to remove.", ephemeral=True)
        real = normalize_tz(tz) or tz  # allow direct removal by IANA
        if real not in cfg["timezones"]:
            return await interaction.followup.send(f"`{real}` not found in the list.", ephemeral=True)
        cfg["timezones"].remove(real)
        save_config(CONFIG)
        return await interaction.followup.send(f"Removed `{real}`.", ephemeral=True)

    elif action.lower() == "list":
        if not cfg["timezones"]:
            return await interaction.followup.send("No time zones configured.", ephemeral=True)
        listed = "\n".join(f"- {z}" for z in cfg["timezones"])
        return await interaction.followup.send(f"**Current time zones:**\n{listed}", ephemeral=True)

    elif action.lower() == "start":
        if not cfg.get("channel_id"):
            return await interaction.followup.send("Set a channel first: `/clock action:setchannel channel:#...`", ephemeral=True)
        cfg["running"] = True
        save_config(CONFIG)
        # Ensure message exists right away
        channel, message = await ensure_message(interaction.guild, cfg)
        if channel is None:
            return await interaction.followup.send("I can't access the configured channel. Check my permissions.", ephemeral=True)
        await interaction.followup.send(f"Clock updates started in {channel.mention}.", ephemeral=True)

    elif action.lower() == "stop":
        cfg["running"] = False
        save_config(CONFIG)
        return await interaction.followup.send("Clock updates stopped.", ephemeral=True)

    elif action.lower() == "refresh":
        if not cfg.get("channel_id"):
            return await interaction.followup.send("No channel configured.", ephemeral=True)
        channel, message = await ensure_message(interaction.guild, cfg)
        if channel is None or message is None:
            return await interaction.followup.send("Couldn't find or create the message. Check permissions.", ephemeral=True)
        embed = await render_embed(interaction.guild, cfg)
        await message.edit(embed=embed)
        return await interaction.followup.send("Refreshed.", ephemeral=True)

    else:
        return await interaction.followup.send("Unknown action. Use one of: setchannel, add, remove, list, start, stop, refresh", ephemeral=True)

# Nice UX: provide a dedicated command with structured subcommands

clock_group = app_commands.Group(name="clock2", description="World clock controls with subcommands")

@clock_group.command(name="setchannel", description="Set the clock channel")
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    cfg["channel_id"] = channel.id
    cfg["message_id"] = None
    save_config(CONFIG)
    await interaction.followup.send(f"Clock channel set to {channel.mention}.", ephemeral=True)

@clock_group.command(name="add", description="Add a time zone (IANA or alias)")
@app_commands.describe(tz="e.g., America/New_York or 'Paris'")
async def addtz(interaction: discord.Interaction, tz: str):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    real = normalize_tz(tz)
    if not real:
        return await interaction.followup.send(f"`{tz}` is not a known time zone or alias.", ephemeral=True)
    if real in cfg["timezones"]:
        return await interaction.followup.send(f"`{real}` already in the list.", ephemeral=True)
    cfg["timezones"].append(real)
    save_config(CONFIG)
    await interaction.followup.send(f"Added `{real}`.", ephemeral=True)

@clock_group.command(name="remove", description="Remove a time zone")
@app_commands.describe(tz="IANA name or alias to remove")
async def removetz(interaction: discord.Interaction, tz: str):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    real = normalize_tz(tz) or tz
    if real not in cfg["timezones"]:
        return await interaction.followup.send(f"`{real}` not found.", ephemeral=True)
    cfg["timezones"].remove(real)
    save_config(CONFIG)
    await interaction.followup.send(f"Removed `{real}`.", ephemeral=True)

@clock_group.command(name="list", description="List configured time zones")
async def listtz(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    if not cfg["timezones"]:
        return await interaction.followup.send("No time zones configured.", ephemeral=True)
    await interaction.followup.send("**Time zones:**\n" + "\n".join(f"- {z}" for z in cfg["timezones"]), ephemeral=True)

@clock_group.command(name="start", description="Start live clock updates")
async def start(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    if not cfg.get("channel_id"):
        return await interaction.followup.send("Set a channel first with `/clock2 setchannel`.", ephemeral=True)
    cfg["running"] = True
    save_config(CONFIG)
    channel, message = await ensure_message(interaction.guild, cfg)
    if channel is None or message is None:
        return await interaction.followup.send("I can't access or create the clock message. Check my permissions.", ephemeral=True)
    await interaction.followup.send(f"Clock started in {channel.mention}.", ephemeral=True)

@clock_group.command(name="stop", description="Stop live updates")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    cfg["running"] = False
    save_config(CONFIG)
    await interaction.followup.send("Clock updates stopped.", ephemeral=True)

@clock_group.command(name="refresh", description="Refresh the clock message")
async def refresh(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not admin_check(interaction):
        return await interaction.followup.send("You need **Manage Server** permission.", ephemeral=True)
    cfg = guild_cfg(CONFIG, interaction.guild_id)
    channel, message = await ensure_message(interaction.guild, cfg)
    if channel is None or message is None:
        return await interaction.followup.send("I can't access or create the clock message. Check my permissions.", ephemeral=True)
    embed = await render_embed(interaction.guild, cfg)
    await message.edit(embed=embed)
    await interaction.followup.send("Refreshed.", ephemeral=True)

# Register group
tree.add_command(clock_group)

# Autocomplete for tz arguments (for /clock2 add)
@addtz.autocomplete("tz")
async def tz_autocomplete(interaction: discord.Interaction, current: str):
    # Suggest matches from pytz and our aliases
    current_lower = current.lower()
    suggestions = []
    for alias, iana in ALIASES.items():
        if current_lower in alias and iana not in suggestions:
            suggestions.append(iana)
            if len(suggestions) >= 20:
                break
    if len(suggestions) < 20:
        for tz in pytz.all_timezones:
            if current_lower in tz.lower():
                suggestions.append(tz)
                if len(suggestions) >= 20:
                    break
    return [app_commands.Choice(name=s, value=s) for s in suggestions]

if __name__ == "__main__":
    ensure_dirs()
    CONFIG = load_config()
    bot.run(TOKEN)
