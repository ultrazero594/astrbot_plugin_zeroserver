# QQ 官方机器人「指令面板」登记清单

> 官方文档：[自定义菜单与指令面板](https://bot.qq.com/wiki/develop/api-v2/server-inter/menu-panel/) ·
> [创建指令面板](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_panels.post.html)
>
> 登记**不影响**指令实际收发——只要机器人能收到消息，插件就会响应；登记只是让玩家在「指令面板」里看到并能一键填入。

## 一、去哪登记（新版开放平台：通过 API）

新版 q.qq.com 里，「菜单与指令」不再提供表单，需要在 **机器人 → 高级设置/开发设置 → 菜单与指令 → 通过 API** 调用接口配置：

| 功能 | 接口 | 说明 |
| --- | --- | --- |
| **指令面板**（推荐） | `POST /v2/panels` | 场景 `c2c`（单聊）/ `group`（群聊）/ `channel` / `dm`；`group`、`c2c` 支持 `target_type=all`（全场景生效）或 `specific` + `group_openids`/`user_openids`（最多 20 个） |
| 自定义菜单（单聊底部按钮） | `PUT /v2/menu` | 单聊窗口底部菜单 |

限制：每个机器人**最多 20 个面板**；每个面板**最多 20 个元素**；元素 `name` ≤ 14 字符（约 7 个汉字）、`desc` ≤ 30 字符（约 15 个汉字）。

### 调用步骤

1. 取 `appid` / `secret`（开放平台 → 开发设置；AstrBot 的 `cmd_config.json` 里也有）；
2. 换取 access_token：
   ```bash
   POST https://bots.qq.com/app/getAppAccessToken
   {"app_id":"你的appid","client_secret":"你的secret"}
   # 返回 access_token（约 2 小时有效）
   ```
3. 带鉴权调用面板接口：
   ```bash
   POST https://api.sgroup.qq.com/v2/panels
   Authorization: QQBot <access_token>
   Content-Type: application/json
   ```
4. 返回 `panel_id`；之后可用 `PUT /v2/panels/{panel_id}` 修改、`DELETE /v2/panels/{panel_id}` 删除。

## 二、可直接使用的请求体（ZeroARK）

### 1) 群聊全局面板

```json
{
  "scope": "group",
  "target_type": "all",
  "panel": {
    "remark": "ZeroARK 群聊指令面板",
    "items": [
      { "type": "command", "name": "帮助", "desc": "查看全部指令" },
      { "type": "command", "name": "进化", "desc": "查进化服，可带地图名" },
      { "type": "command", "name": "飞升", "desc": "查飞升服，可带地图名" },
      { "type": "command", "name": "在线玩家", "desc": "在线玩家与部落名" },
      { "type": "command", "name": "查服", "desc": "按IP或地图名查服" },
      { "type": "command", "name": "倍率", "desc": "当前动态倍率" },
      { "type": "command", "name": "直连", "desc": "所有地图直连地址" },
      { "type": "command", "name": "更新地址", "desc": "刷新地址缓存" },
      { "type": "command", "name": "签到", "desc": "每日签到领点数" },
      { "type": "command", "name": "绑定", "desc": "绑定游戏账号/开绑" },
      { "type": "command", "name": "查绑定", "desc": "查看我的绑定" },
      { "type": "command", "name": "解绑", "desc": "解除某个游戏绑定" },
      { "type": "command", "name": "我是谁", "desc": "查看平台ID/群标识" }
    ]
  }
}
```

### 2) 单聊全局面板（含管理员项，`only_admin` 供群/频道管理员点击）

```json
{
  "scope": "c2c",
  "target_type": "all",
  "panel": {
    "remark": "ZeroARK 单聊指令面板",
    "items": [
      { "type": "command", "name": "帮助", "desc": "查看全部指令" },
      { "type": "command", "name": "签到", "desc": "每日签到领点数" },
      { "type": "command", "name": "查绑定", "desc": "查看我的绑定" },
      { "type": "command", "name": "在线玩家", "desc": "在线玩家与部落名" },
      { "type": "command", "name": "测试推送", "desc": "测试群主动消息" }
    ]
  }
}
```

### 3) 只对指定群生效（可选）

```json
{
  "scope": "group",
  "target_type": "specific",
  "group_openids": ["你的群group_openid"],
  "panel": { "items": [ { "type": "command", "name": "签到", "desc": "每日签到" } ] }
}
```

> `group_openid` 可用插件命令 `/我是谁` 在群里获取（形如 `10F2****…` 的 32 位串，请以实测为准）。

## 三、指令一览（面板用简称，实际指令见下）

| 指令名 | 面板说明建议 | 实际用法 |
| --- | --- | --- |
| 帮助 | 查看全部指令 | `帮助` / `/帮助` / `/help` |
| 进化 | 查进化服 | `进化 [地图名]` / `/ase` |
| 飞升 | 查飞升服 | `飞升 [地图名]` / `/asa` |
| 查服 | 按IP或地图名查服 | `查服 <IP:端口 或 地图名> [ASE\|ASA]` / `/ark` |
| 倍率 | 当前动态倍率 | `倍率` / `/rate` |
| 直连 | 所有地图直连地址 | `直连` / `/direct` |
| 更新地址 | 刷新地址缓存 | `更新地址` / `/update_address` |
| 在线玩家 | 在线玩家与部落名 | `在线玩家 [进化\|飞升] [地图名]` / `/players` |
| 绑定 | 绑定游戏账号/开绑 | `绑定 进化 <SteamID64>`、`绑定 飞升 <EOS>`、`绑定 飞升 开绑` |
| 解绑 | 解除某个游戏绑定 | `解绑 进化` / `解绑 飞升` |
| 查绑定 | 查看我的绑定 | `查绑定` / `/mybind` |
| 签到 | 每日签到领点数 | `签到` / `/signin` |
| 我是谁 | 查看平台ID/群标识 | `我是谁` / `/whoami` |
| rcon | 执行 RCON 命令（管理员） | `/rcon ASA listplayers` |
| 加点 | 给玩家加 ArkShop 点数（管理员） | `/加点 飞升 <EOS> 50` |
| 代加点 | 群内给已绑定群友加点（管理员） | `代加点 进化 50 @群友` |
| 测试推送 | 测试群主动消息（管理员） | `/测试推送` |

## 四、不用登记到平台的指令

| 指令 | 原因 |
| --- | --- |
| `qqbind <QQ号>`、`zsbind <验证码>` | **游戏内公屏指令**，由机器人读取游戏聊天库处理，不属于 QQ 侧指令 |
| `/points`、`/shop`、`/buy` 等 | 游戏内 ArkShop 插件的指令，本机器人不处理 |

## 五、小贴士

1. 面板元素 `name` 会**填入聊天输入框**，所以用不带 `/` 的短名最好（如 `签到`）；
2. 建议至少建两个面板：`scope=group, target_type=all` 给群聊、`scope=c2c` 给单聊；
3. 群内使用建议统一 **@机器人 + 指令**；群设置需开启“获取群内全部消息”与“机器人主动在群聊内发言”；
4. 本机器人下绑定主键是 openid（私聊 `user_openid` / 群 `member_openid`，ZeroARK 实测两者一致）。

## 六、自定义菜单（单聊底部按钮，已配置）

接口：`PUT /v2/menu`（仅 C2C 全局生效；最多 10 个按钮；按钮类型 `switch` / `send_message` / `link` / `menu`(子菜单最多 5 个)）。

ZeroARK 当前已配置（version 41）：

```json
{
  "menu": {
    "items": [
      { "type": "send_message", "name": "帮助", "send_message": "帮助" },
      { "type": "send_message", "name": "签到", "send_message": "签到" },
      { "type": "send_message", "name": "在线玩家", "send_message": "在线玩家" },
      { "type": "menu", "name": "查询", "sub_menu_items": [
        { "type": "send_message", "name": "进化", "send_message": "进化" },
        { "type": "send_message", "name": "飞升", "send_message": "飞升" },
        { "type": "send_message", "name": "倍率", "send_message": "倍率" },
        { "type": "send_message", "name": "直连", "send_message": "直连" },
        { "type": "send_message", "name": "查服", "send_message": "查服" }
      ] },
      { "type": "send_message", "name": "查绑定", "send_message": "查绑定" },
      { "type": "link", "name": "官网", "link": "https://example.com/" }
    ]
  }
}
```

> 点击 `send_message` 类按钮会把文本**填入输入框**（仍需发送）；`menu` 类型为折叠子菜单；`link` 跳转浏览器。
> 查询当前菜单：`GET /v2/menu`；覆盖修改：再次 `PUT /v2/menu`（会整体替换）。

