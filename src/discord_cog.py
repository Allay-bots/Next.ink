"""
Ce programme est régi par la licence CeCILL soumise au droit français et
respectant les principes de diffusion des logiciels libres. Vous pouvez
utiliser, modifier et/ou redistribuer ce programme sous les conditions
de la licence CeCILL diffusée sur le site "http://www.cecill.info".
"""

import hashlib
import re
# Requirements
# ------------
# - Python 3.12
# Standard libraries
from datetime import datetime, time, timezone
from time import mktime

# Project modules
import allay
# External libraries
import discord
import feedparser
import logging
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


# Constants
# ---------

class SILENT:
    ALL = 2
    FIRST = 1
    NONE = 0


# Cog
# ---


class NiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    group = discord.app_commands.Group(
        name="next",
        description="Next.ink",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    @group.command(
        name="subscribe",
        description="Subscribe to Next.ink brief",
    )
    @discord.app_commands.describe(silent="Should the brief be sent as silent messages ?")
    @discord.app_commands.choices(
        silent=[
            discord.app_commands.Choice(name="Send all messages as silent", value=SILENT.NONE),
            discord.app_commands.Choice(name="Send only first message with notification", value=SILENT.FIRST),
            discord.app_commands.Choice(name="Send all messages with notification", value=SILENT.ALL)
        ]
    )
    async def subscribe(self, ctx: discord.Interaction, silent: discord.app_commands.Choice[int]):

        if is_subscribed(ctx.guild.id, ctx.channel.id):
            await ctx.response.send_message(
                allay.I18N.tr(
                    ctx,
                    "nextink.already_subscribed",
                )
            )
            return
        await add_subscription(ctx.guild.id, ctx.channel.id, silent.value)
        await ctx.response.send_message(
            allay.I18N.tr(
                ctx,
                "nextink.subscribed",
            )
        )

    @group.command(
        name="unsubscribe",
        description="Unsubscribe from Next.ink brief",
    )
    async def unsubscribe(self, ctx):
        if not is_subscribed(ctx.guild.id, ctx.channel.id):
            await ctx.response.send_message(
                allay.I18N.tr(
                    ctx,
                    "nextink.not_subscribed",
                )
            )
            return
        await remove_subscription(ctx.guild.id, ctx.channel.id)
        await ctx.response.send_message(
            allay.I18N.tr(
                ctx,
                "nextink.unsubscribed",
            )
        )

    @group.command(
        name="list",
        description="List subscriptions",
    )
    async def list(self, ctx):
        subscriptions = await get_subscriptions(ctx.guild.id)
        if len(subscriptions) == 0:
            await ctx.response.send_message(
                allay.I18N.tr(
                    ctx,
                    "nextink.list.empty",
                )
            )
            return
        embed = discord.Embed(
            title=allay.I18N.tr(
                ctx,
                "nextink.list.title",
            ),
            color=0x00FF00
        )
        for subscription in subscriptions:
            channel = self.bot.get_channel(int(subscription["channel_id"]))
            silence_mode = await get_silence_mode(ctx.guild.id, subscription["channel_id"])
            if silence_mode == SILENT.NONE:
                silence_mode = allay.I18N.tr(ctx, "nextink.notifications.none")
            elif silence_mode == SILENT.FIRST:
                silence_mode = allay.I18N.tr(ctx, "nextink.notifications.first")
            elif silence_mode == SILENT.ALL:
                silence_mode = allay.I18N.tr(ctx, "nextink.notifications.all")
            embed.add_field(
                name=f"{channel.mention}",
                value=silence_mode,
                inline=True
            )
        await ctx.response.send_message(embed=embed)

    #time = [time(hour=x, minute=0) for x in range(0, 24)]
    time = [time(hour=10, minute=0)]

    @tasks.loop(time=time)
    async def check(self):
        logger.info("Next.ink - Checking the feed")
        feed = feedparser.parse("https://next.ink/feed/briefonly")
        last_run = datetime.fromtimestamp(await get_last_run(), timezone.utc)
        embeds = []
        for entry in feed.entries:
            if datetime.fromtimestamp(mktime(entry.published_parsed), timezone.utc) < last_run:
                continue

            embed = discord.Embed(
                title=entry.title,
                type="article",
                color=int(hashlib.sha1(entry.title.encode()).hexdigest(), 16) % 0xFFFFFF,
                url=entry.link
            )
            embed.set_footer(
                text="Next.ink"
            )

            img_regex = r'\bhttps?://\S+?\.(?:jpg|png|gif)\b'
            img = re.search(img_regex, entry.content[0].value, re.IGNORECASE)
            if img:
                embed.set_thumbnail(url=img.group(0))

            embeds.append(embed)

        if len(embeds) == 0:
            await set_last_run(int(datetime.now().timestamp()))
            return

        subscriptions = await get_all_subscriptions()
        for subscription in subscriptions:
            silence_mode = await get_silence_mode(subscription["guild_id"], subscription["channel_id"])
            silence = True if (silence_mode == SILENT.ALL) else False

            channel = self.bot.get_channel(int(subscription["channel_id"]))
            # fallback if no webhook permission
            if not channel.permissions_for(channel.guild.me).manage_webhooks:
                for embed in embeds:
                    await channel.send(
                        embed=embed,
                        silent=silence
                    )
                    if silence_mode == SILENT.FIRST:
                        silence = True
                continue

            webhook = await channel.create_webhook(
                name="Next.ink",
                reason=allay.I18N.tr(
                    channel,
                    "nextink.webhook.reason",
                )
            )
            for embed in embeds:
                await webhook.send(
                    avatar_url=feed.feed.image.href,
                    embed=embed,
                    silent=silence
                )
                if silence_mode == SILENT.FIRST:
                    silence = True
            await webhook.delete()

        await set_last_run(int(datetime.now().timestamp()))

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        """Start the scheduler on cog load"""
        # Avoid spam on first loop
        if await get_last_run() == 0:
            await set_last_run(int(datetime.now().timestamp()))
        self.check.start()

    async def cog_unload(self):
        """Stop the scheduler on cog unload"""
        self.check.stop()  # pylint: disable=no-member


# Database
# --------
async def get_subscriptions(guild_id: int):
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ?",
        (guild_id,)
    )
    return result


async def get_all_subscriptions():
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions"
    )
    return result


async def get_silence_mode(guild_id: int, channel_id: int):
    result = allay.Database.query(
        "SELECT silent FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )
    return result[0]["silent"] if len(result) == 1 else SILENT.NONE


def is_subscribed(guild_id: int, channel_id: int):
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )
    return len(result) == 1


async def add_subscription(guild_id: int, channel_id: int, silent=SILENT.NONE):
    logger.info(f"Next.ink - Adding subscription for {guild_id}")
    allay.Database.query(
        "INSERT INTO nextink_subscriptions (guild_id, channel_id, silent) VALUES (?, ?, ?)",
        (guild_id, channel_id, silent)
    )


async def remove_subscription(guild_id: int, channel_id: int):
    logger.info(f"Next.ink - Removing subscription for {guild_id}")
    allay.Database.query(
        "DELETE FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )


async def get_last_run() -> int:
    result = allay.Database.query(
        "SELECT value FROM nextink_system WHERE key = 'last_run'"
    )
    return int(result[0]["value"])


async def set_last_run(value: int):
    logger.info(f"Next.ink - Setting 'last_run' system key to {value}")
    allay.Database.query(
        "UPDATE nextink_system SET value = ? WHERE key = 'last_run'",
        (value,)
    )
