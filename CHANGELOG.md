# Changelog / 更新日志

All notable changes are documented here. 语义化版本：语义化版本 2.0 / [Semantic Versioning](https://semver.org/lang/zh-CN/).

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

[1.0.0]: https://github.com/ultrazero594/astrbot_plugin_zeroserver/releases/tag/v1.0.0
