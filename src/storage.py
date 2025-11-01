"""
Ce programme est régi par la licence CeCILL soumise au droit français et
respectant les principes de diffusion des logiciels libres. Vous pouvez
utiliser, modifier et/ou redistribuer ce programme sous les conditions
de la licence CeCILL diffusée sur le site "http://www.cecill.info".
"""

from __future__ import annotations

# Standard libraries
from typing import Optional

# Project modules
import allay
from .constants import SILENT, FREQUENCY

# Database accessors
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


def is_subscribed(guild_id: int, channel_id: int):
    result = allay.Database.query(
        "SELECT * FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )
    return len(result) == 1


async def add_subscription(guild_id: int, channel_id: int, silent=SILENT.NONE, frequency=FREQUENCY.REALTIME):
    allay.Database.query(
        "INSERT INTO nextink_subscriptions (guild_id, channel_id, silent, frequency) VALUES (?, ?, ?, ?)",
        (guild_id, channel_id, silent, frequency)
    )


async def remove_subscription(guild_id: int, channel_id: int):
    allay.Database.query(
        "DELETE FROM nextink_subscriptions WHERE guild_id = ? AND channel_id = ?",
        (guild_id, channel_id)
    )


# System key helpers
async def get_system_int(key: str) -> int:
    result = allay.Database.query(
        "SELECT value FROM nextink_system WHERE key = ?",
        (key,)
    )
    if len(result) == 0:
        return 0
    try:
        return int(result[0]["value"]) if result[0]["value"] is not None else 0
    except Exception:
        return 0


async def set_system(key: str, value: str):
    exists = allay.Database.query(
        "SELECT 1 FROM nextink_system WHERE key = ?",
        (key,)
    )
    if len(exists) == 0:
        allay.Database.query(
            "INSERT INTO nextink_system (key, value) VALUES (?, ?)",
            (key, value)
        )
    else:
        allay.Database.query(
            "UPDATE nextink_system SET value = ? WHERE key = ?",
            (value, key)
        )


# Schema and queue helpers
async def ensure_schema():
    # Ensure frequency column exists
    cols = allay.Database.query("PRAGMA table_info('nextink_subscriptions');")
    colnames = [c.get('name') for c in cols]
    if 'frequency' not in colnames:
        try:
            allay.Database.query("ALTER TABLE nextink_subscriptions ADD COLUMN frequency int(2) NOT NULL DEFAULT 0")
        except Exception:
            pass
    # Ensure system keys
    allay.Database.query("CREATE TABLE IF NOT EXISTS 'nextink_system' ('key' varchar(255) NOT NULL PRIMARY KEY, 'value' varchar(255) NOT NULL)")
    for k in ['last_fetch', 'last_send_hourly', 'last_send_daily']:
        allay.Database.query("INSERT OR IGNORE INTO nextink_system (key, value) VALUES (?, '0')", (k,))
    # Ensure queue table
    allay.Database.query(
        """
        CREATE TABLE IF NOT EXISTS 'nextink_articles' (
            'id' varchar(255) NOT NULL PRIMARY KEY,
            'title' text NOT NULL,
            'link' text NOT NULL,
            'image_url' text,
            'published_ts' integer NOT NULL,
            'discovered_ts' integer NOT NULL
        )
        """
    )


async def queue_article(id: str, title: str, link: str, image_url: Optional[str], published_ts: int, discovered_ts: int):
    allay.Database.query(
        "INSERT OR IGNORE INTO nextink_articles (id, title, link, image_url, published_ts, discovered_ts) VALUES (?, ?, ?, ?, ?, ?)",
        (id, title, link, image_url, published_ts, discovered_ts)
    )


async def get_articles_from_queue(start_ts: int, end_ts: int) -> list:
    rows = allay.Database.query(
        "SELECT * FROM nextink_articles WHERE discovered_ts > ? AND discovered_ts <= ? ORDER BY published_ts ASC",
        (start_ts, end_ts)
    )
    return rows