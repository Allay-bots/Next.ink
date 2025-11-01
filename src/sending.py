"""
Ce programme est régi par la licence CeCILL soumise au droit français et
respectant les principes de diffusion des logiciels libres. Vous pouvez
utiliser, modifier et/ou redistribuer ce programme sous les conditions
de la licence CeCILL diffusée sur le site "http://www.cecill.info".
"""

from __future__ import annotations

# Standard libraries
import hashlib
import logging

# External libraries
import discord

# Project modules
import allay
from .constants import SILENT, FREQUENCY
from .storage import get_all_subscriptions, get_articles_from_queue

logger = logging.getLogger(__name__)

async def send_batch(bot, start_ts: int, end_ts: int, frequency: int):
    logger.debug("Sending batch for {}".format(frequency))
    rows = await get_articles_from_queue(start_ts, end_ts)
    embeds = []
    for row in rows:
        title = row['title']
        link = row['link']
        image_url = row.get('image_url')
        embed = discord.Embed(
            title=title,
            type="article",
            color=int(hashlib.sha1(title.encode()).hexdigest(), 16) % 0xFFFFFF,
            url=link,
        )
        embed.set_footer(text="Next.ink")
        if image_url:
            embed.set_thumbnail(url=image_url)
        embeds.append(embed)
    await send_to_frequency(bot, embeds, frequency)


async def send_to_frequency(bot, embeds: list, frequency: int):
    """Send embeds to all subscriptions matching the given frequency.

    Uses webhooks when permitted, otherwise falls back to channel messages.
    Respects the SILENT preference (ALL, FIRST, NONE).
    """
    subscriptions = await get_all_subscriptions()
    targets = [s for s in subscriptions if int(s.get('frequency', FREQUENCY.REALTIME)) == frequency]
    for subscription in targets:
        silence_mode = subscription['silent']
        silence = True if (silence_mode == SILENT.ALL) else False
        channel = bot.get_channel(int(subscription["channel_id"]))
        if not channel:
            continue
        # If no manage_webhooks permission, send directly in channel
        if not channel.permissions_for(channel.guild.me).manage_webhooks:
            for embed in embeds:
                await channel.send(embed=embed, silent=silence)
                if silence_mode == SILENT.FIRST:
                    silence = True
            continue
        # Use a temporary webhook
        webhook = await channel.create_webhook(
            name="Next.ink",
            reason=allay.I18N.tr(channel, "nextink.webhook.reason")
        )
        try:
            for embed in embeds:
                await webhook.send(avatar_url="https://next.ink/wp-content/uploads/2023/11/favicon-150x150.png", embed=embed, silent=silence)
                if silence_mode == SILENT.FIRST:
                    silence = True
        finally:
            await webhook.delete()