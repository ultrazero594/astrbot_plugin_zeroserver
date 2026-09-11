# astrbot_plugin_zeroserver

An [AstrBot](https://github.com/AstrBotDevs/AstrBot) plugin for **ARK: Survival Evolved (`ASE` / 进化)** and **Ark: Survival Ascended (`ASA` / 飞升)** servers.

- **Server queries** — online status / player count / map / rates / direct-connect addresses, auto & manual refresh
- **Cross-server chat relay** — ASE ⇄ ASA ⇄ QQ group in real time (requires game chat written into MySQL)
- **QQ ↔ game account binding** — bind in QQ directly, or inside the game via `qqbind` / verification code `zsbind`
- **Daily check-in** — grants shop points to the bound game account (ASE/ASA independent, once per day, exactly one grant)
- **Optional LLM guide** — when @-mentioned or a trigger keyword matches, an LLM helps players use the commands
- **Cache update notifications** — periodically polls a file list and notifies when new server builds appear

> This repository is a **publishable template**: all real credentials, QQ/group IDs, server IPs, direct-connect ports,
> RCON addresses/ports and other ZeroARK-specific values were removed. Everything you need to configure lives in
> `config.json` and is documented below (see [Configuration](#configuration)).

---

## File layout

```
astrbot_plugin_zeroserver/
├── main.py              # plugin logic
├── config.example.json  # fill-in template (sanitized, safe to commit)
├── config.json          # ★ your real local config (git-ignored; copy from the example)
├── metadata.yaml        # plugin meta info (author / repo)
├── requirements.txt     # Python dependencies
├── README.md            # Chinese full guide
└── README.en.md         # this file (English)
```

## Architecture & data flow

```
              ┌────────────────────────── AstrBot runtime ──────────────────────────┐
QQ group/DM ─▶│  command handlers: /help /ase /asa /ark /rate /bind /signin /rcon…  │
(OneBot evt)  │     │                        │                    │                 │
              │  queries ─┼─▶ scraped caches (servers_html_url / rcon_html_url /    │
              │           │      dynamic_ini_url / usage_url_*) refreshed on a timer │
              │           │                                                        │
              │  bind/checkin ─┼─▶ MySQL bind_db (qq) ── qq_bind / qq_checkin        │
              │           │                                                        │
              │           ▼                                                        │
              │  RCON target list (rcon_targets / auto-built from RCON.html)        │
              └───────────┼─────────────────────────────────────────────────────────┘
                          ▼
  game RCON: AddPoints / GetPlayerPoints / serverchat / admin commands (single server
  or one whole version — never broadcast, so points can never be granted twice)

  Background loops:
   ├─ chat relay      polls db_sources (asa_chat/ase_chat.cross_chat) → QQ group + peer game RCON
   ├─ bind watcher    polls the same tables → detects in-game `qqbind`/`zsbind` → writes qq_bind + notifies
   ├─ rate/cache watcher periodic scrape → broadcasts/notifies on changes
   └─ optional LLM guide  @bot or trigger keyword → calls the LLM → nudges players to use commands
```

> Design rule: all *live data* comes from the bot's own commands/scrapers. The LLM only guides players toward
> commands and never fabricates player counts, points or statuses. Point-granting actions execute exactly once on
> **one online server**, so duplicate grants are structurally impossible.

---

## Commands

### Players (QQ group / DM)
| Command | Effect |
| --- | --- |
| `/help` `/帮助` | Show help (owner DM shows admin section too) |
| `/ase` `/进化 [map]` | Query ASE servers; no map = list all |
| `/asa` `/飞升 [map]` | Query ASA servers; no map = list all |
| `/ark` `/查服 <IP:port> or <map> [ASE\|ASA]` | Generic query |
| `/rate` `/倍率` | Show dynamic rates |
| `/direct` `/直连` | Show all direct-connect addresses |
| `/players` `/在线玩家` `/在线` `/谁在线` `[ASE\|ASA] [map]` | Online player details: name, tribe (chat DB), last active map, ID; **no version = both ASE+ASA** |
| `/update_address` `/更新地址` | Manually refresh address cache |
| `/bind` `/绑定 <ASE\|ASA> <ID>` | Bind game ID (ASE = SteamID64, 17 digits; ASA = EOS, 32 hex chars) |
| `/bind` `/绑定 <ASE\|ASA> 开绑` | Issue an in-game verification code (use with `zsbind`) |
| `/unbind` `/解绑 <ASE\|ASA>` | Unbind |
| `/mybind` `/查绑定` | Show my bindings |
| `/signin` `/签到` `/每日签到` | Daily check-in (ASE/ASA once per day each) |

### QQ official bot additions (v1.2.0)
| Command | Effect |
| --- | --- |
| `/whoami` | Show your platform ID (openid / QQ number) and group ID — used for `owner_qq`, whitelists and the notify group; bypasses the whitelist |
| `/testpush` | Owner only: send a proactive test message to the notify group (verifies proactive-message quota/permission) |

### In game (type in game public chat; picked up from the chat DB)
| Command | Effect |
| --- | --- |
| `qqbind <your QQ number>` | Bind the current game account to that QQ (only if that QQ is not bound to this game yet) |
| `zsbind <code>` | Complete binding/rebinding with the code from `开绑` |

> Shop chat commands (`/points`, `/shop`, `/buy`, ...) belong to the in-game **ArkShop** plugin, not this bot.

> QQ official bot 「commands」 registration checklist (copy-paste for q.qq.com): [docs/qqofficial-commands.md](docs/qqofficial-commands.md)
>
> **Command reference for KOOK & QQ (how to send, platform differences, panels/buttons): [docs/commands.md](docs/commands.md)** (Chinese)

### Admin (owner_qq only; DM only, ignored in groups)
| Command | Effect |
| --- | --- |
| `/rcon <ASE\|ASA> <command>` | Run an RCON command on all servers of that version |
| `/rcon <ASE\|ASA> <map> <command>` | Run on the single server of that map |
| `/rcon <target-name> <command>` | Run on a specific target |
| `/加点` `/addpoints` `/arkshop <ASE\|ASA> <ID> <points>` | Add ArkShop points (executed once on one online server) |
| `/代加点` `/帮加` `/atpoints <ASE\|ASA> <points> @member...` | In a group, add points for members **already bound** to that game |

---

## Quick start

1. Install [AstrBot](https://github.com/AstrBotDevs/AstrBot) and connect your QQ adapter (aiocqhttp / OneBot v11 etc.).
2. Copy this folder into AstrBot's `plugins` directory.
3. `pip install -r requirements.txt`
4. Copy the template and fill it in:
   ```bash
   cp config.example.json config.json    # Windows: copy config.example.json config.json
   ```
   then edit `config.json` and fill every key described below.
5. Prepare the databases (see [Database setup](#database-setup)).
6. Restart AstrBot or hot-reload the plugin.
7. Send `/help` in a group; send `/help` in a DM as owner to see admin commands.

> ⚠️ `config.json` is git-ignored because it holds secrets — never commit it. The repository only publishes the
> sanitized `config.example.json`.

---

## QQ official bot (optional)

1. AstrBot WebUI → **Bots → Create → QQ official bot (WebSocket)** (the QR "one-click create" fills appid/secret automatically);
2. In the mobile QQ group robot settings enable **receive all group messages** and **bot may speak proactively in groups**;
3. **openid**: the official bot cannot obtain real QQ numbers — identities are openids (DM `user_openid`, group `member_openid`). Fill `owner_qq` / `whitelist_groups` / `notify_group` / `update_notify_qq` with openids (get yours via `/我是谁`). Empirically the same user has the same openid in group and DM;
4. **Binding**: in-game `qqbind <QQ number>` is unusable on the official channel; use the code flow (`/绑定 飞升 开绑` → `zsbind <code>` in game chat);
5. **Automatic DB migration**: on startup the plugin converts `qq` from `BIGINT` to `VARCHAR(64)` and adds a `platform` column to `qq_bind` (needs ALTER privilege);
6. Command panels / custom menu can be configured via the open-platform API: see [docs/qqofficial-commands.md](docs/qqofficial-commands.md).

## Configuration

> Keys marked **【SCRAPE】** mean the bot periodically fetches that URL. Host pages yourself or point to your own
> endpoints so the feature works locally — the expected page format is described in
> [Scraped page contract](#scraped-page-contract).

### Groups & permissions
| Key | Example | Description |
| --- | --- | --- |
| `notify_group` | `123456789` | Notification group: announcements, chat relay target, update alerts |
| `whitelist_groups` | `[123456789, 987654321]` | Groups allowed to use commands; `[]` = allow all |
| `owner_qq` | `123456789` | Owner QQ: powers `/rcon`, `/加点`, `/代加点`, owner help |
| `owner_ids` | `["201xxxxxxx"]` | Extra owner IDs (cross-platform: QQ openid / KOOK user id); merged with `owner_qq` |
| `admin_channels` | `["4861xxxxxxxxxxxx"]` | Inside these groups/channels the owner also sees the full `/help` (admin section); empty = DMs only |
| `invite_kook` | `https://kook.vip/xxxx` | KOOK community invite shown at the bottom of `/help` on QQ (empty = hidden) |
| `invite_qq` | `123456789` | QQ group number shown at the bottom of `/help` on KOOK (empty = hidden) |
| `update_notify_qq` | `123456789` | QQ notified privately about cache updates |

### Scraped data feeds 【SCRAPE】
| Key | Example | Description |
| --- | --- | --- |
| `servers_html_url` | `http://your-host:8888/Servers.html` | Server direct-connect list page |
| `rcon_html_url` | `http://your-host:8888/RCON.html` | RCON addresses page (contains RCON password + per-map RCON addresses) |
| `dynamic_ini_url` | `http://your-host/Dynamic.ini` | Rates file (k=v lines, `//` comments) |
| `usage_url_ase` | `https://your-site/ase-usage.html` | (optional) “how to join” page appended to ASE results |
| `usage_url_asa` | `https://your-site/asa-usage.html` | (optional) “how to join” page appended to ASA results |
| `cache_mirror_url` | `http://your-host/cache/` | (optional) cache listing page containing `<64hex>.zip` links |
| `cache_check_interval_minutes` | `10` | cache check interval in minutes |

> A failed scrape is never fatal: the plugin logs and keeps the last cache / empty list.

### Chat DB & binding DB
| Key | Description |
| --- | --- |
| `db_sources` | Array of game-chat DB sources. **Each element `id` must be `asa_chat` (ASA) / `ase_chat` (ASE)** — the plugin picks the correct ID column (`EOSid` vs `SteamId`) from the id |
| `chat_forward_enabled` | Enable ASE⇄ASA⇄QQ relay |
| `chat_check_interval` | Relay poll interval (seconds) |
| `qq_to_game_enabled` | Forward QQ group messages into the game over RCON |
| `qq_forward_prefix` | Prefix added when forwarding into the game; messages containing relay markers are skipped (loop protection) |
| `kook_forward_prefix` | Prefix used when relaying KOOK channel messages into the game |
| `broadcast_targets` | `[{platform,id,label}]` — proactive-message targets (chat relay, cache alerts, bind results, `/testpush`). `platform` may be `qq_official` / `kook` / `aiocqhttp`; list several to broadcast to multiple platforms. Falls back to `notify_group` when empty. **Only groups/channels listed here relay messages into the game** |
| `bridge_enabled` | `true/false` — mirror messages between broadcast targets (e.g. QQ group ↔ KOOK channel); mirrored copies carry a `🔀` marker and are never re-relayed |
| `mask_player_ids` | `true/false` — mask game IDs in the `/在线玩家` list (default `true`; set `false` for full IDs when troubleshooting). Other commands always mask IDs in groups/channels and show full values in DMs |
| `bind_db` | `{host, port, user, password, database}` for bindings/check-ins (default database `qq`) |

Example `db_sources`:
```json
"db_sources": [
  { "id": "asa_chat", "type": "mysql", "host": "your-db-host", "port": 3306,
    "user": "chat-user", "password": "***", "database": "asa_chat", "table": "cross_chat" },
  { "id": "ase_chat", "type": "mysql", "host": "your-db-host", "port": 3306,
    "user": "chat-user", "password": "***", "database": "ase_chat", "table": "cross_chat" }
]
```

### Daily check-in (ArkShop points)
| Key | Example | Description |
| --- | --- | --- |
| `signin.timezone_offset_hours` | `8` | Time zone used for “today” (UTC+8 = 8) |
| `signin.ase_points` | `50` | Points granted by the ASE check-in |
| `signin.asa_points` | `50` | Points granted by the ASA check-in |
| `signin.ase_cmd` | `AddPoints {id} {points}` | RCON add-points command template (ASE: `{id}` = SteamID64) |
| `signin.asa_cmd` | `AddPoints {id} {points}` | RCON add-points command template (ASA: `{id}` = EOS) |
| `signin.verify_with_getpoints` | `true` | Run `GetPlayerPoints` afterwards and echo the balance |

> Match the template to your shop plugin. For the official community ArkShop (ArkServerApi) the RCON commands are
> `AddPoints <ID> <Amount>` and `GetPlayerPoints <ID>`. Exactly-once-per-day is enforced by the unique key
> `(qq, game, day)` on `qq_checkin`; points are executed on **one online server** only — never broadcast.

### In-game binding
| Key | Default | Description |
| --- | --- | --- |
| `game_bind.enable` | `true` | Master switch for in-game binding watcher |
| `game_bind.qq_cmd` | `true` | Allow `qqbind <QQ>` in public chat (rejected if that QQ is already bound to another account — anti-squatting) |
| `game_bind.code_cmd` | `true` | Allow verification-code flow (`开绑` in QQ then `zsbind` in game) |
| `game_bind.poll_interval` | `1.5` | Watcher poll interval (seconds) |
| `game_bind.code_ttl_seconds` | `180` | Code lifetime |
| `game_bind.dm_fallback` | `"@"` / `"off"` | If a private notice fails, announce as `[QQ:xxx]` text in the notify group (codes are never posted to groups) |

### Optional LLM guide
| Key | Description |
| --- | --- |
| `llm_enabled` | Reply when @-mentioned or a trigger keyword matches (with a 5-minute cooldown) |
| `llm_api_url` | OpenAI-compatible endpoint, e.g. Zhipu GLM `https://open.bigmodel.cn/api/paas/v4/chat/completions` |
| `llm_model` | e.g. Zhipu `GLM-4.7-Flash`, DeepSeek `deepseek-chat`, ... |
| `llm_api_key` | Your API key (**never commit it**) |
| `llm_trigger_keywords` | Array of trigger words (e.g. bind, sign-in keywords) |
| `llm_system_prompt` | Persona: instruct the model to guide players toward commands and never fabricate live data |

### Misc
| Key | Description |
| --- | --- |
| `official_site` | Website shown at the bottom of some messages |
| `check_interval_minutes` | Refresh interval for addresses/RCON/rates (minutes) |
| `rcon_timeout` | RCON command timeout (seconds) |
| `list_rcon_fallback` | `true` | Fall back to RCON for online status / player count when list queries (ASE A2S / ASA ARK Status) fail or report 0 players; set `false` if too slow |
| `rcon_targets` | Manual targets `[{name, host, port}]` (can also be built automatically from `rcon_html_url`) |
| `arkstatus_api_key` | (optional) ARK Status API key used as an ASA online fallback |

---

## Database setup

Two kinds of MySQL databases are used.

### 1) Binding / check-in database (`bind_db`, default `qq`)
The plugin creates `qq_bind` and `qq_checkin` automatically at startup (account needs `CREATE`). Manual SQL:
```sql
CREATE DATABASE IF NOT EXISTS qq CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS qq.qq_bind (
  qq BIGINT UNSIGNED NOT NULL,
  game VARCHAR(8) NOT NULL,
  player_id VARCHAR(64) NOT NULL,
  player_name VARCHAR(100) NOT NULL DEFAULT '',
  last_map VARCHAR(50) NOT NULL DEFAULT '',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (qq, game),
  KEY idx_game_player (game, player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS qq.qq_checkin (
  qq BIGINT UNSIGNED NOT NULL,
  game VARCHAR(8) NOT NULL,
  day CHAR(10) NOT NULL,
  points INT NOT NULL DEFAULT 0,
  server_name VARCHAR(100) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (qq, game, day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2) Game-chat database (`db_sources` — for relay and in-game binding)
Your game-server-side chat bridge writes rows here; the plugin only reads new rows. Reference schema (one table can
serve both games):
```sql
CREATE DATABASE IF NOT EXISTS chat_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_db.cross_chat (
  Id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  EOSid VARCHAR(100) NOT NULL DEFAULT '',     -- ASA players: EOS (32 hex chars)
  SteamId BIGINT UNSIGNED NOT NULL DEFAULT 0, -- ASE players: SteamID64
  Map VARCHAR(50) NOT NULL DEFAULT '',
  Sender VARCHAR(100) NOT NULL DEFAULT '',    -- character name
  Message VARCHAR(250) NOT NULL DEFAULT '',
  SenderPlatform TINYINT NOT NULL DEFAULT 0,
  TribeName VARCHAR(100) NOT NULL DEFAULT '',
  TribeId INT NOT NULL DEFAULT 0,
  Mode TINYINT NOT NULL DEFAULT 0,
  Tags VARCHAR(200) NOT NULL DEFAULT '',
  timestamp TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  isPm TINYINT NOT NULL DEFAULT 0,
  PmRecipient VARCHAR(250) NOT NULL DEFAULT '',
  PRIMARY KEY (Id),
  KEY idx_map_sender (Map, Sender),
  KEY idx_eos (EOSid),
  KEY idx_steam (SteamId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```
Important:
- Rows **must include the player ID column**: ASA rows populate `EOSid`, ASE rows populate `SteamId` — otherwise
  in-game binding (`qqbind` / `zsbind`) cannot resolve the account.
- `Message` stores the plain chat text. Bot-relayed messages carry prefixes such as `[QQ群]` and are skipped to avoid loops.
- Grant the chat user at least `SELECT`; grant the `qq`-DB user `SELECT/INSERT/UPDATE/DELETE/CREATE`.

---

## Scraped page contract

If you host the 【SCRAPE】 pages yourself, match this format (what the parser expects):

- an `<h2>` whose text contains `ASE` or `ASA` separates the versions;
- each server entry is a `<div class="item">`, and the first `span class="addr"` inside it holds the direct-connect
  address (RCON address on the RCON page);
- the RCON page also contains a node with `class="password-notice"` holding the RCON password text;
- the rates file is plain `k=v` text (`//` starts comments);
- the cache listing page only needs links matching `<64hex>.zip` for new-build notifications.

---

## FAQ

- **No LLM reply?** Check `llm_enabled: true`, that `llm_api_url` matches `llm_model`, and the key is correct.
  Zhipu free-tier throttling (HTTP 429) is retried automatically with backoff.
- **Check-in says “no online server”?** All RCON targets of that version are unreachable — inspect `rcon_html_url`
  scraping and RCON connectivity.
- **Points granted but `/points` unchanged?** Verify the `signin.*_cmd` template against your shop plugin; watch the
  plugin log lines containing `cmd=` and `resp=`.
- **`qqbind` in game does nothing?** Ensure game chat rows are written into the configured `db_sources` table with
  `EOSid`/`SteamId` populated; startup logs should show watcher sources and watermarks.
- **Cannot receive the binding code?** The bot can only DM friends or users who recently messaged it; or enable
  `game_bind.dm_fallback` for a group announcement (codes are still never posted to groups).

## Security notes
- `config.json` will hold database passwords and API keys — do **not** commit it to a public repository. The sample
  in this repo is empty/placeholder for that reason; fill it only in your local deployment.
- `owner_qq` gates admin commands, which run only in DMs.
- The verification-code flow (`zsbind`) proves that the QQ and the game account belong to the same person and is used
  for rebinding; `qqbind` only works while the QQ is unbound for that game, preventing account squatting.

## License
[MIT](./LICENSE)
