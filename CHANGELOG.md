# Changelog / 更新日志

All notable changes are documented here. 语义化版本：语义化版本 2.0 / [Semantic Versioning](https://semver.org/lang/zh-CN/).

## [1.20.1] - 2026-09-12

### 修复 / Fixed
- 绑定帮助里的位置说法改准确：飞升的 EOS **在游戏里打开商店（ArkShop）就能看到自己的**（原文写成"商店页面"，容易被理解成网页）
- Wording fix: the ASA EOS ID is visible in the **in-game shop (ArkShop)** UI — the previous "shop page" wording read like a website

## [1.20.0] - 2026-09-12

### 变更 / Changed
- **帮助菜单重排（绑定部分）**：只教两条真正可用的路 —— ① **直接绑定**（飞升填 EOS 32 位 ID，**游戏中打开商店（ArkShop）就能看到自己的**；进化填 SteamID64）② **验证码开绑**（`/绑定 <游戏> 开绑` → 游戏公屏 `zsbind <验证码>`，换绑也走它）。`/我的ID` 的用途改为"`/关联` 打通多平台 / 找管理员核对身份"。新增配置 `id_source_hint`（默认写明"飞升 EOS 在游戏内商店 ArkShop 就能看到"，可自行改写）
- **游戏内 `qqbind` 通道默认关闭**（`game_bind.qq_cmd=false`，原为 true）：该通道要求在游戏公屏贴出自己的身份 ID，有冒绑风险，而"直接发 EOS/SteamID"与"验证码 `zsbind`"两条路更安全。关闭后若仍有玩家在公屏发 `qqbind`，会记 INFO 日志（`⏭️ 游戏内 qqbind 已停用…`）—— 之前是**静默忽略**，导致"玩家说在游戏里发了没反应"查不出来
- **修复：`qqbind` 漏打空格时会被当普通聊天转发到 QQ/KOOK**（如游戏公屏的 `qqbind22C5F7CC…`）：新增宽松识别 `BIND_CHAT_RE`，这类消息一律静默吞掉，不再把身份 ID 外泄到群里
- Help menu reorganized (bind section): only the two working paths are documented (direct bind with the EOS ID from the shop page / SteamID64, or the 6-digit `zsbind` code). `/我的ID` now documents its real uses. New `id_source_hint` config. The legacy in-game `qqbind` channel is **off by default** and now logs instead of silently ignoring; a whitespace-less `qqbind…` no longer leaks into group chat via the relay.

## [1.19.4] - 2026-09-12

### 修复 / Fixed
- **转发到公屏/互通时 @提及里的真实 ID 会泄露**：QQ 官方机器人的 @ 在消息文本里是 `<@openid>`（32 位串）、KOOK 是 `(met)userid(met)`，之前原样转发 → 游戏公屏出现 `[QQ]: 【跨服】某某: <@<你的openid>> …`（真实 ID 直接暴露）。新增 `MENTION_RE`，在 `_game_safe()`（覆盖 RCON 与 CCA 两条发往游戏的通道）与**跨平台互通**文案里统一替换成 `@某人`；长度不足 5 位的 `<@123>` 之类不动，避免误伤
  - **Fixed leaking real IDs through @mentions**: QQ puts `<@openid>` and KOOK uses `(met)userid(met)` in message text; those were relayed verbatim into the game chat. A new `MENTION_RE` rewrites them to `@某人` in `_game_safe()` (both RCON & CCA game-facing paths) and in the cross-platform bridge text

## [1.19.3] - 2026-09-12

### 新增 / Added
- **游戏公屏上显示中文「跨服」**（用户问"能改成中文跨服?"）：CCA 的 `Map` 标签字段只吃 ASCII，但**发送者字段支持中文** —— 新增配置 `cca_sender_prefix`（默认 `【跨服】`）拼在发送者前面；同时把 ASCII 标签缩回短值 `cca_map_label="QQ"` / `cca_map_label_kook="KOOK"`
  - 效果：游戏里显示 **`[KOOK]: 【跨服】萌新0号: 内容`** / **`[QQ]: 【跨服】萌新0号: 内容`**
  - Chinese 「跨服」now shows on the game chat line: CCA's `Map` field is ASCII-only, but the sender field renders CJK fine — new `cca_sender_prefix` (default `【跨服】`) is prepended to the sender, and the ASCII labels shrink back to `QQ` / `KOOK`

## [1.19.2] - 2026-09-12

### 修复 / Fixed
- **CCA 标签里的中文会变乱码**（用户报"游戏里面怎么不是跨服kook"）：实测 CCA 的 `Map` 标签字段**只吃 ASCII** —— 写「跨服-KOOK」时游戏里显示成 `[|σ¤¥η∧-KOOK]:`（UTF-8 字节被按单字节解码）。改为**纯 ASCII 标签**：默认 `cca_map_label = "CrossServer-QQ"`、`cca_map_label_kook = "CrossServer-KOOK"`（显示为 `[CrossServer-KOOK]: 名字: 内容`）；并新增 `_cca_label_safe()` 强制只保留可打印 ASCII，即使配置里写了中文也会被清掉而不是打成乱码（`_cca_labels()` 同步用它，保证防回声比较与写库取值一致）
  - **Fix: non-ASCII CCA map labels become mojibake** — CCA's `Map` field is single-byte-decoded, so 「跨服-KOOK」 rendered as `[|σ¤¥η∧-KOOK]`. Labels are now ASCII-only (`CrossServer-QQ` / `CrossServer-KOOK`) with a `_cca_label_safe()` guard

## [1.19.1] - 2026-09-12

### 变更 / Changed
- CCA 通道的公屏标签更醒目：默认 `cca_map_label` / `cca_map_label_kook` 从 `QQ群` / `KOOK` 改为 **`跨服-QQ群` / `跨服-KOOK`**（CCA 会渲染成 `[跨服-KOOK]: 名字: 内容`）
- 写 CCA 时 `Map` 标签也过一遍 `_game_safe()`，避免标签里出现 emoji 后被游戏渲染成缺字形方块
  - Clearer CCA labels (`跨服-QQ群` / `跨服-KOOK`) and the label now goes through `_game_safe()` too

## [1.19.0] - 2026-09-12

### 新增 / Added
- **QQ/KOOK → 游戏公屏 的发送通道可选**（新配置 `game_send_via = rcon | cca`）：
  - `rcon`（默认）：原来的做法，`serverchat` 并发发给所有 RCON 目标
  - `cca`：把消息 **INSERT 进 CrossChatAscended 的 `cross_chat` 表**（`asachat` / `asechat` 两个库），由 CCA 在各自服务器上打印 —— 沿用 CCA 自己的格式（`[地图]: 发送者: 内容`），且**只有装了 CCA 的服会收到**；实测 0.25s 内上屏、中文正常
  - 相关配置：`cca_map_label` / `cca_map_label_kook`（写表时 `Map` 字段用的标签，也用于识别"自己写的行"）、`cca_fallback_rcon`（默认 true：CCA 写失败时回退 RCON，避免消息丢失）
  - 配套防回声：跨服转发读表时会**跳过 `Map` 等于上述标签的行**，否则 QQ→游戏 的消息会被读回来又发回 QQ
  - Optional delivery channel for QQ/KOOK → game chat: `game_send_via = rcon | cca`. The `cca` mode inserts into CrossChatAscended's `cross_chat` table (both `asachat` and `asechat`), letting CCA print it on every server that runs it (with CCA's own formatting); write failures fall back to RCON by default, and the game→chat relay skips rows whose `Map` equals our labels to avoid echo loops

