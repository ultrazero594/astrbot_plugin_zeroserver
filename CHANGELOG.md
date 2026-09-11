# Changelog / 更新日志

All notable changes are documented here. 语义化版本：语义化版本 2.0 / [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.6.0] - 2026-09-11

### 新增 / Added
- **绑定支持 QQ 与 KOOK 双平台**：绑定记录新增按来源平台写入 `platform`（`qq_official` / `kook` / `aiocqhttp`）。验证码流程会把「开绑」时的平台一并存进待验证码记录，游戏内 `zsbind` 完成后按原平台入库，签到/查询行为不变
  - **Bindings work on both QQ and KOOK**: the binding row now records its source platform. The verification-code flow remembers which platform issued the code and stores it when the in-game `zsbind` completes
- `/帮助` 绑定段明确写出：QQ 和 KOOK 都能绑、进化与飞升各绑各的、两侧身份不互通，需要各绑一次
  - `/help` now states: both QQ and KOOK can bind, ASE and ASA are bound separately, and the two platforms are independent identities

### 隐私 / Privacy
- **公共区域一律打码**：群/频道里 `/我是谁`、`/查绑定`、`/解绑`、`/签到`、`/绑定`、`/代加点` 输出中的用户 ID 与游戏 ID 全部打码（保留前 6 后 4）；私聊仍然显示完整值，便于自查
  - **Masked in public channels**: user IDs and game IDs are masked (first 6 / last 4) in `/whoami`, `/mybind`, `/unbind`, `/signin`, `/bind` and `/atpoints` when used in a group/channel; DMs still show the full values
- 绑定结果私聊失败时的群内兜底公告，前缀由完整 ID 改为打码 ID
  - The group fallback announcement for bind results now uses a masked ID prefix
- **`/在线玩家` 名单里的游戏ID默认打码**：新增 `mask_player_ids`（默认 `true`），想恢复完整 ID（如排查用）设为 `false`
  - **Game IDs in the `/在线玩家` list are masked by default**: new `mask_player_ids` option (default `true`); set it to `false` to show full IDs for troubleshooting
- `/我是谁` 在公共区域会提示「需要完整 ID 请私聊机器人」
  - `/whoami` in a public channel now points users to a DM for the full ID

## [1.5.1] - 2026-09-11

### 优化 / Changed
- **`/帮助` 重排**：按「查服务器 / 查在线玩家 / 绑定&签到 / 本平台怎么用 / 消息互通 / 管理员」分组，行数更少、别名不再重复罗列（`/进化`= `/ase` 之类只写常用那个）
  - **`/help` rewritten**: grouped into server query / online players / binding & check-in / how-to-use-this-platform / relay / admin, with fewer lines and no duplicated aliases
- **按平台定制**：KOOK 侧写明「直接在频道里发指令即可，不用 @机器人」；QQ 侧保留「先 @机器人」与 openid 说明；`OneBot` / `qqbind` 相关行只在真的启用了 OneBot 时出现
  - **Platform-aware**: KOOK shows "just type in the channel, no @ needed"; QQ keeps the @-mention and openid notes; `OneBot`/`qqbind` lines only appear when OneBot is actually enabled
- 启用群间互通时，帮助里新增一行说明互通范围（如「QQ群、KOOK公共频道 之间互通；游戏内聊天会同时发到这些位置」）
  - When the bridge is on, help now states the relay scope
- 管理员段标题由「仅 Owner 私聊」改为「管理员」（因为现在也可在 `admin_channels` 里显示），并补上 `/更新地址`
  - Admin section retitled from "owner DM only" to "管理员" (it can now also appear in `admin_channels`) and now lists `/更新地址`

## [1.5.0] - 2026-09-11

### 新增 / Added
- **多主人（跨平台）**：新增 `owner_ids` 列表，与 `owner_qq` 合并生效——同一个服主在 QQ（openid/QQ号）和 KOOK（用户ID）下都能使用 `/rcon`、`/加点`、`/代加点`、`/测试推送` 等管理指令
  - **Multiple owners**: new `owner_ids` list merged with `owner_qq`, so one owner works across platforms (QQ openid/QQ number and KOOK user id)
- **管理员频道**：新增 `admin_channels`（群/频道标识列表）。在这些群/频道里，主人发 `/帮助` 能看到完整版（含【管理员】指令段），不必私聊
  - **Admin channels**: new `admin_channels`. Inside these groups/channels the owner sees the full `/help` including the admin section
- 新增内部辅助 `_is_owner()` / `_owner_ids()` / `_admin_channels()`，所有管理指令的主人校验统一走这里（原先各处各写一遍 ID 比较）
  - New helpers `_is_owner()` / `_owner_ids()` / `_admin_channels()`; all owner checks now go through them

