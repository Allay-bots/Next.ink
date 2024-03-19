CREATE TABLE IF NOT EXISTS 'nextink_subscriptions' (
    'guild_id' varchar(255) NOT NULL,
    'channel_id' varchar(255) NOT NULL,
    'silent' int(2) NOT NULL DEFAULT 0,
    PRIMARY KEY ('guild_id', 'channel_id')
);
CREATE INDEX IF NOT EXISTS 'guild_id' ON 'nextink_subscriptions' ('guild_id', 'channel_id');

CREATE TABLE IF NOT EXISTS 'nextink_system' (
    'key' varchar(255) NOT NULL PRIMARY KEY,
    'value' varchar(255) NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS 'key' ON 'nextink_system' ('key');

INSERT OR IGNORE INTO 'nextink_system' ('key', 'value') VALUES ('last_run', '0');