## [1.18.5] - 2026-09-12

### 修复 / Fixed
- **游戏公屏出现"问号方块"**：实测（往 28 台发 TEST1/TEST2/TEST3 三行并读游戏画面）确认——**中文完全正常**（`中文测试汉字`、中文玩家名都显示无误），出问题的是 **emoji**：`💬`、`🦖` 这类字形 ARK 没有，渲染成"◇ 里带问号"的缺字形方块。而转发前缀恰好是 `💬 [QQ群]` / `💬 [KOOK]`
  - 修法：①前缀去掉 emoji（`[QQ群]` / `[KOOK]`）；②新增 `_game_safe()` 统一清理**发往游戏公屏的文本**——剔除 emoji/符号区段（含 U+1F000–1FAFF、U+2600–27BF、U+2190–21FF、U+2B00–2BFF、U+2000–206F 通用标点、变体选择符/ZWJ 等），**中文与 ASCII 原样保留**；③三处 `serverchat`（QQ/KOOK 转发、倍率更新广播、游戏内跨服互转）都过一遍
  - **Fixed the "question-mark boxes" in game chat**: an A/B test (three lines sent to all 28 servers, then read off the game screen) showed Chinese renders fine — only **emoji** become missing-glyph boxes. The relay prefix was `💬 [QQ群]`. Now: emoji-free prefixes, plus a `_game_safe()` sanitizer applied to every `serverchat` payload

## [1.18.4] - 2026-09-12

