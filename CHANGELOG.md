# Changelog / 更新日志

All notable changes are documented here. 语义化版本：语义化版本 2.0 / [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.3.1] - 2026-09-11

### 修复 / Fixed
- 修复 `/绑定 <进化|飞升> <ID>` 可绕过换绑验证的漏洞：已绑定过其它账号时会被直接覆盖，违反"已绑后需验证码才能换"的设计。现在改为**拒绝**并提示走「开绑 → 游戏公屏 `zsbind <验证码>`」验证码流程（或先 `/解绑` 再重新绑定）
  - Fixed a re-bind bypass in `/bind <game> <id>`: an existing binding could be overwritten with no verification. It is now rejected with a hint to use the in-game verification-code flow (or `/unbind` first)
- 绑定的是同一个账号时，回复由「绑定成功」改为「已绑定同一账号（ID …），信息已刷新」，避免误报为一次新绑定
  - Re-binding the same account now reports "already bound, info refreshed" instead of "bind success"

### 文档 / Docs
- `/帮助` 中 `/绑定` 两条说明后补充一行：已绑定过其它账号时不能直接覆盖，换绑须走开绑验证码流程或先 `/解绑`
  - Help now states that an existing binding cannot be overwritten directly

## [1.3.0] - 2026-09-11

### 新增 / Added
- **旧绑定（OneBot 时代 QQ 号主键）自动迁移**：启动时把 `platform` 为空且主键是纯数字 QQ 号的绑定行标记为 `legacy`（仅在 QQ 官方机器人下执行，OneBot 部署不受影响），并打印剩余条数
  - **Automatic migration of legacy bindings**: rows whose key is a numeric QQ number (created before the QQ-official migration) are tagged `legacy` on startup — only when the QQ official adapter is active; OneBot deployments are unaffected
- 新增 `_claim_legacy_binding()`：玩家重新走「开绑 + 游戏内 `zsbind`」（或游戏公屏 `qqbind`）时，若其游戏 ID 命中一条 `legacy` 旧行，则自动接回原绑定记录并私聊告知「已接回你原「旧QQ号」的绑定记录」
  - New `_claim_legacy_binding()`: when a player re-binds via the in-game verified flow and the game ID matches a `legacy` row, the old record is adopted automatically and the player is notified
- `/查绑定`、`/签到` 在「未绑定」时追加老玩家引导：官方机器人拿不到真实 QQ 号，旧绑定需重新走一次开绑流程
  - `/mybind` and `/signin` now append a legacy-user hint when nothing is bound

### 说明 / Notes
- 旧 QQ 号主键在 openid 体系下无法直接命中，这 4 条记录不会自动生效；玩家完成一次游戏内验证绑定后即自动接回，无需人工改库
  - Legacy numeric keys can never match openids; affected players just need to complete one in-game verified binding and their record is reattached automatically

## [1.2.2] - 2026-09-11

### 修复 / Fixed
- 修复 `_getpoints_text` 调用漏 `await`：签到 / 加点后回读 `GetPlayerPoints` 余额失效（回复中出现 `<coroutine object ...>`），并会持续产生 `RuntimeWarning: coroutine was never awaited`
  - Fixed missing `await` on `_getpoints_text`: the `GetPlayerPoints` balance read-back after check-in / add-points did not run (leaked a coroutine object), and triggered `RuntimeWarning: coroutine was never awaited`

### 优化 / Changed
- `/在线玩家` 的玩家列表改用 `①②③…` 圆序号：每台服务器独立编号，避免 QQ 客户端把 `1.` `2.` 行合并成有序列表而自动续号
  - `/在线玩家` now numbers players with `①②③…` per server, preventing the QQ client from merging `1.`/`2.` lines into one auto-numbered list

## [1.2.1] - 2026-09-11

### 修复 / Fixed
- 修复 `/help` 处理器重复注册：`@filter.command("help")` 曾被误标到内部函数 `_help_lines` 上
  - Fixed duplicated help handler registration (`@filter.command("help")` was mis-applied to the internal `_help_lines`)

### 优化 / Changed
- `/help` 按当前平台自适应：未启用 OneBot（aiocqhttp）时，帮助中不再出现 `qqbind` 与 "OneBot" 字样，绑定主键文案改为 openid；重新启用 OneBot 时该行自动恢复
  - `/help` is now platform-aware: when OneBot is not configured, `qqbind` / "OneBot" lines are omitted and the binding note says openid; the line comes back automatically if OneBot is enabled again

## [1.2.0] - 2026-09-11

