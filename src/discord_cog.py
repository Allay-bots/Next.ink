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
import asyncio

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
            await ctx.response.send_message(
                allay.I18N.tr(
                    ctx,
                    "nextink.already_subscribed",
                )
            )
            return
        logs.info(f"Next.ink - Subscribing {ctx.guild.id} - {ctx.channel.id}")
        await add_suscribtion(ctx.guild.id, ctx.channel.id)
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
        if not is_suscribed(ctx.guild.id, ctx.channel.id):
            await ctx.response.send_message(
                allay.I18N.tr(
                    ctx,
                    "nextink.not_subscribed",
                )
            )
            return
        logs.info(f"Next.ink - Unsubscribing {ctx.guild.id} - {ctx.channel.id}")
        await remove_suscribtion(ctx.guild.id, ctx.channel.id)
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
        suscribtions = await get_suscribtions(ctx.guild.id)
        if len(suscribtions) == 0:
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
        for suscribtion in suscribtions:
            channel = self.bot.get_channel(int(suscribtion["channel_id"]))
            embed.add_field(
                name="",
                value=f"{channel.mention}",
                inline=True
            )
        await ctx.response.send_message(embed=embed)

    @tasks.loop(minutes=60)
    async def check(self):
        logs.info("Next.ink - Checking the feed")
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
                text="#LeBrief - Next.ink"
            )

            img_regex = r'\bhttps?://\S+?\.(?:jpg|png|gif)\b'
            img = re.search(img_regex, entry.content[0].value, re.IGNORECASE)
            if img:
                embed.set_thumbnail(url=img.group(0))

            embeds.append(embed)

        if len(embeds) == 0:
            return

        suscribtions = await get_all_suscribtions()
        for suscribtion in suscribtions:
            channel = self.bot.get_channel(int(suscribtion["channel_id"]))
            # fallback if no webhook permission
            if not channel.permissions_for(channel.guild.me).manage_webhooks:
                for embed in embeds:
                    await channel.send(
                        embed=embed
                    )
                continue

            webhook = await channel.create_webhook(
                name="#LeBrief - Next.ink",
                reason=allay.I18N.tr(
                    channel,
                    "nextink.webhook.reason",
                )
            )
            for embed in embeds:
                await webhook.send(
                    avatar_url=feed.feed.image.href,
                    embed=embed,
                    silent=True
                )
            await webhook.delete()

        await set_last_run(int(datetime.now().timestamp()))

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        """Start the scheduler on cog load"""
        await wait_until_hour()
        self.check.start()  # pylint: disable=no-member

    async def cog_unload(self):
        """Stop the scheduler on cog unload"""
        self.check.stop()  # pylint: disable=no-member


# Database
# --------
async def get_suscribtions(guild_id: int):
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ?",
        (guild_id,)
    )
    return result


async def get_all_suscribtions():
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions"
    )
    return result


def is_suscribed(guild_id: int, channel_id: int):
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )
    return len(result) == 1


async def add_suscribtion(guild_id: int, channel_id: int):
    logs.info(f"Next.ink - Adding suscribtion for {guild_id}")
    allay.Database.query(
        "INSERT INTO nextink_subscriptions (guild_id, channel_id) VALUES (?, ?)",
        (guild_id, channel_id)
    )


async def remove_suscribtion(guild_id: int, channel_id: int):
    logs.info(f"Next.ink - Removing suscribtion for {guild_id}")
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
    logs.info(f"Next.ink - Setting 'last_run' system key to {value}")
    allay.Database.query(
        "UPDATE nextink_system SET value = ? WHERE key = 'last_run'",
        (value,)
    )


async def wait_until_hour():
    logs.info("Next.ink - Waiting until the next hour")
    now = datetime.now()
    if now.minute == 0:
        return
    await asyncio.sleep((60 - now.minute) * 60)