### 修复 / Fixed
- **`/我的ID` 显示"别人的 ID"的错觉**：它原来直接输出 `_resolve_identity()` 的结果，而 `/关联` 打通后这个值是**主身份**（比如 QQ 用户在 QQ 里查到的是 KOOK 那串 id），用户会以为查错了。现在**先显示当前平台自己的 ID**，若已关联再补一行「已关联到主身份：xxx」并说明游戏里 `qqbind` 两串都能用
  - `/myid` used to print the resolved *main* identity, which after `/关联` is the other platform's id — confusing. It now prints the caller's own platform id first, and adds a line with the linked main identity when they differ

## [1.18.3] - 2026-09-12

### 修复 / Fixed
- **@机器人 发的指令不再被转发到游戏公屏**（用户报"kook和qq群@机器人发送指令，会被传消息"）：原来只靠 `event.is_at_or_wake_command` 判断"这是给机器人的指令，别转发"，但适配器给的 `@` 有时**不会被识别成 wake**（`At.qq` 与 `get_self_id()` 不一致），该标记为 False → 消息继续走到"转发到游戏 + 群间互通"分支，指令被刷进游戏公屏。现在加了兜底 `_at_bot()`：扫消息组件（`At` / `AtAll`）并在文本里找 `[At:` / `(met)`，只要**@了机器人（或@全体）**或**看起来像指令**就一律不转发（也不再对已 @ 过的消息回"请先 @"的提示）
  - **Commands sent with an @mention are no longer relayed to the game** — the old guard relied solely on `is_at_or_wake_command`, which the adapters sometimes fail to set for mentions (mismatch between `At.qq` and `get_self_id()`), so the message fell through to the game-relay branch. A new `_at_bot()` fallback inspects message components and text; anything addressed to the bot (or looking like a command) is skipped

## [1.18.2] - 2026-09-12