### 新增 / Added
- **QQ 官方机器人支持**：发送层自动识别平台，优先 `qq_official`（`platform.send_by_session`，群用 `group_openid`、私聊用 `user_openid`），否则回退 OneBot
  - QQ official bot support: platform-aware sending, preferring `qq_official` (`send_by_session` with `group_openid` / `user_openid`) and falling back to OneBot
- 新增 `/我是谁`（`/whoami`）：查看自己的平台 ID（openid/QQ号）与群标识，**不受白名单限制**（迁移期防自锁）
  - New `/whoami`: show your platform ID (openid / QQ number) and group ID; bypasses the whitelist
- 新增 `/测试推送`（`/testpush`，Owner）：在通知群主动发一条消息，验证主动消息权限/配额
  - New `/testpush` (owner): send a proactive test message to the notify group
- 新增文档 [docs/qqofficial-commands.md](docs/qqofficial-commands.md)：QQ 开放平台指令面板 / 自定义菜单的 API 配置指南与现成 JSON
  - New docs page for QQ open-platform command panels & custom menu (API guide + ready-to-use payloads)

### 优化 / Changed
- 身份体系兼容 openid：绑定/签到主键支持字符串；`qq_bind` 增加 `platform` 列；启动时自动把 `qq` 列由 `BIGINT` 迁移为 `VARCHAR(64)`
  - openid-compatible identities: string keys, new `platform` column, automatic `BIGINT` → `VARCHAR(64)` migration on startup
- 群内 `/签到` 未命中绑定时引导到私聊绑定/签到（群与私聊身份可能不同，签到记录共用、不会重复发点）
  - Group `/signin` now guides players to DM when the binding is not found
- `@群友` 解析与兜底 ID 支持 openid（非纯数字）
  - `@member` parsing and fallback IDs now accept openids (non-numeric)
- 帮助（`/help`）重排并补充：官方渠道 `qqbind` 不可用、群聊需 @机器人、绑定主键说明
  - Reworked `/help` with grouped sections and official-channel notes

### 注意 / Notes
- 官方机器人无法获取真实 QQ 号，绑定主键为 openid；从 OneBot 迁移的老绑定记录需玩家**重新绑定**一次
  - The official bot cannot obtain real QQ numbers; bindings are keyed by openid, so existing OneBot bindings must be re-created
- 官方渠道下游戏内 `qqbind <QQ号>` 不可用，请使用验证码流程（`开绑` → `zsbind`）
  - In-game `qqbind <QQ number>` is unavailable on the official channel; use the code flow

## [1.1.0] - 2026-09-10

### 新增 / Added
- 新增 `/在线玩家`（别名 `/在线`、`/players`、`/谁在线`）：查看在线玩家明细，包含**部落名**（取自聊天库 `TribeName`）、最近活动地图与玩家 ID；**不给版本时同时查询进化+飞升**，也可 `/在线玩家 飞升`、`/在线玩家 进化 孤岛` 单独查看
  - New `/在线玩家` (aliases `/在线`, `/players`, `/谁在线`): online player details for a version (optionally a map), including **tribe name** (from the chat DB `TribeName`), last active map and player ID

### 优化 / Changed
- 帮助信息（`/help`、`/帮助`）重排：按功能分组（服务器查询 / 在线玩家 / 账号绑定 / 每日签到 / 游戏内指令 / 管理员 / 其它），统一为“指令 → 说明”格式并列出中英文别名；签到点数从配置动态读取
  - Reworked the help output: grouped by feature with a consistent “command → description” format, aliases listed, and check-in points read from config

## [1.0.3] - 2026-09-10

### 修复 / Fixed
- 单服查询：A2S / ARK Status 只能给出人数、拿不到名单时，也会用 RCON `listplayers` 补全在线玩家名单（修复“明明有人却显示无”）
  - Single-server query now falls back to RCON `listplayers` whenever A2S / ARK Status cannot provide the player list (fixes "players online but none shown")

## [1.0.2] - 2026-09-10

### 修复 / Fixed
- 修复 RCON 解析的“幽灵人数”：空服时 `listplayers` 返回的 `No Players Connected` 不再被计为 1 名玩家
  - Fixed the phantom player: the `No Players Connected` placeholder from `listplayers` is no longer counted as a player
- `getserverinfo` 字段名改为忽略大小写/空格/下划线匹配（`Max Players`/`maxplayers`/`Max_Players` 均可），修掉飞升人数显示 `1/0`
  - `getserverinfo` keys are now matched ignoring case/spaces/underscores (fixes ASA showing `1/0`)
- 飞升列表 RCON 回退时优先使用 ARK Status 的人数上限，避免显示 `?`；仅当上限确实未知时才显示 `?`
  - ASA list prefers ARK Status `max_players` in the RCON fallback, so `?` appears only when the cap is genuinely unknown