### 变更 / Changed
- `_help_lines()` 的参数由 `is_owner_private` 改为语义更准的 `show_admin_help`
  - `_help_lines()`'s parameter renamed to `show_admin_help`

## [1.4.1] - 2026-09-11

### 新增 / Added
- **跨平台互推**：新增 `invite_kook` / `invite_qq` 配置。`/帮助` 会按当前平台自动附上「对方社区」入口——QQ 侧显示 KOOK 邀请链接，KOOK 侧显示 QQ 群号（留空则不显示）
  - **Cross-platform invitation**: new `invite_kook` / `invite_qq` config. `/help` appends the other community's entry depending on the current platform (KOOK invite on QQ, QQ group number on KOOK); empty values are simply omitted

### 优化 / Changed
- 平台名解析统一走 `_event_platform()`，`_help_lines()` 增加 `platform_name` 参数以便按平台定制内容
  - Platform name resolution is centralised in `_event_platform()`; `_help_lines()` now takes `platform_name`

## [1.4.0] - 2026-09-11

### 新增 / Added
- **多平台广播**：新增 `broadcast_targets` 配置（`[{platform,id,label}]`，platform 支持 `qq_official` / `kook` / `aiocqhttp`）。跨服聊天转发、缓存更新通知、绑定结果公告、`/测试推送`、LLM 回复统一走该列表——**同一份消息可同时发到 QQ 群和 KOOK 频道**；未配置时自动回退到 `notify_group`（向后兼容）
  - **Multi-platform broadcast**: new `broadcast_targets` config. Cross-server chat relay, cache notifications, bind-result announcements, `/testpush` and LLM replies all fan out over this list, so one message can reach both a QQ group and a KOOK channel; falls back to `notify_group` when empty
- **群间互通（QQ群 ↔ KOOK 频道）**：`bridge_enabled=true` 时，来自广播目标的消息会带 `🔀` 标记同步到其它目标，两个平台的群/频道互相可见
  - **Cross-platform bridge**: with `bridge_enabled=true`, messages from a broadcast target are mirrored to the other targets with a `🔀` marker
- 新增 `kook_forward_prefix`：KOOK 频道消息转发进游戏公屏时的前缀（默认 `💬 [KOOK]`）
  - New `kook_forward_prefix` for messages relayed from KOOK into the game

### 修复 / Fixed
- 主动消息不再写死只发 QQ：此前 LLM 回复、通知、绑定结果在 KOOK 场景会发到 QQ 群
  - Proactive messages are no longer hard-wired to QQ (previously an LLM reply or notification triggered from KOOK went to the QQ group)
- 防循环标记扩充 `[KOOK]` 与 `🔀`，转发副本不会被二次转发（否则 QQ群 ↔ KOOK 会互相刷屏）
  - Loop-guard markers now include `[KOOK]` and `🔀` so mirrored copies are never re-relayed

### 变更 / Changed
- 仅 `broadcast_targets` 里配置的群/频道会触发「转发到游戏公屏」，其它拉了机器人的群/频道不会再往 28 台服务器刷消息
  - Only groups/channels listed in `broadcast_targets` relay messages into the game

## [1.3.3] - 2026-09-11

### 脱敏 / Sanitization
- `/加点` 用法示例里的 ID 改为占位符（`<EOS 32位hex>` / `<SteamID64 17位数字>`），不再出现真实玩家 ID
  - The `/addpoints` usage example no longer contains real player IDs (now placeholders)
- `docs/qqofficial-commands.md`：移除真实群 `group_openid` 与真实官网域名，改为占位形式（`10F2****…` / `https://example.com/`）
  - `docs/qqofficial-commands.md` no longer contains the real group openid or the real site domain

## [1.3.2] - 2026-09-11

### 优化 / Changed
- 绑定/签到命令不再每次都跑一遍建表与元数据检查：`_ensure_qq_tables()` 首次通过后置 `_qq_tables_ready`，后续调用直接返回（原先每条 `/绑定`、`/签到` 都会执行 2 条 `CREATE TABLE IF NOT EXISTS` + 3 次 `information_schema` 查询）
  - Binding / check-in commands no longer re-run table setup every time: `_ensure_qq_tables()` now short-circuits after the first successful check (previously every `/bind` and `/signin` ran two `CREATE TABLE IF NOT EXISTS` plus three `information_schema` queries)
- 抑制 aiomysql 对 `CREATE TABLE IF NOT EXISTS` 打出的 `Warning: Table '...' already exists` 噪音（原先每条命令都会在日志里刷一次）
  - Suppressed aiomysql's `Warning: Table '...' already exists` noise from `CREATE TABLE IF NOT EXISTS` (previously printed on every command)
- `_ensure_qq_tables(force=True)` 可强制重新检查（供排查时手动调用）

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
