# astrbot_plugin_zeroserver

一个基于 **AstrBot** 的《方舟：生存进化 / 生存飞升》(ARK: Survival Evolved `ASE` / Ark: Survival Ascended `ASA`) 服务器机器人插件：

- **服务器查询**：在线状态 / 在线人数 / 地图 / 倍率 / 直连地址，支持自动与手动刷新
- **跨服聊天转发**：进化 ↔ 飞升 ↔ QQ 群实时互转（需要游戏聊天入库）
- **QQ ↔ 游戏账号绑定**：QQ 内直接绑定、游戏公屏 `qqbind` / 验证码 `zsbind` 绑定
- **每日签到**：给绑定的游戏账号发放商店点数（进化/飞升各自独立、每天一次、只加一次）
- **可选的 LLM 引导助手**：@机器人或命中触发词时，用大模型引导玩家使用指令
- **缓存版本更新提醒**：定时抓取更新包列表并通知

> 本仓库为**可发布模板**：已移除全部真实密钥、QQ/群号、服务器 IP、直连端口、RCON 地址端口等敏感信息。
> 所有需要你填写的位置都集中在 `config.json`，本文档逐条说明（见 [配置说明](#配置说明)）。

---

## 目录结构

```
astrbot_plugin_zeroserver/
├── main.py              # 插件主体（全部逻辑）
├── config.example.json  # 可填写模板（已脱敏，可安全提交到 GitHub）
├── config.json          # ★ 本地真实配置（已 gitignore；复制 config.example.json 后填写）
├── metadata.yaml        # 插件元信息（作者/仓库地址等）
├── requirements.txt     # Python 依赖
├── README.md            # 本文档（中文）
└── README.en.md         # 文档（English）
```

---

## 架构与数据流

```
                ┌────────────────────────── AstrBot 运行环境 ──────────────────────────┐
 QQ 群 / 私聊 ──▶│  插件指令处理  /help /ase /asa /ark /rate /绑定 /签到 /rcon /加点 …   │
 (OneBot 事件)  │        │                    │                     │                   │
                │  指令查询 ─┼─▶ 抓取缓存 (servers_html_url / rcon_html_url /            │
                │            │      dynamic_ini_url / usage_url_*) 定时刷新             │
                │            │                                                        │
                │  绑定/签到 ─┼─▶ MySQL bind_db(qq) ── qq_bind / qq_checkin             │
                │            │                                                        │
                │            ▼                                                        │
                │  RCON 目标列表（rcon_targets / RCON.html 自动构建）                   │
                └────────────┼─────────────────────────────────────────────────────────┘
                             ▼
        游戏服务器 RCON：AddPoints / GetPlayerPoints / serverchat / 管理命令（单台或按版本，绝不广播）

 后台常驻任务：
  ├─ 聊天转发器  轮询 db_sources(asa_chat/ase_chat 的 cross_chat) → QQ 群 + 对端游戏 RCON
  ├─ 游戏内绑定监听 同上轮询 → 识别公屏 qqbind/zsbind → 写 qq_bind 并通知
  ├─ 倍率/地址/缓存检测 定时抓取 → 变动时广播/通知
  └─ LLM 引导（可选）  @机器人或触发词 → 调大模型 → 引导玩家使用指令
```

> 设计要点：**凡“实时数据”均由机器人自己的指令/抓取提供**；LLM 只负责引导玩家使用指令，
> 避免模型编造在线人数、点数等无法查询的数值。加点点数类操作只对**一台在线服务器**执行一次，杜绝重复发放。

---

## 功能与指令

### QQ 群 / 私聊可用（玩家）
| 指令 | 作用 |
| --- | --- |
| `/help` `/帮助` | 查看帮助（Owner 私聊会额外显示管理指令） |
| `/ase` `/进化 [地图名]` | 查询进化(ASE)服务器；不带地图名=列出全部 |
| `/asa` `/飞升 [地图名]` | 查询飞升(ASA)服务器；不带地图名=列出全部 |
| `/ark` `/查服 <IP:端口> 或 <地图名> [ASE|ASA]` | 通用查询 |
| `/rate` `/倍率` | 查看动态倍率 |
| `/direct` `/直连` | 查看所有地图直连地址 |
| `/players` `/在线玩家` `/在线` `/谁在线` `[进化\|飞升] [地图名]` | 在线玩家明细：名字、部落名（取自聊天库）、最近活动地图、ID；**不给版本=进化+飞升一起查** |
| `/update_address` `/更新地址` | 手动刷新地址缓存 |
| `/bind` `/绑定 <进化\|飞升> <ID>` | 绑定游戏 ID（进化=SteamID64 17位数字；飞升=EOS 32位hex） |
| `/bind` `/绑定 <进化\|飞升> 开绑` | 生成游戏内验证码（配合游戏公屏 `zsbind`） |
| `/unbind` `/解绑 <进化\|飞升>` | 解绑 |
| `/mybind` `/查绑定` | 查看我的绑定 |
| `/signin` `/签到` `/每日签到` | 每日签到领点数（进化/飞升每天各一次） |

### QQ 官方机器人相关（v1.2.0 新增）
| 指令 | 作用 |
| --- | --- |
| `/whoami` `/我是谁` | 查看自己的平台 ID（openid/QQ号）与群标识，用于填写 `owner_qq` / 白名单 / 通知群；不受白名单限制 |
| `/testpush` `/测试推送` | Owner 专用：在通知群主动发一条测试消息，验证主动消息权限/配额 |

### 游戏内（在游戏公屏输入，走聊天库监听）
| 指令 | 作用 |
| --- | --- |
| `qqbind <你的QQ号>` | 把当前游戏账号绑到该 QQ（该 QQ 未绑过此游戏时） |
| `zsbind <验证码>` | 用 QQ 里 `开绑` 拿到的验证码完成绑定/换绑 |

> 商店聊天指令（`/points`、`/shop`、`/buy` 等）由游戏内 **ArkShop** 插件提供，本机器人不处理。

> QQ 官方机器人的「指令」登记清单（可直接照抄到 q.qq.com）：[docs/qqofficial-commands.md](docs/qqofficial-commands.md)

### 管理指令（仅 `owner_qq` 私聊生效，群聊忽略）
| 指令 | 作用 |
| --- | --- |
| `/rcon <ASE\|ASA> <命令>` | 对该版本全部服务器执行 RCON 命令 |
| `/rcon <ASE\|ASA> <地图名> <命令>` | 对指定地图那一台服务器执行 |
| `/rcon <目标名> <命令>` | 对指定目标执行 |
| `/加点` `/addpoints` `/arkshop <进化\|飞升> <ID> <点数>` | 给玩家加 ArkShop 点数（单台在线服执行一次） |
| `/代加点` `/帮加` `/atpoints <进化\|飞升> <点数> @群友…` | 群聊中给“已绑定”该游戏的群友加点 |

---

## 快速开始

1. 安装 [AstrBot](https://github.com/AstrBotDevs/AstrBot)，并确保你的 QQ 适配器（如 aiocqhttp / OneBot v11）已接入。
2. 克隆/复制本目录到 AstrBot 的 `plugins` 目录。
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
4. 复制配置模板并逐项填写：
   ```bash
   cp config.example.json config.json   # Windows: copy config.example.json config.json
   # 然后编辑 config.json，按下方「配置说明」逐项填写
   ```
5. 按[数据库准备](#数据库准备)建好数据库与账号授权。
6. 重启 AstrBot / 热重载插件。
7. 群内发 `/help` 检查是否正常；owner 私聊发 `/help` 看管理指令。

> ⚠️ `config.json` 已加入 `.gitignore`（含密钥，请勿提交）；仓库中发布的只有脱敏的 `config.example.json`。

---

## 接入 QQ 官方机器人（可选）

1. AstrBot WebUI → **机器人 → 新建 → QQ 官方机器人（WebSocket）**（推荐“扫码一键创建”，自动写入 appid/secret）；
2. 手机 QQ 的群机器人设置里开启 **获取群内全部消息** 与 **机器人主动在群聊内发言**（否则收不到非 @ 消息、也发不出主动通知）；
3. **openid 说明**：官方机器人无法获取真实 QQ 号，用户标识是 openid（私聊 `user_openid`、群 `member_openid`）。`owner_qq`、`whitelist_groups`、`notify_group`、`update_notify_qq` 都填 openid，可用 `/我是谁` 获取；实测同一用户的群/私聊 openid 一致，可直接用发送者 ID 作统一身份；
4. **绑定方式**：官方渠道下游戏内 `qqbind <QQ号>` 不可用（QQ 号无法映射为 openid），请用验证码流程：QQ 里 `/绑定 飞升 开绑` → 游戏公屏 `zsbind <验证码>`；
5. **数据库自动迁移**：插件启动会检测 `qq_bind`/`qq_checkin` 的 `qq` 列，自动把 `BIGINT` 改为 `VARCHAR(64)`，并给 `qq_bind` 增加 `platform` 列（账号需 ALTER 权限）。若检测到 `platform` 为空且主键是纯数字 QQ 号的旧绑定（OneBot 时代遗留），会标记为 `legacy` 并在启动日志提示条数——这些记录在 openid 下无法直接命中，玩家按第 4 步重新走一次游戏内验证绑定后，插件会按游戏 ID 自动接回原记录；
6. 指令面板 / 自定义菜单可通过开放平台 API 配置：见 [docs/qqofficial-commands.md](docs/qqofficial-commands.md)。

## 配置说明

> `config.json` 中的所有“可填写位置”如下。**带 【抓取】的字段指：机器人会去定时抓取该地址内容**，请确保地址对你可访问，并满足文末的[抓取页面约定](#抓取页面约定)。

### 群与权限
| 键 | 类型/示例 | 说明 |
| --- | --- | --- |
| `notify_group` | `123456789` | 通知群号：签到之外的公告、跨服聊天转发目标群、更新提醒都发这里 |
| `whitelist_groups` | `[123456789, 987654321]` | 允许使用指令的群白名单；留空 `[]`=不限制 |
| `owner_qq` | `123456789` | 服主 QQ：`/rcon`、`/加点`、`/代加点`、Owner 完整帮助 等管理能力 |
| `update_notify_qq` | `123456789` | 缓存更新时私聊通知的 QQ |

### 数据抓取（【抓取】区域 —— 本地可运行需正确填写）
| 键 | 示例 | 说明 |
| --- | --- | --- |
| `servers_html_url` | `http://你的主机:8888/Servers.html` | 【抓取】直连地址列表页（含每张图的服务器地址） |
| `rcon_html_url` | `http://你的主机:8888/RCON.html` | 【抓取】RCON 地址页（含 RCON 密码与各图 RCON 地址） |
| `dynamic_ini_url` | `http://你的主机/Dynamic.ini` | 【抓取】倍率文件（k=v 格式，用于 `/rate` 与倍率变动检测） |
| `usage_url_ase` | `https://你的站/ase-usage.html` | 【抓取】(可选) 进化版“如何加入”说明页，追加在查询结果里 |
| `usage_url_asa` | `https://你的站/asa-usage.html` | 【抓取】(可选) 飞升版“如何加入”说明页 |
| `cache_mirror_url` | `http://你的主机/cache/` | 【抓取】(可选) 缓存更新检测的目录列表页（含 `<64位hash>.zip` 文件链接的 HTML） |
| `cache_check_interval_minutes` | `10` | 缓存检测间隔（分钟） |

> 抓取失败不会崩溃：只记日志并沿用上次缓存/空列表。

### 数据库连接（跨服聊天 + 游戏内绑定）
| 键 | 类型/示例 | 说明 |
| --- | --- | --- |
| `db_sources` | 数组，见下方示例 | 游戏聊天库源。**元素 `id` 必须叫 `asa_chat`(飞升) / `ase_chat`(进化)**，插件据此区分版本并选择 `EOSid`/`SteamId` 列 |
| `chat_forward_enabled` | `true/false` | 跨服聊天转发开关 |
| `chat_check_interval` | `1.0` | 转发轮询秒数 |
| `qq_to_game_enabled` | `true/false` | QQ 群消息是否通过 RCON 转发进游戏 |
| `qq_forward_prefix` | `💬 [QQ群]` | 转进游戏时消息前缀（含该前缀的消息不会被再次转发，防循环） |
| `kook_forward_prefix` | `💬 [KOOK]` | KOOK 频道消息转进游戏时的前缀 |
| `broadcast_targets` | `[{platform,id,label}]` | 主动消息目标列表：跨服聊天转发、缓存更新通知、绑定结果公告、`/测试推送` 都发到这里。`platform` 支持 `qq_official` / `kook` / `aiocqhttp`，可同时配多个实现双平台广播；留空则回退到 `notify_group`。**只有列表里的群/频道会把消息转发进游戏** |
| `bridge_enabled` | `true/false` | 群间互通：广播目标之间的消息互相同步（如 QQ群 ↔ KOOK 频道），转发副本带 `🔀` 标记不会被二次转发 |
| `mask_player_ids` | `true/false` | 隐私：`/在线玩家` 名单里的游戏ID是否打码（默认打码；排查时可设 `false` 看完整 ID）。群/频道里其它命令的 ID 一律自动打码，私聊显示完整值 |
| `bind_db` | `{host,port,user,password,database}` | 绑定/签到记录库（默认库名 `qq`）。需要建表权限（也可由插件自动建表） |

`db_sources` 示例（每游戏一套库或一个库、注意 `id` 命名）：
```json
"db_sources": [
  { "id": "asa_chat", "type": "mysql", "host": "数据库主机", "port": 3306,
    "user": "库账号", "password": "库密码", "database": "asa_chat", "table": "cross_chat" },
  { "id": "ase_chat", "type": "mysql", "host": "数据库主机", "port": 3306,
    "user": "库账号", "password": "库密码", "database": "ase_chat", "table": "cross_chat" }
]
```

### 每日签到（ArkShop 加点）
| 键 | 类型/示例 | 说明 |
| --- | --- | --- |
| `signin.timezone_offset_hours` | `8` | “今天”按哪个时区算（东八区=8） |
| `signin.ase_points` | `50` | 进化签到加多少点 |
| `signin.asa_points` | `50` | 飞升签到加多少点 |
| `signin.ase_cmd` | `AddPoints {id} {points}` | 进化加点 RCON 命令模板（`{id}`=SteamID64，`{points}`=点数） |
| `signin.asa_cmd` | `AddPoints {id} {points}` | 飞升加点 RCON 命令模板（`{id}`=EOS，`{points}`=点数） |
| `signin.verify_with_getpoints` | `true` | 加点后执行 `GetPlayerPoints` 回读余额确认到账 |

> 命令按你的商店插件改：ArkServerApi 官方社区 ArkShop 的 RCON 命令为 `AddPoints <ID> <Amount>`、`GetPlayerPoints <ID>`。
> 每天只加一次由 `qq_checkin` 表的唯一键 `(qq, game, day)` 保证；只挑**一台在线服务器**执行，绝不广播。

### 游戏内绑定
| 键 | 类型/示例 | 说明 |
| --- | --- | --- |
| `game_bind.enable` | `true` | 游戏内绑定监听总开关 |
| `game_bind.qq_cmd` | `true` | 允许公屏 `qqbind <QQ号>`（该 QQ 已绑过其它号时拒绝，防冒绑） |
| `game_bind.code_cmd` | `true` | 允许 QQ 内 `开绑` 验证码流程（`zsbind`） |
| `game_bind.poll_interval` | `1.5` | 监听聊天库的轮询秒数 |
| `game_bind.code_ttl_seconds` | `180` | 验证码有效期 |
| `game_bind.dm_fallback` | `"@"` / `"off"` | 绑定结果私聊失败时是否在通知群以 `[QQ:xxx]` 文本公告（验证码永不发群） |

### LLM 引导助手（可选）
| 键 | 说明 |
| --- | --- |
| `llm_enabled` | `true/false`：是否启用（@机器人 或命中触发词才回；带 5 分钟冷却） |
| `llm_api_url` | OpenAI 兼容接口地址，示例为智谱 GLM 的 `…/chat/completions` |
| `llm_model` | 模型名，如智谱 `GLM-4.7-Flash`、DeepSeek `deepseek-chat` 等 |
| `llm_api_key` | 你的 API Key（**不要提交到公开仓库**） |
| `llm_trigger_keywords` | 触发词数组，扩展后玩家问“怎么绑定/怎么签到”也能唤醒 |
| `llm_system_prompt` | 人格设定：建议让模型“引导玩家用指令、不要编造实时数据”（模板见仓库说明/可自行编写） |

### 其它
| 键 | 说明 |
| --- | --- |
| `official_site` | 官网地址（显示在部分消息底部） |
| `check_interval_minutes` | 地址/RCON/倍率定时刷新间隔（分钟） |
| `rcon_timeout` | 单条 RCON 命令超时秒数 |
| `list_rcon_fallback` | `true` | 列表查询（ASE 的 A2S / ASA 的 ARK Status）失败或人数为 0 时，是否回退 RCON 判定在线与人数；嫌慢可设 `false` |
| `rcon_targets` | 手动 RCON 目标 `[{name,host,port}]`；也可由 `rcon_html_url` 自动构建 |
| `arkstatus_api_key` | (可选) ARK Status API Key，用于 ASA 在线查询回退 |

---

## 数据库准备

需要两类 MySQL 库：

### 1) 绑定/签到库（`bind_db`，默认库名 `qq`）
插件在启动时**会自动创建** `qq_bind` 与 `qq_checkin`（账号需 `CREATE` 权限）。手动创建 SQL：
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

### 2) 游戏聊天库（`db_sources`，跨服转发 / 游戏内绑定依赖）
聊天数据由你游戏服侧的程序（聊天桥/插件）写入；本插件只读取新行。建表参考（一库一张表即可，两个游戏可用同一张表）：
```sql
CREATE DATABASE IF NOT EXISTS chat_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_db.cross_chat (
  Id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  EOSid VARCHAR(100) NOT NULL DEFAULT '',     -- 飞升玩家 EOS（32位hex）
  SteamId BIGINT UNSIGNED NOT NULL DEFAULT 0, -- 进化玩家 SteamID64
  Map VARCHAR(50) NOT NULL DEFAULT '',
  Sender VARCHAR(100) NOT NULL DEFAULT '',    -- 角色名
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
关键点：
- **必须带玩家 ID 列**：飞升写入 `EOSid`、进化写入 `SteamId`，否则“游戏内绑定（qqbind/zsbind）”无法取到账号 ID；
- `Message` 存纯聊天文本（机器人转发回的消息会带 `[QQ群]` 等前缀，插件据此跳过防循环）；
- 权限：聊天账号至少 `SELECT`；`qq` 库账号建议 `SELECT/INSERT/UPDATE/DELETE/CREATE`（绑定/签到读写 + 自动建表）。

---

## 抓取页面约定

若你自建被【抓取】的网页，格式约定如下（与插件解析一致）：

- 页面内用 `<h2>` 文本包含 `ASE` 或 `ASA` 区分版本；
- 每个服务器条目是 `class="item"` 的 `<div>`，其中第一个 `span class="addr"` 文本为该图直连地址（RCON 页则为 RCON 地址）；
- RCON 页还需一个 `class="password-notice"` 的节点内含 RCON 密码文本；
- 倍率页为纯文本 k=v（`//` 开头为注释）；
- 缓存列表页只要能匹配到 `<64位hex>.zip` 链接即可（用于新版本提醒）。

---

## 常见问题

- **机器人没有回复 / LLM 不生效**：确认 `llm_enabled: true`、`llm_api_url` 与 `llm_model` 匹配、Key 正确；智谱免费档限流(429)会由插件自动退避重试。
- **签到显示“无在线服务器”**：该版本所有 RCON 目标都连不上，请检查 `rcon_html_url` 抓取与 RCON 连通性。
- **加了点但 /points 没变**：核对 `signin.*_cmd` 命令模板与商店插件版本是否一致；看日志里 `cmd=` 与 `resp=`。
- **游戏内 qqbind 没反应**：确认聊天已写入 `db_sources` 对应表且行内含 `EOSid/SteamId`；绑定监听启动日志应显示源与水位线。
- **绑定验证码收不到**：机器人私聊需玩家加好友或曾主动私聊；可在 `game_bind.dm_fallback` 开启群公告兜底（验证码仍不会发群）。

---

## 安全提示
- `config.json` 会包含数据库密码 / API Key：**不要提交到公开仓库**，发布示例请清空为占位/空值（本模板已如此处理，本地使用再填写）。
- `owner_qq` 只影响管理命令；管理命令仅私聊生效。
- 验证码绑定（`zsbind`）能证明“QQ 与游戏账号同属一人”，用于已绑定号换绑；`qqbind` 仅限未绑定状态，防他人抢绑。

## License
[MIT](./LICENSE)
