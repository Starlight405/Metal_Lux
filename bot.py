
import discord
from discord import app_commands
import json
import os
import re
import asyncio
import random
from datetime import timedelta

TOKEN = "YOUR_BOT_TOKEN_HERE"

WARNINGS_FILE = "warnings.json"
LEVELS_FILE = "levels.json"


# =========================
# LOAD AND SAVE WARNINGS
# =========================

if os.path.exists(WARNINGS_FILE):
    with open(WARNINGS_FILE, "r") as f:
        warnings = json.load(f)
else:
    warnings = {}


def save_warnings():
    with open(WARNINGS_FILE, "w") as f:
        json.dump(warnings, f, indent=4)


# =========================
# LOAD AND SAVE LEVELS
# =========================

if os.path.exists(LEVELS_FILE):
    with open(LEVELS_FILE, "r") as f:
        levels = json.load(f)
else:
    levels = {}


def save_levels():
    with open(LEVELS_FILE, "w") as f:
        json.dump(levels, f, indent=4)


def get_user_data(guild_id, user_id):
    guild_id = str(guild_id)
    user_id = str(user_id)

    if guild_id not in levels:
        levels[guild_id] = {}

    if user_id not in levels[guild_id]:
        levels[guild_id][user_id] = {
            "xp": 0,
            "level": 0
        }

    return levels[guild_id][user_id]


def xp_needed(level):
    return 100 + (level * 50)


# =========================
# DURATION PARSER
# =========================

def parse_duration(duration):
    match = re.fullmatch(r"(\d+)(s|m|h|d)", duration.lower())

    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "s":
        return timedelta(seconds=amount)
    elif unit == "m":
        return timedelta(minutes=amount)
    elif unit == "h":
        return timedelta(hours=amount)
    elif unit == "d":
        return timedelta(days=amount)

    return None


# =========================
# BOT SETUP
# =========================

class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


client = MyClient()


# =========================
# LEVELING SYSTEM
# =========================

message_cooldowns = {}


@client.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    key = (message.guild.id, message.author.id)
    now = asyncio.get_running_loop().time()

    # Award XP at most once every 60 seconds per user
    if key in message_cooldowns:
        if now - message_cooldowns[key] < 60:
            return

    message_cooldowns[key] = now

    data = get_user_data(message.guild.id, message.author.id)

    data["xp"] += random.randint(5, 15)

    leveled_up = False

    while data["xp"] >= xp_needed(data["level"]):
        data["xp"] -= xp_needed(data["level"])
        data["level"] += 1
        leveled_up = True

    save_levels()

    if leveled_up:
        await message.channel.send(
            f"🎉 Congratulations {message.author.mention}! "
            f"You reached **Level {data['level']}**!"
        )


# =========================
# WARN COMMAND
# =========================

@client.tree.command(name="warn", description="Warn a member")
@app_commands.describe(
    member="The member you want to warn",
    reason="Why are you warning them?"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str
):
    if member == interaction.user:
        await interaction.response.send_message(
            "❌ You can't warn yourself.",
            ephemeral=True
        )
        return

    if member == interaction.guild.owner:
        await interaction.response.send_message(
            "❌ You can't warn the server owner.",
            ephemeral=True
        )
        return

    user_id = str(member.id)

    if user_id not in warnings:
        warnings[user_id] = []

    warnings[user_id].append({
        "reason": reason,
        "moderator": str(interaction.user)
    })

    save_warnings()

    await interaction.response.send_message(
        f"⚠️ **{member.display_name}** has been warned.\n"
        f"**Reason:** {reason}\n"
        f"**Total warnings:** {len(warnings[user_id])}"
    )


# =========================
# WARNINGS COMMAND
# =========================

@client.tree.command(
    name="warnings",
    description="View a member's warnings"
)
@app_commands.describe(
    member="The member whose warnings you want to see"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def warning_list(
    interaction: discord.Interaction,
    member: discord.Member
):
    user_warnings = warnings.get(str(member.id), [])

    if not user_warnings:
        await interaction.response.send_message(
            f"✅ **{member.display_name}** has no warnings.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"Warnings for {member.display_name}",
        color=discord.Color.orange()
    )

    # Discord embeds support up to 25 fields.
    for number, warning in enumerate(user_warnings[:25], start=1):
        embed.add_field(
            name=f"Warning #{number}",
            value=(
                f"**Reason:** {warning['reason']}\n"
                f"**Moderator:** {warning['moderator']}"
            ),
            inline=False
        )

    embed.set_footer(
        text=f"Total warnings: {len(user_warnings)}"
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================
# TIMEOUT COMMAND
# =========================

@client.tree.command(
    name="timeout",
    description="Timeout a member"
)
@app_commands.describe(
    member="The member you want to timeout",
    duration="Duration, such as 10m, 2h, or 1d",
    reason="Why are you timing them out?"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    duration: str,
    reason: str
):
    if member == interaction.user:
        await interaction.response.send_message(
            "❌ You can't timeout yourself.",
            ephemeral=True
        )
        return

    if member == interaction.guild.owner:
        await interaction.response.send_message(
            "❌ You can't timeout the server owner.",
            ephemeral=True
        )
        return

    timeout_duration = parse_duration(duration)

    if timeout_duration is None or timeout_duration <= timedelta(0):
        await interaction.response.send_message(
            "❌ Invalid duration. Use `30s`, `10m`, `2h`, or `1d`.",
            ephemeral=True
        )
        return

    if timeout_duration > timedelta(days=28):
        await interaction.response.send_message(
            "❌ The maximum timeout is 28 days.",
            ephemeral=True
        )
        return

    try:
        await member.timeout(timeout_duration, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I can't timeout this member. Check my permissions "
            "and make sure my bot role is above their role.",
            ephemeral=True
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "❌ Discord couldn't complete the timeout.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"🔇 **{member.display_name}** has been timed out.\n"
        f"**Duration:** {duration}\n"
        f"**Reason:** {reason}"
    )


# =========================
# KICK COMMAND
# =========================

@client.tree.command(
    name="kick",
    description="Kick a member from the server"
)
@app_commands.describe(
    member="The member you want to kick",
    reason="Why are you kicking them?"
)
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str
):
    if member == interaction.user:
        await interaction.response.send_message(
            "❌ You can't kick yourself.",
            ephemeral=True
        )
        return

    if member == interaction.guild.owner:
        await interaction.response.send_message(
            "❌ You can't kick the server owner.",
            ephemeral=True
        )
        return

    bot_member = interaction.guild.me

    if member.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            "❌ You can't kick someone with a role equal to "
            "or higher than yours.",
            ephemeral=True
        )
        return

    if bot_member and member.top_role >= bot_member.top_role:
        await interaction.response.send_message(
            "❌ My bot role must be higher than the member's role.",
            ephemeral=True
        )
        return

    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to kick this member.",
            ephemeral=True
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "❌ Discord couldn't complete the kick.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"👢 **{member.display_name}** has been kicked.\n"
        f"**Reason:** {reason}"
    )