## [1.0.1] - 2026-09-10

### 修复 / Fixed
- 兼容新版 `python-a2s` 字段改名（`players` → `player_count`）：修复 `/ase`、`/asa` 列表把在线服务器误判为离线的问题
  - Compatibility with the renamed `python-a2s` field (`players` → `player_count`); fixes `/ase` and `/asa` listing online servers as offline
- `/ase` 列表：A2S 查询失败时自动**回退 RCON** 判定在线与人数；A2S 超时 3s → 5s
  - `/ase` list now falls back to RCON when A2S fails; A2S timeout 3s → 5s
- `/asa` 列表：ARK Status 未命中或人数为 0 时，用 RCON 并发补全真实人数
  - `/asa` list fills real player counts via RCON when ARK Status misses or reports 0
- 新增配置 `list_rcon_fallback`（默认 `true`），可关闭列表的 RCON 回退
  - New `list_rcon_fallback` option (default `true`) to disable the RCON fallback
- 签到示例点数统一为 50 / 50
  - Example check-in points unified to 50 / 50

## [1.0.0] - 2026-09-10

### 初版发布 / Initial release

AstrBot 插件：方舟（ARK: Survival Evolved `ASE` / Ark: Survival Ascended `ASA`）服务器查询、QQ↔游戏账号绑定与每日签到机器人。
An AstrBot plugin that queries ARK servers, binds QQ ↔ game accounts and runs daily check-ins.

#### 功能特性 / Features
- **服务器查询 Server queries**
  - 在线状态 / 在线人数 / 地图 / 倍率 / 直连地址查询（`/ase` `/asa` `/ark` `/rate` `/direct` `/update_address`），支持定时自动刷新与手动刷新
  - Online status / player count / map / rates / direct-connect addresses with auto & manual refresh
- **跨服聊天转发 Cross-server chat relay**
  - 进化(ASE) ⇄ 飞升(ASA) ⇄ QQ 群实时互转（依赖游戏聊天写入 MySQL）
  - Real-time relay among ASE / ASA / QQ group (requires game chat rows in MySQL)
- **QQ ↔ 游戏账号绑定 Binding**
  - QQ 内直接绑定（进化=SteamID64 / 飞升=EOS）
  - 游戏公屏 `qqbind <QQ号>` / 验证码 `zsbind` 绑定；防冒绑与换绑规则
  - Bind in QQ (ASE = SteamID64, ASA = EOS); in-game `qqbind` / verification-code `zsbind`; anti-squatting + safe rebinding
- **每日签到 Daily check-in**
  - 进化/飞升每天各一次、只对一台在线服务器执行一次加点，杜绝重复发放（进化 +5000 / 飞升 +50，数值可在 `config.json` 调整）
  - Once per day per game, executed once on one online server so points can never be granted twice (ASE +5000 / ASA +50, configurable)
- **管理指令 Admin (owner only, DM)**
  - `/rcon`（单服 / 单地图 / 整版本）、`/加点` `/代加点`（给玩家或群内已绑定群友加 ArkShop 点数）
  - `/rcon` on a single target / map / whole version; `/加点` & `/代加点` grant ArkShop points
- **可选 LLM 引导 Optional LLM guide**
  - @机器人或触发词唤起，引导玩家使用指令、不编造实时数据（OpenAI 兼容接口，如智谱 GLM）
  - @bot or trigger words reply with an LLM that guides players toward commands (OpenAI-compatible, e.g. Zhipu GLM)
- **缓存更新提醒 Cache update alerts**：定时抓取版本包列表并私聊+群通知新版本

#### 工程说明 / Notes for contributors
- 仓库为**脱敏可发布模板**：无真实密钥 / QQ、群号 / 服务器 IP / 直连与 RCON 端口；所有运行配置集中在 `config.json`（本地填写，不入库）
  - This repo is a sanitized, publishable template: no real credentials, QQ/group IDs, server IPs, direct-connect/RCON ports. All runtime settings live in a local, git-ignored `config.json`.
- 请复制 `config.example.json` → `config.json` 后按 README 逐项填写；按 README「数据库准备」一节建库
  - Copy `config.example.json` → `config.json` and follow the README; create databases per the “Database setup” section.
- 文档：`README.md`（中文）/ `README.en.md`（English）

[1.0.1]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.0.1
[1.2.2]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.2.2
[1.2.1]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.2.1
[1.2.0]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.2.0
[1.1.0]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.1.0
[1.0.3]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.0.3
[1.0.2]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.0.2
[1.0.0]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.0.0
