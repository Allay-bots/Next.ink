CREATE TABLE IF NOT EXISTS 'nextink_subscriptions' (
    'guild_id' varchar(255) NOT NULL,
    'channel_id' varchar(255) NOT NULL,
    'silent' int(2) NOT NULL DEFAULT 0,
    'frequency' int(2) NOT NULL DEFAULT 0,
    PRIMARY KEY ('guild_id', 'channel_id')
);
CREATE INDEX IF NOT EXISTS 'guild_id' ON 'nextink_subscriptions' ('guild_id', 'channel_id');

CREATE TABLE IF NOT EXISTS 'nextink_system' (
    'key' varchar(255) NOT NULL PRIMARY KEY,
    'value' varchar(255) NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS 'key' ON 'nextink_system' ('key');

INSERT OR IGNORE INTO 'nextink_system' ('key', 'value') VALUES ('last_fetch', '0');
INSERT OR IGNORE INTO 'nextink_system' ('key', 'value') VALUES ('last_send_hourly', '0');
INSERT OR IGNORE INTO 'nextink_system' ('key', 'value') VALUES ('last_send_daily', '0');

-- Queue of discovered articles
CREATE TABLE IF NOT EXISTS 'nextink_articles' (
    'id' varchar(255) NOT NULL PRIMARY KEY,
    'title' text NOT NULL,
    'link' text NOT NULL,
    'image_url' text,
    'published_ts' integer NOT NULL,
    'discovered_ts' integer NOT NULL
);