# =========================
# TEMPORARY BAN SUPPORT
# =========================

async def unban_later(guild_id, user_id, duration):
    await asyncio.sleep(duration.total_seconds())

    guild = client.get_guild(guild_id)

    if guild is None:
        return

    try:
        user = await client.fetch_user(user_id)
        await guild.unban(user, reason="Temporary ban expired")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


# =========================
# BAN COMMAND
# =========================

@client.tree.command(name="ban", description="Ban a member")
@app_commands.describe(
    member="The member you want to ban",
    reason="Why are you banning them?",
    duration="Optional: 10m, 2h, or 7d. Leave empty for permanent."
)
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str,
    duration: str = None
):
    if member == interaction.user:
        await interaction.response.send_message(
            "❌ You can't ban yourself.",
            ephemeral=True
        )
        return

    if member == interaction.guild.owner:
        await interaction.response.send_message(
            "❌ You can't ban the server owner.",
            ephemeral=True
        )
        return

    bot_member = interaction.guild.me

    if member.top_role >= interaction.user.top_role:
        await interaction.response.send_message(
            "❌ You can't ban someone with a role equal to "
            "or higher than yours.",
            ephemeral=True
        )
        return

    if bot_member and member.top_role >= bot_member.top_role:
        await interaction.response.send_message(
            "❌ My bot role must be higher than the member's role.",
            ephemeral=True
        )
        return

    ban_duration = None

    if duration:
        ban_duration = parse_duration(duration)

        if ban_duration is None or ban_duration <= timedelta(0):
            await interaction.response.send_message(
                "❌ Invalid duration. Use `10m`, `2h`, or `7d`.",
                ephemeral=True
            )
            return

    try:
        await member.ban(reason=reason, delete_message_seconds=0)
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to ban this member.",
            ephemeral=True
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "❌ Discord couldn't complete the ban.",
            ephemeral=True
        )
        return

    if ban_duration is None:
        await interaction.response.send_message(
            f"🔨 **{member.display_name}** has been permanently banned.\n"
            f"**Reason:** {reason}"
        )
    else:
        asyncio.create_task(
            unban_later(
                interaction.guild.id,
                member.id,
                ban_duration
            )
        )

        await interaction.response.send_message(
            f"🔨 **{member.display_name}** has been temporarily banned.\n"
            f"**Duration:** {duration}\n"
            f"**Reason:** {reason}"
        )


# =========================
# LEVEL COMMAND
# =========================

@client.tree.command(
    name="level",
    description="Check a member's level and XP"
)
@app_commands.describe(
    member="The member to check (optional)"
)
async def level(
    interaction: discord.Interaction,
    member: discord.Member = None
):
    member = member or interaction.user

    data = get_user_data(interaction.guild_id, member.id)
    needed = xp_needed(data["level"])

    embed = discord.Embed(
        title=f"🏆 {member.display_name}'s Level",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="Level",
        value=str(data["level"]),
        inline=True
    )

    embed.add_field(
        name="XP",
        value=f"{data['xp']} / {needed}",
        inline=True
    )

    embed.set_thumbnail(url=member.display_avatar.url)

    await interaction.response.send_message(embed=embed)


# =========================
# LEADERBOARD COMMAND
# =========================

@client.tree.command(
    name="leaderboard",
    description="Show the server's top 10 members"
)
async def leaderboard(interaction: discord.Interaction):
    guild_levels = levels.get(str(interaction.guild_id), {})

    if not guild_levels:
        await interaction.response.send_message(
            "No one has earned XP yet. Start chatting!",
            ephemeral=True
        )
        return

    sorted_users = sorted(
        guild_levels.items(),
        key=lambda item: (
            item[1]["level"],
            item[1]["xp"]
        ),
        reverse=True
    )

    lines = []

    for position, (user_id, data) in enumerate(
        sorted_users[:10],
        start=1
    ):
        lines.append(
            f"**{position}.** <@{user_id}> — "
            f"Level {data['level']} ({data['xp']} XP)"
        )

    embed = discord.Embed(
        title="🏆 Server Level Leaderboard",
        description="\n".join(lines),
        color=discord.Color.gold()
    )

    await interaction.response.send_message(embed=embed)


# =========================
# SLASH COMMAND ERROR HANDLER
# =========================

@client.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "❌ You don't have permission to use this command."
    else:
        print(f"Slash command error: {error}")
        message = "❌ Something went wrong while running this command."

    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True
        )


# =========================
# START THE BOT
# =========================

client.run(TOKEN)