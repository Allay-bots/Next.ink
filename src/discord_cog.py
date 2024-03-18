"""
Ce programme est régi par la licence CeCILL soumise au droit français et
respectant les principes de diffusion des logiciels libres. Vous pouvez
utiliser, modifier et/ou redistribuer ce programme sous les conditions
de la licence CeCILL diffusée sur le site "http://www.cecill.info".
"""

# Requirements
# ------------
# - Python 3.12
# Standard libraries
from datetime import datetime, timezone
from time import mktime
import hashlib
import re

# External libraries
import discord
from discord.ext import commands, tasks
from LRFutils import logs
import feedparser

# Project modules
import allay


# Cog
# ---

async def remove_subscription(id: int):
    logs.info(f"Removing suscribtion {id}")
    allay.Database.query(
        "DELETE FROM next_ink WHERE id = ?",
        (id,)
    )


class NiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    group = discord.app_commands.Group(
        name="next",
        description="Next.ink",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True
    )

    @group.command(
        name="subscribe",
        description="Subscribe to Next.ink brief",
    )
    async def subscribe(self, ctx: discord.Interaction):
        if is_suscribed(ctx.guild.id, ctx.channel.id):
            await ctx.response.send_message("This channel is already subscribed to Next.ink brief.")
            return
        logs.info(f"Subscribing to Next.ink for {ctx.guild.id}")
        await add_suscribtion(ctx.guild.id, ctx.channel.id)
        await ctx.response.send_message("Subscribed to Next.ink brief.")

    @group.command(
        name="unsubscribe",
        description="Unsubscribe from Next.ink brief",
    )
    async def unsubscribe(self, ctx):
        if not is_suscribed(ctx.guild.id, ctx.channel.id):
            await ctx.response.send_message("This channel is not subscribed to Next.ink brief.")
            return
        logs.info(f"Unsubscribing from Next.ink for {ctx.guild.id}")
        await remove_suscribtion(ctx.guild.id, ctx.channel.id)
        await ctx.response.send_message(f"Unsubscribed from Next.ink brief.")

    @group.command(
        name="list",
        description="List subscriptions",
    )
    async def list(self, ctx):
        logs.info(f"Listing suscribtions for {ctx.guild.id}")
        suscribtions = await get_suscribtions(ctx.guild.id)
        await ctx.send(f"Subscriptions: {suscribtions}")

    @tasks.loop(minutes=1)
    async def check(self):
        logs.info("Checking Next.ink")
        feed = feedparser.parse("https://next.ink/feed/briefonly")
        last_run = datetime.fromtimestamp(await get_last_run(), timezone.utc)
        for entry in feed.entries:
            if datetime.fromtimestamp(mktime(entry.published_parsed), timezone.utc) < last_run:
                continue
            for suscribtion in await get_all_suscribtions():
                print(suscribtion)
                channel = self.bot.get_channel(int(suscribtion["channel_id"]))
                if channel is None:
                    logs.error(f"Channel {suscribtion['channel_id']} not found")
                    await remove_suscribtion(suscribtion["guild_id"], suscribtion["channel_id"])
                    continue
                embed = discord.Embed(
                    title=entry.title,
                    type="article",
                    color=int(hashlib.sha1(entry.title.encode()).hexdigest(), 16) % 0xFFFFFF,
                    url=entry.link
                )
                embed.set_footer(text="#LeBrief by Next.ink")

                img_regex = r'\bhttps?://\S+?\.(?:jpg|png|gif)\b'
                img = re.search(img_regex, entry.content[0].value, re.IGNORECASE)
                if img:
                    embed.set_thumbnail(url=img.group(0))

                await channel.send(embed=embed)
        await set_last_run(int(datetime.now().timestamp()))

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        """Start the scheduler on cog load"""
        self.check.start() # pylint: disable=no-member

    async def cog_unload(self):
        """Stop the scheduler on cog unload"""
        self.check.stop() # pylint: disable=no-member


# Database
# --------
async def get_suscribtions(guild_id: int):
    logs.info(f"Getting suscribtions for {guild_id}")
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ?",
        (guild_id,)
    )
    return result


async def get_all_suscribtions():
    logs.info(f"Getting all suscribtions")
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions"
    )
    return result


def is_suscribed(guild_id: int, channel_id: int):
    logs.info(f"Checking suscribtion for {guild_id}")
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )
    return len(result) == 1


async def add_suscribtion(guild_id: int, channel_id: int):
    logs.info(f"Adding suscribtion for {guild_id}")
    allay.Database.query(
        "INSERT INTO nextink_subscriptions (guild_id, channel_id) VALUES (?, ?)",
        (guild_id, channel_id)
    )


async def remove_suscribtion(guild_id: int, channel_id: int):
    logs.info(f"Removing suscribtion for {guild_id}")
    allay.Database.query(
        "DELETE FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )


async def get_last_run() -> int:
    logs.info(f"Getting 'last_run' system key")
    result = allay.Database.query(
        "SELECT value FROM nextink_system WHERE key = 'last_run'"
    )
    return int(result[0]["value"])


async def set_last_run(value: int):
    logs.info(f"Setting 'last_run' system key to {value}")
    allay.Database.query(
        "UPDATE nextink_system SET value = ? WHERE key = 'last_run'",
        (value,)
    )
