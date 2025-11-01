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
from datetime import datetime, time, timezone
from time import mktime
from typing import List, Optional
import hashlib
import re

# Project modules
import allay

# Plugin internal
from .constants import SILENT, FREQUENCY
from .storage import (
    ensure_schema,
    get_system_int,
    set_system,
    queue_article,
    get_subscriptions,
    is_subscribed,
    add_subscription,
    remove_subscription,
)
from .sending import send_to_frequency, send_batch

# External libraries
import discord
import feedparser
import logging
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


# Cog
# ---


class NiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    FETCH_INTERVAL_MINUTES = 1

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
    @discord.app_commands.describe(
            silent="Should the brief be sent as silent messages ?",
            frequency="How often to send batches"
        )
    @discord.app_commands.choices(
            silent=[
                discord.app_commands.Choice(name="Send all messages as silent", value=SILENT.NONE),
                discord.app_commands.Choice(name="Send only first message with notification", value=SILENT.FIRST),
                discord.app_commands.Choice(name="Send all messages with notification", value=SILENT.ALL)
            ],
            frequency=[
                discord.app_commands.Choice(name="Real-time", value=FREQUENCY.REALTIME),
                discord.app_commands.Choice(name="Hourly", value=FREQUENCY.HOURLY),
                discord.app_commands.Choice(name="Daily", value=FREQUENCY.DAILY)
            ]
        )
    async def subscribe(self, ctx: discord.Interaction, silent: discord.app_commands.Choice[int], frequency: discord.app_commands.Choice[int]):

        if is_subscribed(ctx.guild.id, ctx.channel.id):
            await ctx.response.send_message(
                allay.I18N.tr(
                    ctx,
                    "nextink.already_subscribed",
                )
            )
            return
        await add_subscription(ctx.guild.id, ctx.channel.id, silent.value, frequency.value)
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
            silence_mode = subscription['silent']
            if silence_mode == SILENT.NONE:
                silence_label = allay.I18N.tr(ctx, "nextink.notifications.none")
            elif silence_mode == SILENT.FIRST:
                silence_label = allay.I18N.tr(ctx, "nextink.notifications.first")
            else:
                silence_label = allay.I18N.tr(ctx, "nextink.notifications.all")
            freq_val = int(subscription.get("frequency", FREQUENCY.REALTIME))
            if freq_val == FREQUENCY.DAILY:
                freq_label = "Daily"
            elif freq_val == FREQUENCY.HOURLY:
                freq_label = "Hourly"
            else:
                freq_label = "Real-time"
            embed.add_field(
                name=f"{channel.mention}",
                value=f"{silence_label} — {freq_label}",
                inline=True
            )
        await ctx.response.send_message(embed=embed)

    # Fetch every 5 minutes and queue new articles
    @tasks.loop(minutes=FETCH_INTERVAL_MINUTES)
    async def fetch_loop(self):
        logger.info("Next.ink - Fetching feed")
        feed = feedparser.parse("https://next.ink/feed/full")
        last_fetch_ts = await get_system_int('last_fetch')
        now_ts = int(datetime.now().timestamp())
        for entry in feed.entries:
            logger.debug("Looking at article : {}".format(entry.title))
            published_ts = int(mktime(entry.published_parsed)) if hasattr(entry, 'published_parsed') and entry.published_parsed else now_ts
            if published_ts <= last_fetch_ts:
                logger.debug("Too old")
                continue
            article_id = hashlib.sha1(f"{entry.get('link')}".encode()).hexdigest()
            img_url = None
            try:
                img_regex = r'\bhttps?://\S+?\.(?:jpg|png|gif)\b'
                if 'content' in entry and entry.content and hasattr(entry.content[0], 'value'):
                    img = re.search(img_regex, entry.content[0].value, re.IGNORECASE)
                    if img:
                        img_url = img.group(0)
            except Exception:
                pass
            await queue_article(article_id, entry.title, entry.link, img_url, published_ts, now_ts)
        # Send a batch for realtime
        await send_batch(self.bot, last_fetch_ts, now_ts, FREQUENCY.REALTIME)
        # Update last_fetch
        await set_system('last_fetch', str(now_ts))

    @fetch_loop.before_loop
    async def before_fetch(self):
        await self.bot.wait_until_ready()

    # Unified send loop: runs hourly; triggers daily batch at 08:00
    @tasks.loop(time=[time(hour=x, minute=0) for x in range(0, 24)])
    async def send_loop(self):
        logger.info("Next.ink - Send loop")
        now = datetime.now()
        now_ts = int(now.timestamp())

        # Hourly batch
        logger.debug("Running hourly batch")
        last_hourly = await get_system_int('last_send_hourly')
        await send_batch(self.bot, last_hourly, now_ts, FREQUENCY.HOURLY)
        await set_system('last_send_hourly', str(now_ts))

        # Daily batch if it's 08:00
        if now.hour == 17:
            logger.debug("Running daily batch")
            last_daily = await get_system_int('last_send_daily')
            await send_batch(self.bot, last_daily, now_ts, FREQUENCY.DAILY)
            await set_system('last_send_daily', str(now_ts))

    @send_loop.before_loop
    async def before_send(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        """Start the scheduler on cog load"""
        logger.debug("Ensuring DB schema is up to date")
        await ensure_schema()
        # Initialize system keys if first run
        if await get_system_int('last_fetch') == 0:
            logger.debug("Initializing system keys")
            now_ts = int(datetime.now().timestamp())
            await set_system('last_fetch', str(now_ts))
            await set_system('last_send_hourly', str(now_ts))
            await set_system('last_send_daily', str(now_ts))
        self.fetch_loop.start()
        self.send_loop.start()

    async def cog_unload(self):
        """Stop the scheduler on cog unload"""
        self.fetch_loop.stop()  # pylint: disable=no-member
        self.send_loop.stop()