### 变更 / Changed
- **KOOK 按钮的结果改回点击发生的频道**（v1.18.1 曾一律私聊，用户反馈"这又不是验证码"）：从点击事件的 `extra.body` 里取 `target_id`（频道 id）与 `channel_type`，**在频道里点的就回频道、在私聊里点的才回私聊**；频道场景下合成的也是"频道消息"事件，所以 ID 照常打码、逻辑与用户手打指令完全一致。回频道失败时才退回私聊
  - **KOOK button results now go back to the channel where the click happened** (v1.18.1 sent everything to DM, which the user rightly rejected — results aren't secrets). The handler reads `target_id`/`channel_type` from the click payload: channel clicks reply in the channel (with the usual ID masking, since the synthetic event is a channel message), DM clicks reply in DM; falls back to DM only if the channel send fails

## [1.18.1] - 2026-09-12

### 修复 / Fixed
- **KOOK 按钮点了没回执**（v1.18.0 的补丁已经能收到点击并执行指令，但结果发不出去）：
  - 原因一：注入管道时伪造了 `message_id`（`btnclick-<时间戳>`），AstrBot 据此生成**引用回复**，KOOK 直接拒收：`40000 引用不存在或者你没有权限操作`
  - 原因二：注入管道会让 AstrBot 的 **LLM 也对同一条消息回一句**（一按出两条回复）
  - 现在改为**不注入管道**：用 `adapter_inst.create_event()` 造一个"点击者私聊"事件对象，直接调用插件内部的指令处理器（在线玩家 / 状态 / 签到 / 查绑定 / 菜单 / 帮助 / 直连 / 倍率 / 我的ID），把结果**私聊**发回点击者 —— 既没有伪造 msg_id 的引用问题，也不会触发 LLM
- **KOOK card button clicks now actually reply**: v1.18.0's patch received the click and ran the command, but the reply was rejected by KOOK (`引用不存在或者你没有权限操作`) because the injected message carried a fake `message_id` → AstrBot built a quote-reply. It also caused the LLM to answer the same message (two replies per click). The handler no longer injects into the pipeline: it builds a synthetic private-chat event, calls the plugin's own command handlers, and DMs the result to the clicker

## [1.18.0] - 2026-09-12

### 新增 / Added
- **KOOK 卡片按钮可用**（实验功能，配置 `kook_button_patch`，默认开）：AstrBot 的 KOOK 适配器只处理 `KMARKDOWN/CARD`，把 `SYSTEM(255)` 里除"角色更新"以外的系统通知（含 `extra.type="message_btn_click"`，即**卡片按钮点击**）当作未实现通知丢弃。插件现在给 `KookPlatformAdapter._on_received` 包一层补丁：识别到按钮点击后，取 `extra.body.value`（如 `/在线玩家`）**当作该用户发来的一条私聊消息注入 AstrBot 管道**，于是所有指令逻辑（白名单、参数、打码规则）原样复用，**结果私聊回点击者**、不刷频道
  - **KOOK card buttons now work** (experimental, `kook_button_patch`): the upstream adapter drops `message_btn_click` system notifications; the plugin patches `_on_received` and re-injects the button value as a private message from the clicker, so all existing command logic applies and the reply goes to their DM
- 实测依据：DEBUG 日志确认 KOOK 会下发该事件（`d.type=255`、`extra.type=message_btn_click`、`extra.body={value,user_id,target_id,user_info}`），只是 AstrBot 侧忽略

### 说明 / Notes
- 补丁是**宿主内部包装**，AstrBot 升级后若适配器实现改变可能失效；出问题把 `kook_button_patch` 设为 `false` 即可完全回退（不影响其它功能）
- 卡片消息（type 10）可用 `action-group` 放最多 4 个按钮，`click:"return-val"` 的 `value` 就是点击后执行的内容

## [1.17.1] - 2026-09-12

### 优化 / Changed
- **帮助文案按平台说清楚**：QQ 群那行改为「发 `/指令` 即可（带 `/` 前缀就会响应），@机器人 也可以」；KOOK 行改为「KOOK 频道：直接发 `/指令` 即可，不用 @机器人」；私聊行统一为「私聊：直接发 `/指令` 即可」
- 绑定分类页里过时的一行（「游戏公屏：qqbind <QQ号>（OneBot 渠道）」）改为「游戏内也能绑：/我的ID 查身份 ID → 游戏公屏发 `qqbind <ID>`」
- **仓库文档刷新**：`docs/qqofficial-commands.md` 指令一览补齐 `/菜单`、`/状态`、`/我的ID`、`/关联`、`/解绑` 等；群聊面板请求体更新为新指令集；小贴士改为「群内发 `/指令` 即可，不必 @机器人」，并注明 QQ 个人认证私聊受限时的验证码兜底行为

## [1.17.0] - 2026-09-12

### 新增 / Added
- **`/我的ID`**（别名 `/我的id`、`/myid`）：显示你自己的身份 ID**全文**（不限于私聊——QQ 个人认证下没有私聊可用），并给出「复制这串 → 进游戏公屏发 `qqbind <ID>`」的三步用法；带"别外传"提示。专为"不想去查 EOS/SteamID"的玩家设计
- **游戏内 `qqbind` 支持 openid**：`QQBIND_RE` 从只认 5-12 位纯数字放宽为 `[A-Za-z0-9_-]{5,64}`（仍要求整行只有 `qqbind <ID>`，避免误匹配聊天内容），因此官方机器人玩家可以复制自己的 openid 到游戏里完成绑定；绑定记录的 platform 按"是否纯数字"自动判为 `legacy` / `qq_official`（原来硬编码 `aiocqhttp`）
- **验证码群内兜底**（配置 `bind_code_public_fallback`，默认 `true`）：QQ 个人认证收不到私聊时，`/绑定 <游戏> 开绑` 会把 6 位验证码直接回在当前会话里（一次性、限时、附"请勿外传，别人用了会绑到他自己的角色上"），否则 QQ 玩家完全走不了验证码流程。想严格保密可设为 `false`
- `/help 绑定` 分类页、`BIND_GUIDE`、游戏内帮助文案同步更新为四种绑定方式

## [1.16.0] - 2026-09-12

### 新增 / Added
- 新增配置 `arkshop_exclude_servers`（默认 `["Club", "海洋"]`）：**没装 ArkShop 插件的服务器**名单，按**名字子串**匹配（不区分大小写）。命中后：
  - `/签到`、`/加点`、`/代加点` 选服务器时会跳过它们（`_pick_online_rcon_target` 过滤）
  - 倍率更新时的 `ForceUpdateDynamicConfig` 广播也会跳过它们（`serverchat` 照旧发给全部，因为那是原生命令）
  - 新增 `New config arkshop_exclude_servers` (default `["Club", "海洋"]`): servers **without the ArkShop plugin**, matched by case-insensitive name substring; point-granting commands and the rate-refresh broadcast skip them

## [1.15.1] - 2026-09-12

### 修复 / Fixed
- **验证码泄露到公共区域（严重）**：`/绑定 <游戏> 开绑` 私聊发码成功后，群/频道里那条「开绑成功」的回复把下一步提示 `下一步：在游戏公屏输入：zsbind <验证码>` 一并打印了 —— 而该提示字符串里**带着真实验证码**，等于把码贴进公共频道（QQ 群同样受影响）。现在公共回复固定写成 `zsbind <验证码>（验证码看你我私聊）`，`hint` 只在私聊文本里使用
  - **Security fix**: the public "binding started" reply leaked the actual verification code (it printed the `zsbind <code>` hint). The code is now only ever sent in the private message; public replies show `zsbind <验证码>`
- 主动消息的日志文案改为平台中立（原来无论哪个平台都打印「QQ 官方机器人已发送」，排查时误导）

## [1.15.0] - 2026-09-12

### 新增 / Added
- **编号菜单**：新增 `/菜单`（`/menu`）——QQ 个人认证下用不了消息按钮，改用「编号快捷入口」代替：发 `/1` 就是 `/在线玩家`、`/2` 状态、`/3` 签到、`/4` 查绑定、`/5 帮助 查询`、`/6 帮助 绑定`。带斜杠的短指令在群里本来就能唤醒，因此**零平台权限依赖、QQ/KOOK 通用**
  - **Numbered menu**: `/menu` prints a numbered shortcut list; `/1`–`/6` dispatch to the corresponding internal commands (works in both QQ groups and KOOK, since a slash-prefixed message wakes the bot without needing any platform capability)
- `/帮助` 总览加一行提示「懒得记指令？发 /菜单 用编号」

## [1.14.0] - 2026-09-12

### 变更 / Changed
- **绑定流程改以「直接绑定」为主路径**：QQ 开放平台的「允许被其他 QQ 用户添加使用」**只对企业开发者灰度开放，个人认证开发者无法开启** → 普通玩家拿不到机器人私聊，验证码开绑走不通。因此：
  - `BIND_GUIDE` 改为「① 直接绑定（推荐，不需私聊）② 换绑＝先 `/解绑` 再绑定 ③ 验证码开绑（需机器人能私聊你，个人认证暂不支持）」三选一
  - 私聊发码失败的提示直接点明原因（个人认证无法开通该能力）并给出替代路径
  - `/帮助 绑定` 分类页同步：首行改为「直接绑定（推荐）」，换绑改为「先 /解绑 再重新绑定」
  - Direct-ID binding is now the primary path, because "allow other QQ users to add the bot" is enterprise-only (gradual rollout) — individual-certified bots cannot enable it, so users never receive the DM code. Rebinding is now "unbind, then bind again"; code-based binding remains as an alternative
- `/help 绑定` section updated accordingly

## [1.13.3] - 2026-09-12

### 修复 / Fixed
- **修复 `metadata.yaml` 的无效 YAML**：第 4 行被写成了 `version: version: "1.11.0"`（从 v1.11.0 起一直存在，是脚本里用局部字符串替换版本号导致的），已改回 `version: "1.13.3"`
  - Fixed invalid YAML in `metadata.yaml`: line 4 was `version: version: "1.11.0"` (present since v1.11.0, caused by a partial-string version replacement in a script)
- 私聊发码失败时的提示更具体：一是"你还没加机器人为好友"，二是"QQ 开放平台 → 好友（私聊）→ 允许被其他 QQ 用户添加使用"（该开关关闭时，普通玩家收不到私聊验证码，开绑/换绑都做不了）
  - Clearer hint when the DM fails: (1) add the bot as a friend first, (2) enable “allow other QQ users to add the bot” on the open platform — with it off, regular users never receive the verification code

### 优化 / Changed
- 「绑定三步」第一步改为「先在 QQ 里添加机器人为好友」；「直接发 ID 绑定」一行注明**无需私聊**
  - The 3-step guide now starts with "add the bot as a friend first", and the direct-ID binding line notes it needs no DM

## [1.13.2] - 2026-09-11

### 优化 / Changed
- **未绑定提示改成「绑定三步」**：`/签到` `/查绑定` 在未绑定时的回复，从一句话改成编号步骤（① 保持角色在线 → ② 发 `/绑定 进化 开绑` → ③ 游戏公屏 `zsbind <验证码>`），并说明「也可直接发 ID 绑定」以及「老玩家走这三步会自动接回原账号」
  - The not-bound reply now shows a numbered 3-step binding guide (keep the character online → `/绑定 进化 开绑` → `zsbind <code>` in game), mentions direct-ID binding, and notes that legacy rows are re-attached automatically

## [1.13.1] - 2026-09-11

### 修复 / Fixed
- **又一处地址泄露**：新增的服务器状态提醒 `/状态`、以及 `/签到` `/加点` `/代加点` `/rcon` 的成功提示里，服务器名直接用了内部 RCON 目标名（形如 `ASA-繁星 a2.example.cn:18083`），把 **RCON 地址+端口**带进了群/频道。新增 `_target_label()` 在展示前统一剥掉尾部的 `host:port`，日志里仍保留完整地址便于排查
  - Another address leak fixed: status notifications, `/状态`, and the success messages of `/签到` `/加点` `/代加点` `/rcon` printed the internal RCON target name (e.g. `ASA-繁星 a2.example.cn:18083`), exposing the RCON address/port. New `_target_label()` strips the trailing `host:port` for display (logs keep the full address)

## [1.13.0] - 2026-09-11

### 新增 / Added
- **服务器上/下线提醒**：随 `check_interval_minutes` 周期（默认 10 分钟）并发探测每台服务器的 RCON，状态发生变化时把提醒推送到 `broadcast_targets`（QQ 群 + KOOK 频道）
  - 首轮只建立基线**不播报**（避免重启后一次性刷 28 条）；**连续 `status_notify_fail_threshold`（默认 2）次探测失败**才判定离线，防抖动误报；恢复则立即播报；单条消息最多列 `status_notify_limit`（默认 8）条变化
  - 配置：`status_notify_enabled`（默认 `true`）、`status_notify_fail_threshold`、`status_notify_limit`
- 新增指令 `/状态`（`/serverstatus`）：查看当前各服务器在线 / 离线 / 未知一览
- Server up/down notifications, probed over RCON each cycle; first round only builds a baseline, offline requires N consecutive failures (anti-flapping), recovery is reported immediately; new `/状态` command lists the snapshot

## [1.12.0] - 2026-09-11

### 新增 / Added
- **新人首次互动欢迎**：插件拿不到"成员入群"事件（QQ 官方机器人不提供、KOOK 的加入事件也没被适配器转成插件事件），因此改用**首次交互**代替——某人在机器人回复里第一次出现时，回复底部附一句欢迎引导，并把该用户写入 `seen_users.json`，之后不再重复。配置：`welcome_new_user`（默认 `true`）、`welcome_text`（可自定义文案）；主人自己不受影响
  - **First-interaction welcome**: since no member-join event exists on either platform, the first time a user gets a reply from the bot a welcome line is appended and the user is recorded in `seen_users.json` (never repeated). Config: `welcome_new_user`, `welcome_text`; the owner is skipped

## [1.11.2] - 2026-09-11

### 新增 / Added
- 新增配置 `qq_keyboard_template_id`：QQ 开放平台**「消息按钮模板」审核通过后**填入模板 id，插件会自动改用 `keyboard={"id": "<模板id>"}` 发送。平台开通能力后**只需填一个配置**，无需改代码
  - New `qq_keyboard_template_id`: once the open platform approves the "message button template", fill in its id and the plugin automatically sends `keyboard={"id": ...}`

### 说明 / Notes
- 实测确认：内联 `keyboard` 字段会被 QQ 平台**静默忽略**（API 返回成功、手机与 PC 客户端都不渲染按钮）；官方要求先申请「Markdown 消息模板 + 消息按钮模板」并审核
  - Confirmed by testing: inline `keyboard` payloads are silently ignored by QQ (API succeeds, but neither mobile nor desktop renders buttons). An approved button template is required

## [1.11.1] - 2026-09-11

### 变更 / Changed
- `/测试按钮` 支持指定变体：`/测试按钮`（1=文本+按钮）、`/测试按钮 2`（markdown+按钮）、`/测试按钮 3`（不带 msg_id 的主动消息+按钮）、`/测试按钮 all`（三个一起发），便于平台开通能力后快速定位可用组合
  - `/testkb` now accepts a variant argument (1 text+buttons, 2 markdown+buttons, 3 proactive without msg_id, `all`)

## [1.11.0] - 2026-09-11

### 新增 / Added
- **实验：QQ 群消息带可点按钮**（Owner 指令 `/测试按钮`）——绕过 AstrBot 消息链，直接调 botpy 的 `post_group_message(keyboard=...)` 发送按钮；按钮 `action.type=2`（点击即把预设文本当指令发出）。按钮失败会原样回报错误信息便于定位（多半是 QQ 开放平台未开通「按钮」能力）
  - **Experimental QQ inline buttons** (owner command `/testkb`): bypasses the AstrBot message chain and calls botpy's `post_group_message(keyboard=...)` directly; buttons use `action.type=2` (clicking sends the preset text as a command). Failures report the raw error for diagnosis
- 命令与按钮映射：在线玩家 / 签到 / 查绑定 / 帮助查询

### 优化 / Changed
- **`/帮助` 总览再瘦身到 10 行以内**（QQ 群普通版 7 行）：去掉分节标题与空行，改成「3 条最常用 + 一行指令汇总 + 平台提示 + 互通提示」，细节全部走 `/帮助 查询|绑定|管理`
  - `/help` overview slimmed to under 10 lines (7 for a regular QQ group): three most-used commands, one summary line, one platform hint, one relay hint; details live in `/help 查询|绑定|管理`

## [1.10.0] - 2026-09-11

### 优化 / Changed
- **`/帮助` 瘦身 + 分级**：总览从 26 行压到 20 行（群聊普通版 421 字），只留「最常用」三条 + 分类入口；细节按需查看，不再一次性糊满屏
  - `/help` slimming: the overview dropped from 26 lines to 20 (421 chars for a regular QQ group), keeping only the three most-used commands plus section entry points
- 新增分类详情页：
  - `/帮助 查询` → 在线玩家 / 状态 / 倍率 / 直连（8 行）
  - `/帮助 绑定` → 绑定 / 开绑 / 解绑 / 关联 / 签到（9 行）
  - `/帮助 管理` → RCON / 加点 / 代加点 / 测试推送 / 关联管理（仅主人可见，非主人提示去私聊）
  - New section pages: `/help 查询` `/help 绑定` `/help 管理` (admin page is owner-only; others are told to DM)
- 管理指令段不再默认出现在每次 `/帮助` 里，只在 `/帮助 管理` 或分类页显示；互推入口行在所有分类页底部照常附带

## [1.9.0] - 2026-09-11

### 新增 / Added
- **所有回复统一附带互推入口**：新增 `@filter.on_decorating_result()` 钩子，在消息发送前给**任意回复**底部补上「对方社区」一行（QQ 侧显示 KOOK 邀请、KOOK 侧显示 QQ 群号），不再只有 `/帮助` 才有；`/帮助` 自身已含该行时会自动跳过不重复；回复里带官网页脚时，该行会插在页脚**之前**
  - **Invite line on every reply**: a new `on_decorating_result` hook appends the other community's entry to any outgoing reply (KOOK invite on QQ, QQ group number on KOOK), not just `/help`; it skips when the line is already present and inserts before the site footer when there is one
- 新增配置 `invite_on_reply`（默认 `true`）：关掉后只保留 `/help` 里的那一行
  - New `invite_on_reply` switch (default `true`); set to `false` to keep the line only in `/help`

## [1.8.1] - 2026-09-11

### 修复 / Fixed
- `/帮助` 里一行过时说明：「QQ 与 KOOK 是两套身份：两边都要签到，就得各绑一次（同一个人的两侧不互通）」——v1.7.0 起有 `/关联`、v1.8.0 起同游戏账号还会自动关联，这句已经和上一行矛盾且误导。改为「一边绑定后，另一个平台只要 /关联 打通就共用同一份绑定；绑同一游戏账号会自动关联」
  - Removed a stale `/help` line that claimed the two platforms are fully independent ("you must bind twice"); it contradicted the `/link` line right above it since v1.7.0/v1.8.0
- 「绑定/签到建议都在私聊完成（群与私聊的用户ID可能不同）」改为「绑定/签到建议在私聊完成；群与私聊身份不同时用 /关联 打通」
  - The DM advice line now points to `/link` for cross-scene identities

## [1.8.0] - 2026-09-11

### 新增 / Added
- **同一游戏账号自动关联**：绑定/换绑时如果发现**同一个游戏账号已绑在另一个平台身份**上，自动把两边关联起来（无需手动 `/关联`），并在回复里提示「已自动关联（两边共用绑定与签到）」。配合按游戏账号判重，同账号每天仍只加一次点数
  - **Automatic linking by game account**: when a newly bound game account already exists under another platform identity, both are linked automatically (no manual `/link` needed)
- **身份关联管理（Owner）**：`/关联 列表` 查看全部关联（ID 打码），`/关联 解除 @某人` 强制解除他人关联
  - Owner tools: `/link list` and `/link unlink @user`
- 部落名查询增强：最近一条聊天记录没写部落名时，继续回溯该玩家**最近一条带部落名**的记录，命中率更高；显示文案简化为 `部落：未知`
  - Tribe lookup now falls back to the player's most recent record that actually carries a tribe name; the placeholder is shortened to `部落：未知`

### 变更 / Changed
- 生产副本的 `DEFAULT_CONFIG` 补齐 `servers_html_url` / `rcon_html_url` / `dynamic_ini_url` / `cache_mirror_urls` / `llm_*`，这些项现在会出现在 AstrBot 插件配置页里（代码仍保留常量兜底）
  - The production `DEFAULT_CONFIG` now lists the fetch URLs, `cache_mirror_urls` and the `llm_*` keys so they show up in AstrBot's plugin config page (constants remain as fallbacks)

## [1.7.1] - 2026-09-11

### 优化 / Changed
- **代码体检（静态审查）后的清理**：
  - 删除死代码：`_alias_of()`（定义后从未调用）、`_check_whitelist()` 里那段 `if "kook" in event.session_id` 判断（KOOK 的 session_id 是纯数字频道ID，永远不会命中）
  - `/关联 开码` 在群/频道里改为**优先私聊发码**，私聊失败才在本会话显示并加警告，避免关联码被旁人截走
  - `_link_identities()` 补齐：关联时把别名下的 `qq_checkin` 签到记录一并搬到主身份（`UPDATE IGNORE` + 清理残留），避免两边各自留下当天的签到行
  - README 中英补充 `owner_ids` / `admin_channels` / `invite_kook` / `invite_qq` 四个配置项说明
- 审查结论：无 TODO/未实现标记；40 个命令处理器与别名均正常注册；`self.config` 读取的键都有 `.get` 兜底；`_check_updates` 等"看似未被调用"的方法实际是通过 `scheduler.add_job(self._check_updates, …)` 与 `run_in_executor(None, self._xxx_sync, …)` 以函数对象形式引用的，不是死代码

## [1.7.0] - 2026-09-11

### 新增 / Added
- **QQ ↔ KOOK 身份关联（`/关联`）**：一边绑定，两边通用
  - `/关联 开码` → 生成 6 位关联码（3 分钟有效、一次性）
  - 到另一个平台发 `/关联 <关联码>` → 两个身份连通，共用同一份绑定与签到记录
  - `/关联 状态` 查看关联情况，`/关联 解除` 取消关联
  - 关联后：在任一边 `/签到` 都会按主身份记账，配合 v1.6.1 的按游戏账号判重，**同一游戏账号每天仍然只加一次点数**；绑定行与签到记录都归到主身份下，绑定时如两边绑了不同账号以主身份（开码方）为准
  - New identity linking across platforms: `/link code` → `/link <code>` on the other platform makes both share one binding + check-in record; `/link status`, `/link unlink` included

### 修复 / Fixed
- **私聊发送现在按平台走**：`_send_private_msg()` 原先固定用 QQ 官方机器人发送，KOOK 用户走「开绑」时验证码会被发到 QQ（必然失败）→ 现在按事件平台选择适配器；绑定结果通知同样带上绑定所在平台
  - **DMs are now platform-aware**: `_send_private_msg()` used to always send through the QQ official adapter, so a KOOK user's bind-verification code was sent to QQ and always failed. The adapter is now chosen from the event platform, and bind-result notifications carry the binding's platform

## [1.6.2] - 2026-09-11

### 修复 / Fixed
- **`/在线玩家` 不再输出服务器地址**：名单标题原本是 `【地图】a2.xxx:16060（1 人）`，会把直连/RCON 地址暴露在群/频道里；现在改为 `【地图】1 人在线`
  - **No more server addresses in `/在线玩家`**: the header used to print `【map】host:port (n players)`, leaking connect/RCON addresses into public chats; it now reads `【map】N 人在线`

### 新增 / Added
- **群里漏 @机器人 的指令会给一次提示**：在 QQ 群里直接发 `签到` / `/绑定 …`（没 @机器人）时，AstrBot 不会把它派发给指令处理器、玩家会以为"没反应"；现在会回一句「群里发指令要先 @机器人 哦～例如：@机器人 /帮助」，且该消息不会被转发到游戏
  - **Hint when a group command misses the @-mention**: messages like `签到` or `/绑定 …` sent in a QQ group without @-mentioning the bot used to be silently dropped (AstrBot only dispatches @-ed messages to command handlers). The bot now replies with a hint and does not relay that message into the game
- KOOK 频道不受影响（频道里本来就不需要 @）

## [1.6.1] - 2026-09-11

### 修复 / Fixed
- **同一游戏账号每天只能领一次**：签到唯一性原先只按 `(用户身份, 游戏, 日期)`——同一个人 QQ 和 KOOK 各绑一次同一游戏账号，就能**一天领两次（+100）**。现在 `qq_checkin` 增加 `player_id` 列 + `(game, player_id, day)` 索引，签到前先按**游戏账号**判重，第二次会回复「这个 XX 游戏账号今天已经领过了，同一账号不会重复加点」
  - **One check-in per game account per day**: uniqueness was keyed on `(identity, game, date)`, so binding the same game account on both QQ and KOOK let one account collect **twice a day (+100)**. `qq_checkin` now stores `player_id` with a `(game, player_id, day)` index and the check-in is de-duplicated by **game account**
- 启动时自动补 `player_id` 列与该索引，并按 `qq_bind` 回填历史签到的 `player_id`（幂等）
  - The `player_id` column + index are added automatically on startup, and historical rows are back-filled from `qq_bind` (idempotent)
- 说明：同一个人的 QQ 与 KOOK 身份仍可各自绑定（两个平台都能用），但如果绑的是**同一个游戏账号**，只有第一次签到能加点
  - Note: QQ and KOOK identities can each hold their own binding, but when they point at the **same game account** only the first check-in of the day pays out

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
