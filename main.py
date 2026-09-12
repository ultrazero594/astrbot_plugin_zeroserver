import asyncio
import hashlib
import json
import re
import copy
import os
import random
import time
import warnings
from datetime import datetime, timedelta

import a2s
import httpx
from bs4 import BeautifulSoup
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.config import logger

from rcon.source import Client as RconClient

# ======================== 跨服聊天数据库支持 ========================
import aiomysql

# ======================== 数据源 URL ========================
_SERVERS_URL = ""  # 由 config.json 的 servers_html_url 提供（【抓取】直连地址列表页）
_RCON_URL = ""  # 由 config.json 的 rcon_html_url 提供（【抓取】RCON 地址页）
DYNAMIC_INI_URL = ""  # 由 config.json 的 dynamic_ini_url 提供（【抓取】倍率文件）

# ======================== ARK Status API 配置 ========================
DEFAULT_ARKSTATUS_API_KEY = ""  # 可选：ARK Status API Key，配置于 config.json 的 arkstatus_api_key
ARKSTATUS_API_BASE = "https://arkstatus.com/api/v1/servers"

# ======================== 各版本官网（错误/成功消息共用） ========================
FOOTER_ASE = "\n\n"
FOOTER_ASA = "\n\n"

# ======================== 旧绑定（OneBot 时代 QQ 号主键）引导文案 ========================
BIND_GUIDE = (
    "\n\n📝 绑定方式（选一种即可）：\n"
    "① 直接绑定（推荐，随时可用、不需要私聊）：\n"
    "   /绑定 飞升 <EOS 32位ID>　或　/绑定 进化 <SteamID64 17位数字>\n"
    "   · 飞升的 EOS ID 在游戏里打开商店（ArkShop）就能看到\n"
    "② 验证码绑定（不知道上面那串 ID、或要换绑时用这个）：\n"
    "   /绑定 进化 开绑 → 拿 6 位验证码 → 进游戏公屏发：zsbind <验证码>\n"
    "   （能私聊就私发给你；QQ 个人认证收不到私聊时会直接回在这里）\n"
    "③ 换绑：先发 /解绑 进化（或 /解绑 飞升），再用上面方式重新绑定\n"
    "🇶 老玩家注意：以前用 QQ 号绑定的记录已失效，重新绑定会自动接回你原来的账号。")
LEGACY_BIND_HINT = BIND_GUIDE   # 兼容旧引用

# ======================== 地图名称中英文映射（进化ASE/飞升ASA 分开；英文只保留地址表中出现的） ========================
MAP_NAME_CN = {
    "ASE": {
        "TheIsland": "孤岛",
        "ScorchedEarth_P": "焦土",
        "Aberration_P": "畸变",
        "Extinction": "灭绝",
        "Genesis": "创一",
        "Gen2": "创二",
        "TheCenter": "中心",
        "Ragnarok": "仙境",
        "Valguero_P": "瓦尔",
        "LostIsland": "迷失",
        "CrystalIsles": "水晶",
        "Fjordur": "维京",
        "Aquatic": "海洋",
    },
    "ASA": {
        "TheIsland_WP": "孤岛",
        "ScorchedEarth_WP": "焦土",
        "TheCenter_WP": "中心岛",
        "Svartalfheim_WP": "矮人国度",
        "Aberration_WP": "畸变",
        "BobsMissions_WP": "Club",
        "Extinction_WP": "灭绝",
        "Astraeos_WP": "繁星",
        "Ragnarok_WP": "仙境",
        "Valguero_WP": "瓦尔",
        "LostColony_WP": "失落之地",
        "Genesis_WP": "创一",
    },
}

def get_map_cn(eng_map: str, version: str = "") -> str:
    """英文地图名转中文：优先按版本（ASE/ASA）映射，未命中时跨版本兜底"""
    if not eng_map or eng_map == "unknown":
        return "未知"
    table = MAP_NAME_CN.get(version, {})
    if eng_map in table:
        return table[eng_map]
    for t in MAP_NAME_CN.values():
        if eng_map in t:
            return t[eng_map]
    return eng_map

# ======================== 标准/官方英文地图名（去掉开服方自定义后缀 _P/_WP；Gen2→Genesis2；已对照 ARK 官方 wiki 的 Server map name 校验） ========================
MAP_NAME_STD = {
    "ASE": {
        "TheIsland": "TheIsland",
        "ScorchedEarth_P": "ScorchedEarth",
        "Aberration_P": "Aberration",
        "Extinction": "Extinction",
        "Genesis": "Genesis",
        "Gen2": "Genesis2",
        "TheCenter": "TheCenter",
        "Ragnarok": "Ragnarok",
        "Valguero_P": "Valguero",
        "LostIsland": "LostIsland",
        "CrystalIsles": "CrystalIsles",
        "Fjordur": "Fjordur",
        "Aquatic": "Aquatic",
    },
    "ASA": {
        "TheIsland_WP": "TheIsland",
        "ScorchedEarth_WP": "ScorchedEarth",
        "TheCenter_WP": "TheCenter",
        "Svartalfheim_WP": "Svartalfheim",
        "Aberration_WP": "Aberration",
        "BobsMissions_WP": "BobsMissions",
        "Extinction_WP": "Extinction",
        "Astraeos_WP": "Astraeos",
        "Ragnarok_WP": "Ragnarok",
        "Valguero_WP": "Valguero",
        "LostColony_WP": "LostColony",
        "Genesis_WP": "Genesis",
    },
}

def get_map_std(name: str, version: str = "") -> str:
    """地图名（中文/英文/带纯净前缀）转标准/官方英文。
    支持：中文(仙境)→Ragnarok、英文(Ragnarok_WP)→Ragnarok、纯净(纯净孤岛)→TheIsland
    纯净与普通为同一张地图（靠端口区分），故先剥离纯净前缀。
    """
    if not name or name == "unknown":
        return "Unknown"
    clean = re.sub(r'^纯净\s*', '', name).strip()
    table = MAP_NAME_STD.get(version, {})
    # 1) 直接命中：英文键
    if clean in table:
        return table[clean]
    # 2) 中文输入：在中文表里反查英文键
    cn_table = MAP_NAME_CN.get(version, {})
    for eng_key, cn_val in cn_table.items():
        if cn_val == clean:
            return table.get(eng_key, eng_key)
    # 3) 跨版本兜底
    for ver, t in MAP_NAME_STD.items():
        if clean in t:
            return t[clean]
    for ver, t in MAP_NAME_CN.items():
        for eng_key, cn_val in t.items():
            if cn_val == clean:
                return MAP_NAME_STD.get(ver, {}).get(eng_key, eng_key)
    # 4) 去掉 _P/_WP 后缀
    base = re.sub(r'(_P|_WP)$', '', clean)
    return base or clean

def get_map_display(name: str, version: str, lang: str = "zh") -> str:
    """按语言返回地图名：en→标准/官方英文；zh→中文"""
    if lang == "en":
        return get_map_std(name, version)
    return get_map_cn(name, version)

def clean_map_name(raw: str) -> str:
    return re.sub(r'\s*\([^)]*\)\s*', '', raw).strip()

def _fuzzy_key(mapping: dict, query: str):
    """在 map/rcon 地址表中模糊查找地图名：
    ① 完全匹配 → ② 忽略空白后匹配 → ③ 互相包含（仅唯一命中时）。
    找不到返回 None。
    """
    if not query or not mapping:
        return None
    if query in mapping:
        return query
    normalized = query.replace(' ', '').replace('　', '')
    for key in mapping:
        if key.replace(' ', '').replace('　', '') == normalized:
            return key
    matches = [k for k in mapping if query in k or k in query]
    return matches[0] if len(matches) == 1 else None

def _parse_dynamic_ini(content: str) -> dict:
    """解析 Dynamic.ini：跳过空行 / // 注释行，取 k=v"""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('//') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        result[k.strip()] = v.strip()
    return result

# ======================== 游戏内绑定聊天指令（玩家在游戏公屏输入） ========================
RELAY_SKIP_MARKERS = ("[飞升]", "[进化]", "[QQ群]", "[KOOK]", "[跨服]", "🔀")
# qqbind 既接受老式 QQ 号（5-12 位数字），也接受 QQ 官方机器人的 openid（32 位 hex 之类）
QQBIND_RE = re.compile(r'^\s*qqbind\s+([A-Za-z0-9_-]{5,64})\s*$', re.IGNORECASE)
ZSBIND_RE = re.compile(r'^\s*zsbind\s+([a-z0-9]{4,12})\s*$', re.IGNORECASE)
# 识别用（宽松版）：玩家可能漏打空格（如 qqbind22C5F7CC…），也要算绑定指令、不能转发到群里
BIND_CHAT_RE = re.compile(r'^\s*(?:qqbind|zsbind)\s*[A-Za-z0-9_-]{4,64}\s*$', re.IGNORECASE)

def _is_direct_game_chat(text: str) -> bool:
    """是否机器人转发回来（含转发标记）的消息：是则不是玩家直接在游戏里输入的"""
    if not text:
        return False
    return not any(mk in text for mk in RELAY_SKIP_MARKERS)

def _is_bind_chat(text: str) -> bool:
    """判断是否为游戏内绑定指令消息（qqbind/zsbind），用于转发时静默吞掉、仅由绑定监听消费"""
    if not text or not _is_direct_game_chat(text):
        return False
    return bool(BIND_CHAT_RE.search(text))

# 游戏内指令提示（帮助/签到成功/更新地址等处复用）
GAME_CMD_TIPS = (
    "【游戏内绑定（在游戏公屏输入）】\n"
    "· zsbind <验证码> —— 先在 QQ/KOOK 里发 /绑定 <进化|飞升> 开绑 拿 6 位验证码，"
    "再到游戏公屏发 zsbind <验证码>，即可完成绑定/换绑\n"
    "绑定后可用 /signin 每日签到领点数"
)

RATE_NAMES = {
    'XPMultiplier': '经验倍率', 'HarvestAmountMultiplier': '采集倍率',
    'TamingSpeedMultiplier': '驯服速度', 'BabyMatureSpeedMultiplier': '幼崽成长速度',
    'EggHatchSpeedMultiplier': '孵化速度', 'BabyCuddleIntervalMultiplier': '留痕间隔',
    'BabyImprintAmountMultiplier': '留痕倍率', 'MatingIntervalMultiplier': '交配间隔',
    'MatingSpeedMultiplier': '交配速度', 'BabyFoodConsumptionSpeedMultiplier': '幼崽食物消耗',
    'CropGrowthSpeedMultiplier': '作物成长速度', 'HexagonRewardMultiplier': '六角币倍率',
}

DEFAULT_CONFIG = {
    "notify_group": 0,                        # 通知群号（int），改成你的群号
    "whitelist_groups": [],                   # 允许使用指令的群白名单；留空=不限制
    "owner_qq": "",                           # 服主 QQ（/rcon、/加点、/代加点 等管理命令校验）
    "owner_ids": [],                          # 额外主人 ID（跨平台：QQ openid / KOOK 用户ID），与 owner_qq 合并生效
    "admin_channels": [],                     # 这些群/频道里，主人也能看到完整帮助（含管理指令段）
    "check_interval_minutes": 10,             # 地址/倍率定时刷新间隔（分钟）
    "official_site": "https://example.com/",  # 官网，显示在部分消息底部
    "rcon_timeout": 5.0,
    "arkstatus_api_key": "",                  # 可选：ARK Status API Key
    "chat_forward_enabled": False,            # 跨服聊天转发开关
    "chat_check_interval": 1.0,
    "list_rcon_fallback": True,               # 列表查询失败时用 RCON 回退判定在线/人数
    "db_sources": [],                         # 游戏聊天库源（见 README 数据库一节）
    "qq_to_game_enabled": True,               # QQ 群消息转发进游戏（RCON serverchat）
    "qq_forward_prefix": "[QQ群]",
    "kook_forward_prefix": "[KOOK]",       # KOOK 频道消息转发进游戏时的前缀
    # QQ/KOOK → 游戏公屏 的发送通道：rcon（默认，任何环境可用）| cca（写 CrossChatAscended 的表，
    # 借用它的跨服通道与格式；只有装了 CCA 的服会显示）
    "game_send_via": "rcon",
    "cca_map_label": "QQ",                 # 写 CCA 时 Map 字段用的标签（**必须纯 ASCII**，中文会被 CCA 解成乱码）
    "cca_map_label_kook": "KOOK",
    "cca_sender_prefix": "【跨服】",         # 加在发送者前面（Sender 字段支持中文，用来显示"跨服"）
    # 彩色通道：走 AsaApi 插件 ZeroARKMsg 的 RCON 命令（game_send_via = rcon_color / plugin）
    "plugin_msg_cmd": "ZeroARKMsgSend",     # 插件里的彩色发送命令名
    "plugin_msg_color": "0.2,0.85,1",       # 默认颜色 r,g,b（0~1）
    "plugin_msg_color_qq_official": "0.35,0.75,1",   # QQ 消息用蓝色
    "plugin_msg_color_kook": "0.75,0.5,1",  # KOOK 消息用紫色
    # 已经装了彩色插件 ZeroARKMsg 的服务器（按名字子串匹配，不区分大小写）；
    # 名单内的走 ZeroARKMsgSend 上色，名单外仍用 serverchat 纯文本（保证不会因为没装插件而漏消息）
    "plugin_msg_servers": [],
    # 富文本（CCA 那种分段多色）：走 ZeroARKMsgChat（聊天栏通道，实测支持 <RichColor>）
    # 占位符：{c}=平台颜色 {tag}=前缀 {sender}=发送者 {message}=内容；留空则退回"整条单色"
    "plugin_chat_cmd": "ZeroARKMsgChat",
    "plugin_chat_format": "<RichColor Color=\"{c}\">{tag} {sender}</> <RichColor Color=\"1,1,1,1\">{message}</>",
    # 公共消息审计（用户红线：发往公共区域的内容必须先过审）
    # off=关闭 / log=只记日志（默认，dry-run 观察误报）/ redact=命中即自动打码
    "public_msg_audit": "log",
    "cca_fallback_rcon": True,        # CCA 通道失败时回退 RCON，避免消息丢失
    # 主动消息目标（跨服聊天转发 / 通知 / 绑定结果 / 代加点公告）：[{platform,id,label}]
    # platform: qq_official | kook | aiocqhttp；留空则回退到 notify_group（QQ群）
    "broadcast_targets": [],
    # 群间互通：把某个目标群/频道的消息同步到其它目标（QQ群 ↔ KOOK 频道），带 🔀 标记防循环
    "bridge_enabled": False,
    # 跨平台互推：QQ 侧展示 KOOK 邀请链接、KOOK 侧展示 QQ 群号（留空则该侧不显示）
    "invite_kook": "",
    "invite_qq": "",
    # 是否在"所有回复"底部统一附带互推入口行（关闭则只在 /帮助 显示）
    "invite_on_reply": True,
    # 新人首次互动时附一句欢迎引导（插件收不到"入群事件"，用首次交互替代）
    "welcome_new_user": True,
    "welcome_text": "👋 欢迎新朋友～发 /帮助 看我都会啥；/在线玩家 查在线，/签到 领点数",
    # 服务器上/下线提醒（按 RCON 探测结果，状态变化时推送到广播目标）
    "status_notify_enabled": True,
    "status_notify_fail_threshold": 2,   # 连续失败几次才算离线（防抖）
    "status_notify_limit": 8,            # 单条播报最多列几条变化
    # QQ 开放平台申请到「消息按钮模板」后填模板 id（填了就用模板发送按钮，否则用内联按钮实验）
    "qq_keyboard_template_id": "",
    # 私聊发不出验证码时，是否允许把验证码直接发在群/频道里（QQ 个人认证收不到私聊，只能这样）
    "bind_code_public_fallback": True,
    # 玩家从哪儿查自己的游戏 ID（写进绑定帮助文案；游戏内 ArkShop 商店界面能看到飞升的 EOS）
    "id_source_hint": "飞升的 EOS 32 位 ID：在游戏里打开商店（ArkShop）就能看到；进化用 SteamID64（17 位数字，7656119 开头）",
    # KOOK 卡片按钮补丁（AstrBot 默认丢弃 message_btn_click；打开后点卡片按钮=执行对应指令）
    "kook_button_patch": True,
    # 没装 ArkShop 插件的服务器（按名字子串匹配，不区分大小写）：加点、倍率刷新等 ArkShop 命令会跳过它们
    "arkshop_exclude_servers": ["Club", "海洋"],
    # 隐私：/在线玩家 名单里的游戏ID是否打码（默认打码，改为 false 则显示完整 ID）
    "mask_player_ids": True,
    "rcon_targets": [],                       # 手动 RCON 目标（也可由 rcon_html_url 自动构建）
    "cache_mirror_url": "",                   # 【抓取】缓存更新检测的目录列表页
    "cache_mirror_urls": [],                  # 多个镜像目录（优先于上面的单值；留空则用单值）
    "cache_check_interval_minutes": 10,
    "update_notify_qq": 0,                    # 缓存更新私聊通知对象（QQ号）
    "servers_html_url": "",                   # 【抓取】直连地址列表页（Servers.html）
    "rcon_html_url": "",                      # 【抓取】RCON 地址页（RCON.html）
    "dynamic_ini_url": "",                    # 【抓取】倍率文件（Dynamic.ini）
    "usage_url_ase": "",                      # 【抓取】进化版“如何加入”说明页
    "usage_url_asa": "",                      # 【抓取】飞升版“如何加入”说明页
    "bind_db": {"host": "", "port": 3306, "user": "", "password": "", "database": "qq"},
    "signin": {
        "timezone_offset_hours": 8,
        "ase_points": 50,
        "asa_points": 50,
        "ase_cmd": "AddPoints {id} {points}",
        "asa_cmd": "AddPoints {id} {points}",
        "verify_with_getpoints": True
    },
    "game_bind": {
        "enable": True,
        # 游戏内 qqbind <身份ID> 通道：默认关闭（在公屏贴身份 ID 有冒绑风险，
        # 现在有"直接发 EOS/SteamID"和"6 位验证码 zsbind"两条更安全的绑定路；置 true 可重新启用）
        "qq_cmd": False,
        "code_cmd": True,
        "poll_interval": 1.5,
        "code_ttl_seconds": 180,
        "dm_fallback": "@"
    },
    "llm_trigger_keywords": ["报告", "总结", "解释", "帮忙", "ZeroARK", "指令", "绑定", "签到", "怎么", "使用", "倍率", "查服", "直连"],
    # 插件自带 LLM（默认关闭；开启需填 llm_api_key，否则不会调用）
    "llm_enabled": False,
    "llm_model": "glm-4-flash",
    "llm_api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "llm_api_key": "",
    "llm_system_prompt": "",
    "llm_enabled": False,                     # 智谱 GLM / OpenAI 兼容接口，可自行替换
    "llm_api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "llm_model": "GLM-4.7-Flash",
    "llm_api_key": "",
    "llm_system_prompt": ""
}
# 默认「地图名 -> 直连地址」表。正式使用请通过 config.json 的 servers_html_url
# 指向你服务器的直连地址列表页自动抓取填充；也可在本处预填你的服务器地址。
DEFAULT_MAP = {"ASE": {}, "ASA": {}}

class CrossChatForwarder:
    def __init__(self, plugin):
        self.plugin = plugin
        self.sources = plugin.config.get('db_sources', [])
        self.last_ids = {}
        self.running = False
        self._conns = {}          # src_id -> 复用的 aiomysql 连接
        self._fail_until = {}     # src_id -> 失败冷却截止时间（秒），避免失败时每秒重连刷日志
        for src in self.sources:
            self.last_ids[src.get('id', 'default')] = 0
        if not self.sources:
            logger.warning("⚠️ 未配置数据库源，跨服聊天转发禁用")
        else:
            logger.info(f"📂 跨服聊天数据源: {[s.get('id') for s in self.sources]}")

    # 转发标记：含这些标记的消息是"已被转发过"的，需跳过，防止 飞升↔进化↔QQ 无限转发循环
    SKIP_MARKERS = RELAY_SKIP_MARKERS

    def _is_relayed(self, text: str) -> bool:
        if not text:
            return False
        return any(mk in text for mk in self.SKIP_MARKERS)

    async def _get_conn(self, src):
        """获取/复用某源的 MySQL 连接；断线时自动重建"""
        src_id = src.get('id', 'default')
        conn = self._conns.get(src_id)
        if conn is not None:
            try:
                if conn.open:
                    return conn
            except Exception:
                pass
            try:
                await conn.ensure_closed()
            except Exception:
                pass
        conn = await aiomysql.connect(
            host=src.get('host'), port=src.get('port', 3306),
            user=src.get('user'), password=src.get('password'),
            db=src.get('database'), autocommit=True, charset='utf8mb4'
        )
        self._conns[src_id] = conn
        return conn

    async def start(self):
        if not self.plugin.config.get('chat_forward_enabled', False):
            logger.info("⏭️ 跨服聊天转发未启用")
            return
        if not self.sources:
            logger.warning("⚠️ 没有可用的数据库源")
            return
        # 等待 aiocqhttp 适配器连接（通过 get_login_info API 测试）
        await self.plugin._wait_qq_adapter("跨服聊天转发启动")

        # 初始化各源的最后ID为当前最大值，避免转发历史消息
        for src in self.sources:
            src_id = src.get('id', 'default')
            if src.get('type') != 'mysql':
                continue
            try:
                conn = await self._get_conn(src)
                cursor = await conn.cursor()
                await cursor.execute(f"SELECT MAX(Id) FROM {src.get('table', 'cross_chat')}")
                row = await cursor.fetchone()
                max_id = row[0] if row and row[0] is not None else 0
                self.last_ids[src_id] = max_id
                logger.info(f"📌 源 {src_id} 初始最大ID = {max_id}，只转发之后的新消息")
                await cursor.close()
            except Exception as e:
                self.last_ids[src_id] = 0
                logger.warning(f"⚠️ 获取源 {src_id} 最大ID失败: {e}，将使用0，可能转发历史消息")

        self.running = True
        interval = self.plugin.config.get('chat_check_interval', 1.0)
        logger.info(f"✅ 跨服聊天转发已启动，监听 {len(self.sources)} 个源，间隔 {interval}s")
        while self.running:
            try:
                await self._check_and_forward()
            except Exception as e:
                logger.error(f"❌ 跨服聊天转发异常: {e}")
            await asyncio.sleep(interval)

    async def _check_and_forward(self):
        for src in self.sources:
            src_id = src.get('id', 'default')
            last_id = self.last_ids.get(src_id, 0)
            logger.debug(f"🔍 检查源 {src_id}，last_id={last_id}")
            try:
                if src.get('type') == 'mysql':
                    messages = await self._read_mysql(src, last_id)
                else:
                    continue
                if messages:
                    self.last_ids[src_id] = max(m.get('Id', 0) for m in messages)
                    # 过滤掉"已转发"消息（含转发标记），防止跨服/跨QQ无限循环；绑定指令（qqbind/zsbind）也只由绑定监听消费，不再转发
                    # 另外跳过我们自己写进 CCA 表的行（Map = cca 标签），否则 QQ→游戏 的消息会被读回来又发回 QQ（回声）
                    _cca_labels = self.plugin._cca_labels()
                    fresh = [m for m in messages
                             if not self._is_relayed(str(m.get('Message', '')))
                             and not _is_bind_chat(str(m.get('Message', '')))
                             and str(m.get('Map', '')) not in _cca_labels]
                    skipped = len(messages) - len(fresh)
                    if skipped:
                        logger.info(f"🔁 源 {src_id} 跳过 {skipped} 条已转发消息（防循环）")
                    if fresh:
                        logger.info(f"📨 从 {src_id} 读取到 {len(fresh)} 条新消息")
                        await self._forward_messages(fresh, src)
                else:
                    logger.debug(f"🔍 源 {src_id} 无新消息")
            except Exception as e:
                logger.error(f"❌ 源 {src_id} 读取失败: {e}")

    async def _read_mysql(self, src, last_id) -> list:
        """读取某源新增消息。失败后进入 5 秒冷却窗口（期间跳过该源），避免每秒重连刷错误日志。"""
        src_id = src.get('id', 'default')
        if time.time() < self._fail_until.get(src_id, 0):
            return []
        try:
            conn = await self._get_conn(src)
            cursor = await conn.cursor(aiomysql.DictCursor)
            table = src.get('table', 'cross_chat')
            await cursor.execute(f"SELECT Id, Map, Sender, Message, timestamp FROM {table} WHERE Id > %s ORDER BY Id ASC", (last_id,))
            rows = await cursor.fetchall()
            logger.debug(f"🔍 {src_id} 查询到 {len(rows)} 行 (last_id={last_id})")
            await cursor.close()
            return rows
        except Exception as e:
            self._fail_until[src_id] = time.time() + 5
            logger.error(f"❌ MySQL 读取失败 ({src_id}): {e}")
            return []

    async def _forward_messages(self, messages, src):
        src_id = src.get('id', '未知')
        prefix = "[飞升]" if src_id == 'asa_chat' else "[进化]" if src_id == 'ase_chat' else "[跨服]"
        # 目标游戏版本：asa_chat(飞升)的消息 -> 转发到 ASE(进化)；ase_chat(进化)的消息 -> 转发到 ASA(飞升)
        target_ver = "ASE" if src_id == 'asa_chat' else "ASA" if src_id == 'ase_chat' else None
        for msg in messages:
            server = msg.get('Map', '未知地图')
            player = msg.get('Sender', '未知玩家') or '匿名'
            content = msg.get('Message', '')
            if not content:
                continue
            chat_text = f"{prefix}【{server}】{player}: {content}"
            # 1) 发到所有广播目标（QQ 群 + KOOK 频道等，双发）
            logger.info(f"📤 转发到广播目标: {chat_text[:50]}...")
            sent_n = await self.plugin._broadcast(chat_text)
            if not sent_n:
                logger.error("❌ 跨服聊天转发失败：没有任何目标发送成功")
            # 2) 转发到另一个游戏（RCON serverchat），实现 飞升↔进化 游戏内互转
            if target_ver:
                await self._relay_to_game(target_ver, chat_text)

    async def _relay_to_game(self, version: str, text: str):
        """把消息通过 RCON serverchat 并发转发到指定版本（ASE/ASA）的所有服务器"""
        if not self.plugin.rcon_password:
            logger.debug(f"RCON 密码未获取，跳过 {version} 游戏转发")
            return
        targets = [t for t in (self.plugin.rcon_targets or [])
                   if str(t.get('name', '')).startswith(version + "-")]
        if not targets:
            logger.debug(f"没有 {version} 的 RCON 目标，跳过转发")
            return
        await self.plugin._send_rcon_concurrent(targets, f"serverchat {self.plugin._game_safe(text)}")

    def stop(self):
        self.running = False

@register("astrbot_plugin_zeroserver", "ZeroARK", "方舟服务器查询机器人", "1.25.0", "https://github.com/ultrazero594/astrbot_plugin_zeroserver")
class ZeroARKPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = self._load_config()
        self.map_cache = copy.deepcopy(DEFAULT_MAP)
        self.rcon_cache = {"ASE": {}, "ASA": {}}
        self.usage_cache = {"ASE": "", "ASA": ""}
        self.last_rate_hash = None
        self.last_rate_content = {}
        self.rcon_password = ""
        self.footer = f"\n\n🌐 官网：{self.config['official_site']}"
        self._bot = None
        self.rcon_targets = []
        self._last_llm_reply_time = 0
        self._signin_lock = asyncio.Lock()

        self._background_tasks = []
        self._last_umo = None
        self._notify_umo = None

        self._background_tasks.append(asyncio.create_task(self._fetch_all_data()))
        self._background_tasks.append(asyncio.create_task(self._fetch_usage()))
        self._schedule_tasks()

        self.chat_forwarder = CrossChatForwarder(self)
        self._background_tasks.append(asyncio.create_task(self.chat_forwarder.start()))
        logger.info("✅ 跨服转发任务已创建并保存引用")

        # KOOK 卡片按钮补丁（AstrBot 默认把 message_btn_click 当未实现的系统通知忽略掉）
        try:
            self._install_kook_button_patch()
        except Exception as e:
            logger.debug(f"KOOK 按钮补丁装载失败: {e}")

        self.seen_cache_files = set()
        self._background_tasks.append(asyncio.create_task(self._check_cache_updates()))
        logger.info("✅ 缓存更新检测任务已创建")
        # 服务器状态基线（启动后尽快探测一次，避免首轮 10 分钟空窗）
        self._background_tasks.append(asyncio.create_task(self._initial_status_baseline()))

        # QQ 绑定 / 签到：初始化数据表（幂等；失败只记日志，不影响主流程）
        # _qq_tables_ready：首次检查通过后置 True，后续命令直接返回，
        # 不再每条命令都跑一遍 CREATE TABLE IF NOT EXISTS + information_schema 查询
        self._qq_tables_ready = False
        self._background_tasks.append(asyncio.create_task(self._safe_ensure_qq_tables()))

        # 游戏内绑定监听（玩家在游戏公屏输入 qqbind/zsbind）
        self._pending_codes = {}
        self._pending_links = {}
        self._seen_users = None
        self._server_status = {}
        self._status_baseline_done = False
        self._bind_chat_conns = {}
        self._background_tasks.append(asyncio.create_task(self._bind_watcher()))

        if self.config.get('qq_to_game_enabled', True):
            logger.info("✅ QQ->游戏 消息转发已启用（通过 filter.event_message_type 订阅）")

        logger.info("✅ ZeroARKPlugin 初始化完成")

    def __del__(self):
        if hasattr(self, 'chat_forwarder'):
            self.chat_forwarder.stop()

    def _load_config(self):
        try:
            # 优先插件目录下的 config.json，其次工作目录（兼容不同部署方式）
            here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
            path = here if os.path.exists(here) else "config.json"
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # 与默认配置合并，避免旧版 config.json 缺字段导致 KeyError
            merged = copy.deepcopy(DEFAULT_CONFIG)
            merged.update(loaded or {})
            return merged
        except FileNotFoundError:
            logger.warning("⚠️ 未找到 config.json，使用默认配置")
            return copy.deepcopy(DEFAULT_CONFIG)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"⚠️ config.json 读取失败: {e}，使用默认配置")
            return copy.deepcopy(DEFAULT_CONFIG)

    async def _fetch_all_data(self):
        await asyncio.gather(
            self._fetch_rcon_data(),
            self._fetch_servers(),
            return_exceptions=True
        )
        self._build_rcon_targets()
        logger.info("✅ 数据获取完成（RCON + 直连服务器列表）")

    async def _fetch_rcon_data(self):
        try:
            url = self.config.get('rcon_html_url') or _RCON_URL
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'lxml')
                pw = soup.find('div', class_='password-notice')
                if pw:
                    span = pw.find('span')
                    if span:
                        self.rcon_password = span.get_text(strip=True)
                        logger.info("✅ RCON密码已获取")
                for ver in ["ASE", "ASA"]:
                    sec = soup.find('h2', string=re.compile(ver))
                    if sec:
                        parent = sec.parent
                        rcon_map = {}
                        for item in parent.find_all('div', class_='item'):
                            text = item.get_text(strip=True)
                            parts = re.split(r'[:：]', text, maxsplit=1)
                            raw = parts[0].strip() if len(parts) > 1 else text.strip()
                            name = clean_map_name(raw)
                            addr_span = item.find('span', class_='addr')
                            if addr_span:
                                rcon_map[name] = [addr_span.get_text(strip=True)]
                        if rcon_map:
                            self.rcon_cache[ver] = rcon_map
                            logger.info(f"✅ {ver} RCON 地址已解析（{len(rcon_map)} 个地图）")
        except Exception as e:
            logger.warning(f"❌ RCON数据获取失败: {e}")

    def _build_rcon_targets(self):
        targets = []
        seen = set()
        # 先加载用户配置的目标
        if self.config.get('rcon_targets'):
            for t in self.config['rcon_targets']:
                targets.append(t)
                key = (t.get('host'), t.get('port'))
                if key not in seen:
                    seen.add(key)
            logger.info(f"✅ 使用用户配置的 RCON 目标: {len(targets)} 个")
        # 再追加来自 RCON.html / rcon_cache 的地址（含 rcon_addrs，如海洋: host:16130）
        rcon_cache = self.rcon_cache
        for ver in ["ASE", "ASA"]:
            rcon_map_ver = rcon_cache.get(ver, {})
            for name, addrs in rcon_map_ver.items():
                for addr in addrs:
                    if not addr or ":" not in addr:
                        continue
                    host, port_str = addr.split(":")
                    try:
                        port = int(port_str)
                    except ValueError:
                        continue
                    key = (host, port)
                    if key in seen:
                        continue
                    seen.add(key)
                    targets.append({"name": f"{ver}-{name}", "host": host, "port": port})
                    logger.info(f"✅ 自动添加 RCON 目标: {ver}-{name} {host}:{port}")
        if targets:
            self.rcon_targets = targets
            logger.info(f"✅ 已构建 {len(self.rcon_targets)} 个 RCON 目标（发送到所有服务器）")
        else:
            logger.warning("⚠️ 未能从 RCON.html 和 rcon_addrs 构建任何 RCON 目标")

    async def _fetch_servers(self):
        try:
            url = self.config.get('servers_html_url') or _SERVERS_URL
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'lxml')
                for ver in ["ASE", "ASA"]:
                    sec = soup.find('h2', string=re.compile(ver))
                    if sec:
                        parent = sec.parent
                        mp = {}
                        for item in parent.find_all('div', class_='item'):
                            text = item.get_text(strip=True)
                            parts = re.split(r'[:：]', text, maxsplit=1)
                            raw = parts[0].strip() if len(parts) > 1 else text.strip()
                            name = clean_map_name(raw)
                            addrs = [s.get_text(strip=True) for s in item.find_all('span', class_='addr')]
                            if addrs:
                                mp[name] = addrs
                        if mp:
                            self.map_cache[ver] = mp
                            logger.info(f"✅ {ver} 直连地址已更新（{len(mp)} 个地图）")
        except Exception as e:
            logger.warning(f"❌ 直连服务器列表获取失败: {e}，使用默认地址")

    async def _fetch_usage(self):
        new_usage = {"ASE": "", "ASA": ""}
        urls = {
            "ASE": (self.config.get('usage_url_ase') or "").strip(),
            "ASA": (self.config.get('usage_url_asa') or "").strip(),
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            for key, url in urls.items():
                if not url:
                    continue
                try:
                    resp = await client.get(url)
                    soup = BeautifulSoup(resp.text, 'lxml')
                    article = soup.find('article')
                    if article:
                        for p in article.find_all('p'):
                            txt = p.get_text(strip=True)
                            if txt and len(txt) > 10:
                                new_usage[key] = txt
                                break
                    if not new_usage[key]:
                        for p in soup.find_all(['p', 'div']):
                            txt = p.get_text(strip=True)
                            if '非官方服务器' in txt or '控制台' in txt:
                                new_usage[key] = txt
                                break
                except Exception as e:
                    logger.error(f"{key} 使用说明抓取失败: {e}")
        self.usage_cache = new_usage
        logger.info("使用说明缓存已更新")

    def _schedule_tasks(self):
        if hasattr(self.context, 'scheduler'):
            interval = self.config['check_interval_minutes'] * 60
            try:
                # replace_existing：插件热重载时不再因同名 job 抛 ConflictingIdError
                self.context.scheduler.add_job(self._check_updates, 'interval', seconds=interval,
                                               id='check_updates', replace_existing=True)
            except Exception as e:
                logger.error(f"定时任务注册失败（缓存更新检查）: {e}")

    async def _check_updates(self):
        await self._fetch_servers()
        await self._fetch_rcon_data()
        self._build_rcon_targets()
        await self._check_rate_update()
        await self._check_server_status()

    async def _check_server_status(self):
        """服务器上/下线监控：并发探测每个 RCON 目标，状态变化时推送到广播目标。
        ① 首轮只建基线不播报；② 连续 fail_threshold 次探测失败才判定离线（防抖）；
        ③ 恢复立即播报；④ 一轮最多报 limit 条，多的折叠成一行。"""
        if not self.config.get('status_notify_enabled', True):
            return
        targets = [t for t in (self.rcon_targets or []) if t.get('host') and t.get('port')]
        if not targets or not self.rcon_password:
            return
        threshold = max(1, int(self.config.get('status_notify_fail_threshold', 2)))
        limit = max(1, int(self.config.get('status_notify_limit', 8)))
        loop = asyncio.get_running_loop()
        try:
            oks = await asyncio.gather(*[
                loop.run_in_executor(None, self._rcon_online_sync, t['host'], t['port'])
                for t in targets], return_exceptions=True)
        except Exception as e:
            logger.debug(f"服务器状态探测异常: {e}")
            return
        events = []
        for t, ok in zip(targets, oks):
            name = self._target_label(t.get('name') or f"{t.get('host')}:{t.get('port')}")
            st = self._server_status.get(name) or {'online': None, 'fails': 0}
            ok = bool(ok) if not isinstance(ok, Exception) else False
            if ok:
                if st.get('online') is False:
                    events.append(f"✅ 已恢复：{name}")
                st = {'online': True, 'fails': 0}
            else:
                fails = int(st.get('fails', 0)) + 1
                if st.get('online') is not False and fails >= threshold:
                    if st.get('online') is True:
                        events.append(f"⚠️ 已离线：{name}")
                    st = {'online': False, 'fails': fails}
                else:
                    st = {'online': st.get('online'), 'fails': fails}
            self._server_status[name] = st
        first_round = not self._status_baseline_done
        self._status_baseline_done = True
        if first_round or not events:
            if first_round:
                online_n = sum(1 for v in self._server_status.values() if v.get('online'))
                logger.info(f"🖥️ 服务器状态基线已建立：{online_n}/{len(targets)} 在线（首轮不播报）")
            return
        shown, rest = events[:limit], events[limit:]
        text = "🖥️ 【服务器状态变化】\n" + "\n".join(shown)
        if rest:
            text += f"\n…另有 {len(rest)} 条变化（省略）"
        logger.info(f"🖥️ 服务器状态变化播报 {len(events)} 条")
        await self._broadcast(text)

    async def _initial_status_baseline(self):
        """启动后尽快建立服务器状态基线（最多等 90 秒直到 RCON 目标与密码就绪）"""
        for _ in range(45):
            if self.rcon_targets and self.rcon_password:
                try:
                    await self._check_server_status()
                except Exception as e:
                    logger.debug(f"启动状态基线探测失败: {e}")
                return
            await asyncio.sleep(2)

    def _status_summary(self) -> str:
        """当前已知的服务器状态摘要（/状态 用）"""
        if not self._server_status:
            return "ℹ️ 还没有状态数据（等一轮检查后再试）"
        on = [k for k, v in self._server_status.items() if v.get('online')]
        off = [k for k, v in self._server_status.items() if v.get('online') is False]
        unk = [k for k, v in self._server_status.items() if v.get('online') is None]
        out = [f"🖥️ 服务器状态（在线 {len(on)} / 离线 {len(off)} / 未知 {len(unk)}）"]
        if off:
            out.append("离线：\n" + "\n".join(f"· {x}" for x in off[:15]))
        if unk:
            out.append("未知：\n" + "\n".join(f"· {x}" for x in unk[:10]))
        return "\n".join(out)

    def _arkshop_excluded(self, target) -> bool:
        """该服务器是否没装 ArkShop（配置 arkshop_exclude_servers 里的名字子串，不区分大小写）"""
        names = self.config.get('arkshop_exclude_servers') or []
        if not names:
            return False
        tname = str((target or {}).get('name') or '').lower()
        if not tname:
            return False
        return any(str(n).strip().lower() and str(n).strip().lower() in tname for n in names)

    def _arkshop_targets(self, targets=None) -> list:
        """过滤掉没装 ArkShop 的服务器"""
        src = self.rcon_targets if targets is None else targets
        kept = [t for t in (src or []) if not self._arkshop_excluded(t)]
        skipped = [t.get('name') for t in (src or []) if self._arkshop_excluded(t)]
        if skipped:
            logger.debug(f"⏭️ 跳过未装 ArkShop 的服务器: {skipped}")
        return kept

    async def _send_rcon_command_to_all(self, command: str, skip_arkshop_excluded: bool = False):
        """向全部 RCON 目标并发发送命令（单个失败不影响其它目标）
        skip_arkshop_excluded=True 时跳过没装 ArkShop 的服务器（如 club / 海洋）。"""
        targets = self._arkshop_targets() if skip_arkshop_excluded else self.rcon_targets
        await self._send_rcon_concurrent(targets, command)

    async def _send_rcon_concurrent(self, targets: list, command: str):
        """并发向多个 RCON 目标发送同一命令，逐目标记录成功/失败，互不阻塞。

        单个目标的超时时间由 config 的 rcon_timeout 控制（见 _send_rcon_command_sync）。
        """
        targets = [t for t in targets or [] if t.get('host') and t.get('port')]
        if not targets:
            return
        loop = asyncio.get_running_loop()

        async def _send_one(t):
            host, port = t.get('host'), t.get('port')
            logger.info(f"📤 发送到 {t.get('name')} ({host}:{port})")
            try:
                await loop.run_in_executor(None, self._send_rcon_command_sync, host, port, command)
            except Exception as e:
                logger.error(f"❌ 发送到 {t.get('name')} 失败: {e}")

        await asyncio.gather(*(_send_one(t) for t in targets))

    async def _check_rate_update(self):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.config.get('dynamic_ini_url') or DYNAMIC_INI_URL)
                resp.encoding = 'utf-8'
                content = resp.text
            current = _parse_dynamic_ini(content)
            new_hash = hashlib.md5(json.dumps(current, sort_keys=True).encode()).hexdigest()
            if self.last_rate_hash is None:
                self.last_rate_hash = new_hash
                self.last_rate_content = current
                return
            if new_hash != self.last_rate_hash:
                changes = []
                all_keys = set(current.keys()) | set(self.last_rate_content.keys())
                for key in all_keys:
                    old = self.last_rate_content.get(key, "无")
                    new = current.get(key, "无")
                    if old != new:
                        cn = RATE_NAMES.get(key, key)
                        changes.append(f"🔄 {cn}：{old} → {new}")
                if changes:
                    await self._send_rcon_command_to_all("ForceUpdateDynamicConfig", skip_arkshop_excluded=True)
                    # 游戏内广播（精简摘要）
                    short = []
                    for c in changes[:5]:
                        parts = c.split("：")
                        if len(parts) == 2:
                            short.append(parts[0].replace("🔄 ", "") + ":" + parts[1].split("→")[-1].strip())
                    broadcast = "服务器倍率已更新: " + " | ".join(short)
                    await self._send_rcon_command_to_all(f"serverchat {self._game_safe(broadcast)}")
                    msg = "📊 【服务器倍率更新提醒】\n" + "\n".join(changes)
                    await self._send_notify(msg + self.footer)
                    self.last_rate_hash = new_hash
                    self.last_rate_content = current
        except Exception as e:
            logger.error(f"检查倍率失败: {e}")

    async def _send_notify(self, message: str):
        await self._broadcast(message)

    # ======================== 平台发送层（OneBot + QQ 官方机器人） ========================
    def _platform_insts(self):
        """获取所有平台适配器实例"""
        try:
            pm = getattr(self.context, 'platform_manager', None)
            insts = getattr(pm, 'platform_insts', None) if pm else None
            return list(insts) if insts else []
        except Exception:
            return []

    def _find_platform_inst(self, name: str):
        """按适配器名查找平台实例（qq_official / aiocqhttp）"""
        for p in self._platform_insts():
            try:
                if getattr(p.meta(), 'name', '') == name:
                    return p
            except Exception:
                continue
        return None

    def _platform_tag(self) -> str:
        """当前优先平台标识：qq_official（openid 体系）或 qq（OneBot QQ号体系）"""
        return 'qq_official' if self._find_platform_inst('qq_official') is not None else 'qq'

    def _platform_tag_for(self, event=None) -> str:
        """绑定记录里的平台标识：优先事件来源平台（qq_official / kook / aiocqhttp），否则按适配器推断"""
        name = self._event_platform(event) if event is not None else ''
        return name or self._platform_tag()

    @staticmethod
    def _mask_id(value, head: int = 6, tail: int = 4) -> str:
        """用户标识打码（公共区域展示用）：保留前 head 与后 tail 字符"""
        s = str(value or '').strip()
        if len(s) <= head + tail + 1:
            return s
        return f"{s[:head]}…{s[-tail:]}"

    # 群里"没 @机器人 就发指令"时用于识别并提示的命令名
    CMD_HINTS = ("绑定", "解绑", "查绑定", "签到", "在线玩家", "在线", "谁在线", "进化", "飞升", "查服",
                 "倍率", "直连", "帮助", "我是谁", "代加点", "加点", "rcon", "测试推送", "更新地址",
                 "bind", "unbind", "mybind", "signin", "players", "help", "whoami", "关联", "link")

    def _looks_like_command(self, text: str) -> bool:
        """判断一条群消息是不是"想发指令但没 @机器人"（首 token 精确等于某个命令名，或带 / 前缀）"""
        t = str(text or '').strip()
        slash = t.startswith('/')
        body = t.lstrip('/').strip()
        if not body:
            return False
        first = body.split()[0].lower()
        return slash or first in {c.lower() for c in self.CMD_HINTS}

    def _at_bot(self, event) -> bool:
        """消息里是否 @ 了机器人 / @全体（兜底用：适配器的 @ 有时没被 AstrBot 识别成 wake，
        于是 is_at_or_wake_command 为 False，不能只靠它判断"这是对着机器人说的"）"""
        try:
            self_id = str(event.get_self_id() or '')
        except Exception:
            self_id = ''
        try:
            for comp in (event.get_messages() or []):
                cname = type(comp).__name__.lower()
                if 'atall' in cname:
                    return True          # @全体也视为"喊话"，不往游戏公屏转
                if cname.startswith('at') and getattr(comp, 'qq', None) is not None:
                    if not self_id or str(getattr(comp, 'qq')) == self_id:
                        return True
        except Exception:
            pass
        text = str(getattr(event, 'message_str', '') or '')
        return ('[At:' in text) or ('(met)' in text)

    async def _wait_platform(self, platform_name: str, purpose: str = "", timeout: float = 20.0):
        """等待指定平台适配器就绪；超时返回 None（避免后台任务无限等待）"""
        deadline = time.time() + max(1.0, timeout)
        while True:
            inst = self._find_platform_inst(platform_name)
            if inst is not None:
                return inst
            if time.time() >= deadline:
                logger.warning(f"⚠️ 平台 {platform_name} 未就绪，跳过发送（{purpose}）")
                return None
            await asyncio.sleep(1.0)

    def _broadcast_targets(self) -> list:
        """主动消息目标列表 [{platform,id,label}]；未配置时回退为 notify_group（QQ群）"""
        out = []
        raw = self.config.get('broadcast_targets') or []
        if isinstance(raw, list):
            for t in raw:
                if isinstance(t, dict) and t.get('id'):
                    out.append({'platform': str(t.get('platform') or 'qq_official'),
                                'id': str(t['id']),
                                'label': str(t.get('label') or '')})
        if not out:
            g = self.config.get('notify_group')
            if g:
                out.append({'platform': 'qq_official', 'id': str(g), 'label': 'QQ群'})
        return out

    @staticmethod
    def _target_key(platform: str, target_id) -> str:
        return f"{str(platform or '').strip()}:{str(target_id).strip()}"

    @staticmethod
    def _target_label(name) -> str:
        """服务器显示名：去掉名称尾部附带的 host:port，避免把直连/RCON 地址发到群里"""
        s = str(name or '').strip()
        s = re.sub(r'\s*[A-Za-z0-9._-]+:\d{2,5}\s*$', '', s).strip()
        return s or "未知服务器"

    def _platform_label(self, platform_name: str) -> str:
        for t in self._broadcast_targets():
            if t['platform'] == platform_name and t.get('label'):
                return t['label']
        return {'qq_official': 'QQ群', 'aiocqhttp': 'QQ群', 'kook': 'KOOK'}.get(
            platform_name or '', platform_name or '群')

    @staticmethod
    def _platform_tag_cn(tag: str) -> str:
        """绑定记录里的平台标识 → 中文（/查绑定 展示用）"""
        return {'qq_official': 'QQ官方', 'aiocqhttp': 'QQ(OneBot)', 'kook': 'KOOK',
                'legacy': '旧版待重绑', 'auto': '自动关联', '': '未知'}.get(str(tag or ''), str(tag))

    @staticmethod
    def _event_platform(event) -> str:
        """事件来源平台名（qq_official / kook / aiocqhttp …），取不到返回空串"""
        try:
            return str(event.get_platform_name() or '')
        except Exception:
            return ''

    def _invite_line(self, platform_name: str = "") -> str:
        """按平台互推对方社区：QQ 侧显示 KOOK 邀请，KOOK 侧显示 QQ 群号（未配置则返回空串）"""
        kook = str(self.config.get('invite_kook') or '').strip()
        qq = str(self.config.get('invite_qq') or '').strip()
        if (platform_name or '').strip() == 'kook':
            return f"💬 玩家 QQ 群：{qq}" if qq else ""
        return f"🔗 KOOK 社区：{kook}" if kook else ""

    async def _send_group_text(self, platform: str, group_id, message: str) -> bool:
        """按平台名主动发送群/频道消息；platform 为空或 aiocqhttp 时走旧的 QQ 发送链"""
        plat = (platform or '').strip()
        if not plat or plat == 'aiocqhttp':
            return await self._send_group_msg(group_id, message)
        inst = await self._wait_platform(plat, f"群消息发送({str(group_id)[:12]})")
        if inst is None:
            return False
        return await self._official_send(inst, 'group', str(group_id), message)

    async def _broadcast(self, message: str, exclude: str = "") -> int:
        """把消息发到所有 broadcast 目标（exclude 传 'platform:id' 可跳过来源，用于群间互通）"""
        targets = self._broadcast_targets()
        if not targets:
            logger.warning("⚠️ 未配置 broadcast_targets / notify_group，主动消息无处可发")
            return 0
        sent = 0
        for t in targets:
            key = self._target_key(t['platform'], t['id'])
            if exclude and key == exclude:
                continue
            if await self._send_group_text(t['platform'], t['id'], message):
                sent += 1
            else:
                logger.error(f"❌ 主动消息发送失败（{t['label'] or key}）")
        return sent

    def _find_aiocqhttp_client(self):
        """定位 aiocqhttp(OneBot) 适配器的 client；找不到返回 None"""
        p = self._find_platform_inst('aiocqhttp')
        if p is not None:
            try:
                c = p.get_client()
                if c is not None:
                    return c
            except Exception as e:
                logger.debug(f"AIOCQHTTP client 获取失败: {e}")
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
            for p in self._platform_insts():
                if isinstance(p, AiocqhttpAdapter):
                    c = p.get_client()
                    if c is not None:
                        return c
        except Exception as e:
            logger.debug(f"AIOCQHTTP 适配器(平台管理器)查找失败: {e}")
        return None

    async def _wait_qq_adapter(self, purpose: str = "发送消息", timeout: float = 20.0):
        """等待任一可用 QQ 平台就绪：优先 QQ 官方机器人，其次 OneBot；返回 (kind, obj)，超时返回 None"""
        logger.info(f"⏳ 等待 QQ 适配器连接（{purpose}，最多 {int(timeout)} 秒）...")
        deadline = time.time() + max(1.0, float(timeout))
        while time.time() < deadline:
            official = self._find_platform_inst('qq_official')
            if official is not None:
                logger.info(f"✅ QQ 官方机器人适配器就绪（{purpose}）")
                return ('qq_official', official)
            client = self._find_aiocqhttp_client()
            if client is not None:
                try:
                    await client.api.call_action("get_login_info", timeout=5.0)
                    logger.info(f"✅ OneBot 适配器已连接（{purpose}）")
                    return ('aiocqhttp', client)
                except Exception as e:
                    logger.debug(f"适配器未就绪: {e}")
            await asyncio.sleep(2)
        # 关键：必须有超时，否则没有 QQ 适配器时调用方会永久挂住（用户永远收不到回复）
        logger.warning(f"⚠️ 等待 QQ 适配器超时（{purpose}），本次放弃")
        return None

    # ======================== KOOK 卡片按钮点击补丁 ========================
    # AstrBot 的 KOOK 适配器只处理 KMARKDOWN/CARD，SYSTEM(255) 里仅实现"角色更新"，
    # 「卡片按钮点击」(extra.type=message_btn_click) 会被当未实现通知丢弃 → 这里包一层补上。
    def _install_kook_button_patch(self):
        if not self.config.get('kook_button_patch', True):
            logger.info("ℹ️ KOOK 按钮补丁已按配置关闭（kook_button_patch=false）")
            return
        try:
            from astrbot.core.platform.sources.kook.kook_adapter import KookPlatformAdapter
        except Exception as e:
            logger.debug(f"KOOK 按钮补丁跳过（导入失败）: {e}")
            return
        if getattr(KookPlatformAdapter, '_zs_button_patched', False):
            return
        original = KookPlatformAdapter._on_received

        async def _patched_on_received(adapter_self, event_data):
            try:
                extra = getattr(event_data, 'extra', None)
                if str(getattr(extra, 'type', '') or '') == 'message_btn_click':
                    body = getattr(extra, 'body', None)
                    value = self._kook_body_field(body, 'value')
                    uid = self._kook_body_field(body, 'user_id') or str(getattr(event_data, 'author_id', '') or '')
                    nick = ''
                    info = body.get('user_info') if isinstance(body, dict) else getattr(body, 'user_info', None)
                    if isinstance(info, dict):
                        nick = str(info.get('nickname') or info.get('username') or '')
                    elif info is not None:
                        nick = str(getattr(info, 'nickname', '') or getattr(info, 'username', '') or '')
                    if value and uid:
                        logger.info(f"🖱️ KOOK 按钮点击: {value!r} ← {str(uid)[:8]}…")
                        # 回到点击发生的那个频道（点击在频道 → 回频道；点在私聊 → 回私聊）
                        dest = self._kook_body_field(body, 'target_id')
                        ctype = self._kook_body_field(body, 'channel_type')
                        asyncio.create_task(self._run_kook_button_command(
                            adapter_self, uid, nick, value, dest, ctype))
                        return
            except Exception as e:
                logger.debug(f"KOOK 按钮补丁处理异常: {e}")
            return await original(adapter_self, event_data)

        KookPlatformAdapter._on_received = _patched_on_received
        KookPlatformAdapter._zs_button_patched = True
        logger.info("🔧 已装载 KOOK 卡片按钮补丁（实验功能；kook_button_patch=false 可关闭）")

    @staticmethod
    def _kook_body_field(body, key: str) -> str:
        """按钮点击事件的 extra.body 可能是 dict 也可能是模型对象"""
        if body is None:
            return ''
        if isinstance(body, dict):
            return str(body.get(key) or '')
        return str(getattr(body, key, '') or '')

    # 按钮 value → 内部处理函数（不走管道，直接执行 + 私聊回结果）
    KOOK_BUTTON_COMMANDS = {
        '在线玩家': '_players_cmd', '在线': '_players_cmd',
        '签到': '_signin_cmd', '查绑定': '_mybind_cmd', '菜单': '_menu_cmd',
    }

    # ARK 公屏能正常显示中文，但 emoji / 部分符号会变成"缺字形方块（◇里带问号）"→ 发往游戏前统一剔除
    EMOJI_RE = re.compile(
        "[\U0001F000-\U0001FAFF"      # emoji 与符号
        "\U0001F1E6-\U0001F1FF"       # 区域指示符（国旗）
        "\U00002600-\U000027BF"       # 杂项符号 / 装饰符号
        "\U00002190-\U000021FF"       # 箭头
        "\U00002B00-\U00002BFF"       # 杂项符号与箭头
        "\U00002000-\U0000206F"       # 通用标点（弯引号、破折号、省略号…）
        "\U0000FE0F\U0000200D\U000020E3"
        "]+")

    # 转发到游戏公屏前顺带把"@提及"里的真实 ID 换掉：
    # QQ 官方机器人的 @ 在文本里是 <@openid>，KOOK 是 (met)userid(met) —— 直接发出去等于把 ID 泄露到公屏
    MENTION_RE = re.compile(r'(?:<@!?[A-Za-z0-9_\-]{5,}>)|(?:\(met\)[A-Za-z0-9_\-]{3,}\(met\))')

    def _game_safe(self, text: str) -> str:
        """发往游戏公屏前清理：ARP 显示不了的字形（emoji/符号）+ @提及里的真实 ID"""
        s = self.EMOJI_RE.sub('', str(text or ''))
        s = self.MENTION_RE.sub('@某人', s)
        return re.sub(r'[ \t]{2,}', ' ', s).strip()

    # ======================== CCA（CrossChatAscended）通道 ========================
    @staticmethod
    def _cca_label_safe(text: str) -> str:
        """CCA 的 Map 标签字段只吃 ASCII —— 实测写中文（如「跨服-KOOK」）会被它按单字节解码成乱码
        （游戏里显示 [|σ¤¥η∧-KOOK]），所以标签统一只保留可打印 ASCII，非 ASCII 直接丢掉。"""
        s = str(text or '')
        s = ''.join(ch for ch in s if '\x20' <= ch <= '\x7e')
        return s.strip()

    def _cca_label_for(self, platform_name: str) -> str:
        key = 'cca_map_label_kook' if (platform_name or '') == 'kook' else 'cca_map_label'
        return self._cca_label_safe(
            self.config.get(key) or ('KOOK' if key.endswith('kook') else 'QQ'))

    def _cca_labels(self) -> set:
        """我们自己写进 CCA 表时用的 Map 标签集合（用于在跨服转发时跳过这些行，防回声）
        注意要与真正写库时的取值完全一致，所以同样过一遍 _cca_label_safe()。"""
        return {self._cca_label_safe(self.config.get('cca_map_label') or 'QQ'),
                self._cca_label_safe(self.config.get('cca_map_label_kook') or 'KOOK')}

    async def _cca_send(self, platform_name: str, sender: str, message: str) -> bool:
        """把消息写进 CrossChatAscended 的 cross_chat 表：各服装有 CCA 就会自动打印（带 CCA 的格式/颜色）"""
        srcs = [s for s in (self.config.get('db_sources') or [])
                if str(s.get('id')) in ('asa_chat', 'ase_chat') and s.get('host') and s.get('user')]
        if not srcs:
            logger.warning("⚠️ 未配置 asa_chat / ase_chat 数据源，无法走 CCA 通道")
            return False
        label = self._game_safe(self._cca_label_for(platform_name))[:50]
        if not label:
            label = 'CrossServer'
        # Map 标签字段只吃 ASCII，所以"跨服"这类中文标记放在**发送者**里（该字段中文正常）
        sender_prefix = str(self.config.get('cca_sender_prefix') or '')
        sender = self._game_safe(sender_prefix + str(sender))[:100]
        message = self._game_safe(message)[:250]
        ok_any = False
        for src in srcs:
            ase = str(src.get('id')) == 'ase_chat'
            table = src.get('table', 'cross_chat')
            if ase:      # ASE 表用 SteamId，没有 SenderPlatform 列
                cols = "(`SteamId`,`Map`,`Sender`,`Message`,`TribeName`,`TribeId`,`Mode`,`Tags`,`isPm`,`PmRecipient`)"
                vals = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                args = (0, label, sender, message, '', 0, 0, '', 0, '')
            else:        # ASA 表
                cols = ("(`EOSid`,`Map`,`Sender`,`Message`,`SenderPlatform`,`TribeName`,`TribeId`,"
                        "`Mode`,`Tags`,`isPm`,`PmRecipient`)")
                vals = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                args = ('', label, sender, message, 0, '', 0, 0, '', 0, '')
            conn = None
            try:
                conn = await aiomysql.connect(host=src.get('host'), port=int(src.get('port') or 3306),
                                              user=src.get('user'), password=src.get('password'),
                                              db=src.get('database'), charset='utf8mb4',
                                              autocommit=True, connect_timeout=5)
                cur = await conn.cursor()
                await cur.execute(f"INSERT INTO {table} {cols} VALUES {vals}", args)
                await cur.close()
                ok_any = True
                logger.info(f"✅ 已写入 CCA（{src.get('id')}）: [{label}] {sender}: {message[:40]}")
            except Exception as e:
                logger.error(f"❌ 写入 CCA 失败（{src.get('id')}）: {type(e).__name__}: {e}")
            finally:
                # 异常路径也必须关连接，否则每失败一次就漏一个
                if conn is not None:
                    try:
                        await conn.ensure_closed()
                    except Exception:
                        pass
        return ok_any

    @staticmethod
    def _result_text(res) -> str:
        """把指令处理器产出的 MessageEventResult 抽成纯文本"""
        try:
            t = res.get_plain_text()
            if t:
                return str(t)
        except Exception:
            pass
        try:
            parts = []
            for comp in (getattr(res, 'chain', None) or []):
                txt = getattr(comp, 'text', None)
                if txt:
                    parts.append(str(txt))
            return "\n".join(parts)
        except Exception:
            return ""

    async def _run_kook_button_command(self, adapter_inst, user_id, nickname, value: str,
                                       dest: str = '', channel_type: str = ''):
        """KOOK 卡片按钮点击：把 value 当指令执行，结果**发回点击发生的那个频道**（点在私聊就回私聊）。
        不注入 AstrBot 管道 —— 一是避免 LLM 也插一句，二是伪造的 msg_id 会被 KOOK 当"引用不存在"拒收。"""
        text = str(value).strip()
        if text.startswith('/'):
            text = text[1:]
        text = text.strip()
        if not text:
            return
        name = text.split()[0]
        in_channel = bool(dest) and str(channel_type).upper() not in ('PERSON', '')
        try:
            from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
            from astrbot.api.message_components import Plain
            abm = AstrBotMessage()
            abm.type = MessageType.GROUP_MESSAGE if in_channel else MessageType.FRIEND_MESSAGE
            abm.self_id = str(getattr(getattr(adapter_inst, 'client', None), 'bot_id', '') or '')
            abm.session_id = str(dest) if in_channel else str(user_id)
            abm.group_id = str(dest) if in_channel else ''
            abm.sender = MessageMember(user_id=str(user_id), nickname=nickname or str(user_id))
            abm.message_id = ''
            abm.message = [Plain(text=text)]
            abm.message_str = text
            abm.raw_message = {"from": "kook_button_click", "value": value}
            ev = adapter_inst.create_event(abm)
            ev.is_wake = True
            ev.is_at_or_wake_command = True
        except Exception as e:
            logger.error(f"❌ KOOK 按钮补丁：构造事件失败 {type(e).__name__}: {e}")
            return
        outs = []
        try:
            if name == '状态':
                outs.append(self._status_summary())
            elif name == '直连':
                async for r in self.direct_command(ev):
                    outs.append(self._result_text(r))
            elif name == '倍率':
                async for r in self.rate_command(ev):
                    outs.append(self._result_text(r))
            elif name in ('我的ID', '我的id', 'myid'):
                async for r in self._myid_cmd(ev):
                    outs.append(self._result_text(r))
            elif name in ('帮助', 'help'):
                group = self._event_group_id(ev)
                outs.append("\n".join(self._help_lines(self._is_owner(ev), self._event_platform(ev),
                                                       bool(group), '')))
            elif name in self.KOOK_BUTTON_COMMANDS:
                handler = getattr(self, self.KOOK_BUTTON_COMMANDS[name])
                async for r in handler(ev):
                    outs.append(self._result_text(r))
            else:
                outs.append(f"ℹ️ 这个按钮我还没接上：{value}\n直接发 /指令 就行，例如 /帮助")
        except Exception as e:
            logger.error(f"❌ KOOK 按钮指令执行失败: {type(e).__name__}: {e}")
            outs.append(f"❌ 执行 {value} 出错：{type(e).__name__}")
        body = "\n\n".join([o for o in outs if o]).strip() or "（没有输出）"
        if in_channel:
            ok = await self._send_group_text('kook', str(dest), body)
            logger.info(f"🖱️ KOOK 按钮 {value!r} → 回频道 {str(dest)[:8]}…{'成功' if ok else '失败'}")
            if ok:
                return
            logger.warning("KOOK 按钮回频道失败，改走私聊")
        ok = await self._send_private_msg(user_id, body, platform='kook')
        logger.info(f"🖱️ KOOK 按钮 {value!r} → 私聊回执{'成功' if ok else '失败'}")

    async def _official_send(self, platform_inst, message_type: str, session_id: str, message: str) -> bool:
        """通过 QQ 官方机器人 send_by_session 主动发送（群=group_openid，私聊=user_openid）"""
        try:
            from astrbot.api.event import MessageChain
            from astrbot.core.platform.message_session import MessageSession
            from astrbot.core.platform.message_type import MessageType
            mtype = MessageType.GROUP_MESSAGE if message_type == 'group' else MessageType.FRIEND_MESSAGE
            # 群聊：适配器要求已记录 scene=group 才允许主动发送（收到过该群消息即可满足）
            if mtype == MessageType.GROUP_MESSAGE:
                try:
                    platform_inst.remember_session_scene(str(session_id), 'group')
                except Exception:
                    pass
            platform_id = ''
            try:
                platform_id = str(platform_inst.meta().id or '')
            except Exception:
                pass
            session = MessageSession(
                platform_name=platform_id or 'qq_official',
                message_type=mtype,
                session_id=str(session_id),
            )
            await platform_inst.send_by_session(session, MessageChain().message(message))
            logger.info(f"✅ 主动消息已发送（{platform_id or '?'} {message_type}:{str(session_id)[:12]}...）")
            return True
        except Exception as e:
            logger.error(f"❌ 主动消息发送失败（{message_type}:{str(session_id)[:12]}...）: {type(e).__name__}: {e}")
            return False

    @staticmethod
    def _umo_group_id(umo) -> str:
        """从 unified_msg_origin 中解析会话标识（数字群号或 openid）；无法解析返回空串"""
        try:
            sess = str(getattr(umo, 'session_id', '') or umo)
        except Exception:
            return ""
        m = re.search(r'group[_:]?([A-Za-z0-9_-]{5,})', sess)
        if m:
            return m.group(1)
        parts = sess.split(':')
        return parts[-1] if len(parts) >= 3 else ''

    async def _send_group_msg(self, group_id, message: str) -> bool:
        """主动发送群消息：优先 QQ 官方机器人，其次 OneBot（含 umo 回复通道）"""
        kind, obj = await self._wait_qq_adapter("群消息发送") or (None, None)
        if kind is None:
            logger.warning(f"⚠️ 没有可用 QQ 适配器，群消息 {group_id} 发送失败")
            return False
        if kind == 'qq_official':
            return await self._official_send(obj, 'group', str(group_id), message)
        client = obj
        # OneBot 方式1: 用捕获的 umo 发送（仅当 umo 所在群与目标群一致，避免发错群）
        try:
            from astrbot.api.event import MessageChain
            umo = getattr(self, '_notify_umo', None) or getattr(self, '_last_umo', None)
            if umo and str(group_id) == self._umo_group_id(umo):
                await self.context.send_message(umo, MessageChain().message(message))
                logger.info(f"✅ 消息已发送到群 {group_id} (umo方式)")
                return True
        except Exception as e:
            logger.error(f"❌ umo 发送失败: {e}")
        # OneBot 方式2: call_action
        try:
            await client.api.call_action("send_group_msg", group_id=group_id, message=message)
            logger.info(f"✅ 消息已发送到群 {group_id} (call_action方式)")
            return True
        except Exception as e:
            logger.error(f"❌ 平台发送群消息失败: {e}")
        return False

    async def _send_private_msg(self, user_id, message: str, platform: str = '') -> bool:
        """主动发送私聊消息：platform 指定时用该平台（KOOK 等），否则按 QQ 官方 → OneBot 回退"""
        plat = (platform or '').strip()
        if plat and plat != 'aiocqhttp':
            inst = await self._wait_platform(plat, f"私聊发送({str(user_id)[:12]})")
            if inst is None:
                return False
            return await self._official_send(inst, 'private', str(user_id), message)
        kind, obj = await self._wait_qq_adapter("私聊消息发送") or (None, None)
        if kind is None:
            logger.warning(f"⚠️ 没有可用 QQ 适配器，私聊 {str(user_id)[:12]} 发送失败")
            return False
        if kind == 'qq_official':
            return await self._official_send(obj, 'private', str(user_id), message)
        client = obj
        try:
            await client.api.call_action("send_private_msg", user_id=user_id, message=message)
            logger.info(f"✅ 私聊消息已发送到 {user_id} (call_action方式)")
            return True
        except Exception as e:
            logger.error(f"❌ 发送私聊消息失败: {e}")
        return False

    async def _check_cache_updates(self):
        """定时检查缓存镜像目录（支持多镜像）。规则：
        ① 同一文件名出现在多个镜像只算一次（并集去重）；
        ② 已通知过的不再提醒（notified_cache.json 持久化）；
        ③ 只有从未见过的新缓存文件才私聊+群通知一次。"""
        mirrors = self.config.get('cache_mirror_urls') or []
        if not mirrors:
            legacy = self.config.get('cache_mirror_url') or ''
            mirrors = [legacy]
        interval = self.config.get('cache_check_interval_minutes', 10) * 60
        cache_record_file = os.path.join(os.path.dirname(__file__), "notified_cache.json")
        if os.path.exists(cache_record_file):
            try:
                with open(cache_record_file, "r", encoding="utf-8") as f:
                    self.seen_cache_files = set(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"⚠️ notified_cache.json 读取失败({e})，重置已通知记录")
                self.seen_cache_files = set()
        else:
            self.seen_cache_files = set()

        await asyncio.sleep(15)
        logger.info(f"🔄 缓存更新检测已启动，镜像 {len(mirrors)} 个: {mirrors}，间隔 {interval}s")
        while True:
            if not mirrors or not any(mirrors):
                logger.info('⚠️ 未配置缓存镜像地址（cache_mirror_url），缓存更新检测暂停')
                await asyncio.sleep(interval)
                continue
            try:
                async def _scan(url) -> set:
                    """抓取单个镜像页面，返回其中的 64位hash 文件名集合；失败返回空集（不影响其它镜像）"""
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                return set(re.findall(r'([a-f0-9]{64})\.zip', resp.text))
                    except Exception as e:
                        logger.warning(f"⚠️ 缓存镜像访问失败 {url}: {e}")
                    return set()

                # 并发扫描所有镜像后取并集：同一文件多镜像只算一次
                results = await asyncio.gather(*(_scan(u) for u in mirrors))
                all_found = set()
                for s in results:
                    all_found |= s

                new_hashes = all_found - self.seen_cache_files
                if new_hashes:
                    new_files = sorted(h + ".zip" for h in new_hashes)
                    self.seen_cache_files |= all_found
                    try:
                        with open(cache_record_file, "w", encoding="utf-8") as f:
                            json.dump(sorted(self.seen_cache_files), f)
                    except OSError as e:
                        logger.error(f"❌ notified_cache.json 写入失败: {e}")
                    msg = "🆕 提示：有新服务器版本更新，请及时更新！"
                    logger.info(f"✅ 新缓存通知: {new_files}")
                    # 私聊通知
                    notify_qq = self.config.get('update_notify_qq', )
                    ok = await self._send_private_msg(notify_qq, msg)
                    if not ok:
                        logger.error(f"❌ 发送私聊更新通知到 {notify_qq} 失败")
                    # 群通知（QQ 群 + KOOK 频道等广播目标）
                    if await self._broadcast(msg) == 0:
                        logger.error("❌ 群更新通知发送失败：没有任何目标发送成功")
            except Exception as e:
                logger.error(f"❌ 检查缓存更新失败: {e}")
            await asyncio.sleep(interval)

    def _query_via_rcon_sync(self, host: str, port: int) -> dict:
        if not self.rcon_password:
            return None
        try:
            with RconClient(host, port, passwd=self.rcon_password, timeout=self.config.get('rcon_timeout', 10.0)) as client:
                raw = client.run("getserverinfo")
                info = {}
                for line in raw.splitlines():
                    if ': ' in line:
                        k, v = line.split(': ', 1)
                        info[k.strip()] = v.strip()

                def _info_get(*names, default=""):
                    """按“忽略大小写/空格/下划线”取值：不同 ARK 版本 getserverinfo 字段名不一致"""
                    for k, v in info.items():
                        kk = re.sub(r'[\s_\-]', '', str(k)).lower()
                        if kk in names:
                            return v
                    return default

                raw_players = client.run("listplayers")
                players = []
                for line in raw_players.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    low = line.lower()
                    # 空服提示行（如 "No Players Connected"）不是玩家
                    if 'no players' in low or low.startswith('players:'):
                        continue
                    if re.match(r'^\d+\.', line):
                        name_part = re.split(r'^\d+\.\s*', line, maxsplit=1)[-1].strip()
                        name = re.sub(r'\s*\([^)]+\)$', '', name_part).strip()
                        if ',' in name:
                            name = name.split(',')[0].strip()
                        if name:
                            players.append(name)
                    elif ',' in line:
                        name = line.split(',')[0].strip()
                        if name:
                            players.append(name)
                    # 其它无法识别的文本行不再当作玩家，避免幽灵人数
                maxp_raw = _info_get('maxplayers', 'maxplayer', 'maxplayerslimit', default='0')
                try:
                    maxp = int(maxp_raw)
                except (TypeError, ValueError):
                    maxp = 0
                return {
                    "map_name": _info_get('map', 'mapname', default='未知') or '未知',
                    "max_players": maxp,
                    "player_count": len(players),
                    "player_names": players,
                    "server_name": _info_get('servername', 'name', 'sessionname', default='未知') or '未知',
                    "source": "RCON"
                }
        except Exception as e:
            logger.error(f"RCON 查询失败: {e}")
            return None

    async def _query_via_rcon(self, host: str, port: int) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._query_via_rcon_sync, host, port)

    async def _get_players_via_rcon(self, version: str, map_name: str):
        """当 API/A2S 查不到在线玩家时的备用方案：通过 RCON listplayers 获取。
        返回 (player_count, player_names)；失败返回 (None, None)。
        """
        rcon_ver = self.rcon_cache.get(version, {})
        if not rcon_ver or not map_name:
            return None, None
        # 模糊匹配地图名 -> RCON 地址（与 ASA 回退同一套逻辑）
        key = _fuzzy_key(rcon_ver, map_name)
        rcon_addr_list = rcon_ver[key] if key else None
        if not rcon_addr_list:
            logger.info(f"RCON 玩家补全: {version} 未找到 '{map_name}' 的 RCON 地址")
            return None, None
        rcon_addr = rcon_addr_list[0]
        if ":" not in rcon_addr:
            rcon_addr += ":7777"
        host, port_str = rcon_addr.split(":")
        try:
            port = int(port_str)
        except ValueError:
            return None, None
        result = await self._query_via_rcon(host, port)
        if not result:
            return None, None
        pcount = result.get('player_count', 0)
        pnames = result.get('player_names', [])
        logger.info(f"RCON 玩家补全: {version}/{map_name} -> {pcount} 人")
        return pcount, pnames

    def _execute_rcon_command_sync(self, host: str, port: int, command: str) -> str:
        if not self.rcon_password:
            return "❌ RCON 密码未配置"
        try:
            with RconClient(host, port, passwd=self.rcon_password, timeout=self.config.get('rcon_timeout', 10.0)) as client:
                result = client.run(command)
                return result.strip() if result else "(无输出)"
        except Exception as e:
            return f"❌ 错误: {e}"

    def _format_arkstatus(self, s: dict) -> dict:
        # 注意：ARK Status API 返回 max_players（带下划线），非 maxplayers
        maxp = s.get('max_players', s.get('maxplayers', 0))
        return {
            "ip": s.get('ip'), "port": s.get('port'),
            "name": s.get('name', '未知'), "map": s.get('map', '未知'),
            "players": s.get('players', 0), "max_players": maxp,
            "source": "ARK Status"
        }

    async def _fetch_zeroark_servers(self) -> list:
        """单次 ARK Status 搜索 ZeroARK 关键词，返回在线服务器列表（原始 dict）"""
        api_key = self.config.get('arkstatus_api_key', DEFAULT_ARKSTATUS_API_KEY)
        if not api_key:
            return []
        headers = {"X-API-Key": api_key}
        params = {"search": "ZeroARK", "status": "online", "server_type": "unofficial", "per_page": 100}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(ARKSTATUS_API_BASE, headers=headers, params=params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                if not data.get('success') or not data.get('data'):
                    return []
                return data['data']
        except Exception as e:
            logger.warning(f"ARK Status API 查询失败: {e}")
            return []

    def _match_zeroark(self, servers: list, map_name: str, known_ports: set = None, is_pure: bool = False) -> dict:
        """在 ZeroARK 服务器列表中匹配目标服务器（按精确度降序）：
        ① 地图 = 开服英文（get_map_std 规范名，如 ScorchedEarth）+ 直连端口 + 纯净前缀
        ② 地图 + 端口前缀（直连端口可能已变更，端口前缀仍可区分纯净/普通）
        ③ 仅直连端口命中
        ④ 仅地图命中（兜底）
        """
        std_map = get_map_std(map_name, "ASA").strip().lower()

        def _map_ok(s) -> bool:
            s_map = (s.get('map') or '').strip().lower()
            if not s_map:
                return False
            return s_map == std_map or std_map in s_map or s_map in std_map

        def _port_ok(s) -> bool:
            return bool(known_ports) and str(s.get('port', '')).strip() in known_ports

        def _prefix_ok(s) -> bool:
            port_str = str(s.get('port', '')).strip()
            if not port_str or not port_str.isdigit():
                return False
            return port_str.startswith("19" if is_pure else "18")

        # ① 最精确：地图 + 直连端口 + 纯净意图
        if known_ports:
            for s in servers:
                if _map_ok(s) and _port_ok(s) and _prefix_ok(s):
                    logger.info(f"✅ ARK Status 命中(地图+端口+纯净): {s.get('name')} map={s.get('map')} port={s.get('port')}")
                    return self._format_arkstatus(s)
        # ② 地图 + 纯净端口前缀（端口可能已变更，但前缀可区分纯净/普通）
        for s in servers:
            if _prefix_ok(s) and _map_ok(s):
                logger.info(f"✅ ARK Status 命中(地图+纯净端口): {s.get('name')} map={s.get('map')} port={s.get('port')}")
                return self._format_arkstatus(s)
        # ③ 直连端口命中（兜底）
        if known_ports:
            for s in servers:
                if _port_ok(s):
                    logger.info(f"✅ ARK Status 命中(仅端口): {s.get('name')} map={s.get('map')} port={s.get('port')}")
                    return self._format_arkstatus(s)
        # ④ 兜底：仅地图命中（无端口基准时）
        for s in servers:
            if _map_ok(s):
                logger.info(f"⚠️ ARK Status 命中(仅地图): {s.get('name')} map={s.get('map')} port={s.get('port')}")
                return self._format_arkstatus(s)
        return None

    async def _query_asa_arkstatus(self, map_name: str, known_ports: set = None, is_pure: bool = False) -> dict:
        """ARK Status API 查询 ZeroARK ASA 服务器（三重匹配：ZeroARK 关键词 + 开服英文地图 + 直连端口 + 纯净意图）"""
        servers = await self._fetch_zeroark_servers()
        if not servers:
            return None
        return self._match_zeroark(servers, map_name, known_ports, is_pure)

    async def _call_llm(self, user_message: str) -> str | None:
        """调用智谱 GLM（OpenAI 兼容接口）回复群消息，仅在 LLM 启用时有效；429/5xx 自动退避重试"""
        llm_enabled = self.config.get('llm_enabled', False)
        if not llm_enabled:
            return None
        api_url = self.config.get('llm_api_url', 'https://open.bigmodel.cn/api/paas/v4/chat/completions')
        api_key = self.config.get('llm_api_key', '')
        model = self.config.get('llm_model', 'GLM-4.7-Flash')
        system_prompt = self.config.get('llm_system_prompt', '你是一个方舟服务器查询助手。请简洁专业地回答，避免废话。')
        if not api_key:
            logger.warning("⚠️ LLM 未配置 API Key，无法调用 GLM")
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 512
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                resp = None
                for attempt in range(3):
                    resp = await client.post(api_url, headers=headers, json=payload)
                    # 限流/服务端繁忙：退避后重试
                    if resp.status_code == 429 or resp.status_code >= 500:
                        if attempt < 2:
                            wait = 2 + attempt * 2
                            logger.warning(f"⏳ LLM API 限流/繁忙 ({resp.status_code})，{wait}s 后重试（第 {attempt + 1}/3 次）")
                            await asyncio.sleep(wait)
                            continue
                    break
                if resp.status_code != 200:
                    logger.error(f"❌ LLM API 返回非 200: {resp.status_code} {resp.text[:200]}")
                    return None
                data = resp.json()
                if not data.get('choices'):
                    logger.error(f"❌ LLM 返回空 choices: {data}")
                    return None
                reply = data['choices'][0]['message']['content']
                logger.info(f"🤖 LLM 回复: {reply[:50]}...")
                return reply.strip()
        except Exception as e:
            logger.error(f"❌ LLM 调用失败: {e}")
            return None

    @staticmethod
    def _a2s_player_count(info) -> int:
        """兼容 python-a2s 字段改名：新版 player_count，旧版 players"""
        for attr in ('player_count', 'players'):
            v = getattr(info, attr, None)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return 0

    @staticmethod
    def _a2s_max_players(info) -> int:
        v = getattr(info, 'max_players', None)
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _a2s_player_names(players) -> list:
        """兼容玩家名字段差异（name / player_name）"""
        names = []
        for p in players or []:
            n = getattr(p, 'name', None) or getattr(p, 'player_name', None)
            if n:
                names.append(str(n))
        return names

    async def _query_ase_a2s(self, address: str, map_name: str, version: str = "ASE", lang: str = "zh") -> str:
        try:
            if ":" not in address:
                address += ":27015"
            host, port_str = address.split(":")
            port = int(port_str)
            # a2s 是同步阻塞调用（各 5 秒超时），必须丢进线程池，否则会卡住整个事件循环
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, lambda: a2s.info((host, port), timeout=5.0))
            try:
                players = await loop.run_in_executor(None, lambda: a2s.players((host, port), timeout=5.0))
                pnames = self._a2s_player_names(players)
                pcount = len(pnames)
            except Exception as e:
                logger.debug(f"A2S players 查询失败: {e}")
                pnames = []
                pcount = self._a2s_player_count(info)
            # A2S 拿不到玩家名单时，用 RCON listplayers 补全名单与人数
            # （注意：A2S 有时能报人数但拿不到名单，所以判断依据是“名单为空”）
            query_method = "A2S"
            if not pnames:
                rcount, rn = await self._get_players_via_rcon(version, map_name)
                if rn or (rcount and rcount > 0):
                    pnames = rn or []
                    pcount = rcount or pcount
                    query_method = "A2S + RCON玩家"
            map_display = get_map_display(info.map_name, version, lang)
            footer = FOOTER_ASE
            usage = self.usage_cache.get("ASE", "")
            lines = [
                f"🎮 服务器状态", f"📌 地址：{address}", f"🟢 状态：在线",
                f"🌐 地图：{map_display}", f"👥 在线人数：{pcount} / {self._a2s_max_players(info)}",
                f"🕹️ 服务器名称：ZeroARK-{map_name}{version}", f"📡 查询方式：{query_method}", "",
                "👥 在线玩家：", "  " + ("、".join(pnames[:20]) if pnames else "无"), "",
                "🔗 直连方式：", f"【控制台】open {address}（按 Tab 或 ~ 打开控制台）",
                "⚠️ 请使用游戏端口（ASE默认27015）"
            ]
            if usage:
                lines.extend(["", "📖 如何加入：", usage])
            lines.append(footer)
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 查询失败（A2S）：{str(e)}" + FOOTER_ASE

    async def _query_asa(self, map_name: str, lang: str = "zh") -> str:
        asa_map = self.map_cache.get("ASA", {})
        # ① 判断是否为 纯净查询（端口前缀：19xxx）
        is_pure = "纯净" in map_name
        expected_prefix = "19" if is_pure else "18"
        # ② 先精确匹配（优先，避免 fuzzy 误配）
        matched_key = None
        if map_name in asa_map:
            matched_key = map_name
        else:
            # Fuzzy 匹配：分纯净/非纯净两档，避免 孤岛 误配 纯净孤岛
            clean_query = re.sub(r'[（(][^）)]*[）)]', '', map_name).strip()
            key_is_pure = lambda k: "纯净" in re.sub(r'[（(][^）)]*[）)]', '', k).strip()
            # 先完全匹配（去括号后）
            for key in asa_map:
                clean_key = re.sub(r'[（(][^）)]*[）)]', '', key).strip()
                if clean_key == clean_query and key_is_pure(key) == is_pure:
                    matched_key = key
                    break
            # 再包含匹配（但必须纯净性一致）
            if not matched_key:
                for key in asa_map:
                    clean_key = re.sub(r'[（(][^）)]*[）)]', '', key).strip()
                    if key_is_pure(key) == is_pure and (clean_key == clean_query or clean_key in clean_query or clean_query in clean_key):
                        matched_key = key
                        break
        direct_addr = None
        known_ports = set()
        if matched_key:
            direct_addr = asa_map[matched_key][0]
            for a in asa_map[matched_key]:
                if ":" in a:
                    p = a.split(":")[-1]
                    if p.isdigit():
                        known_ports.add(p)
        std_map = get_map_std(map_name, "ASA")
        logger.info(f"ARK Status 查询: 关键词=ZeroARK, 地图(开服英文)={std_map}, 直连端口={known_ports}, 纯净意图={is_pure}")
        result = await self._query_asa_arkstatus(map_name, known_ports, is_pure)
        if result:
            port = str(result.get('port', ''))
            address = f"{result['ip']}:{port}"
            custom_name = result.get('name', f"ZeroARK-{map_name}ASA")
            map_display = get_map_display(result.get('map', 'unknown'), "ASA", lang)
            pcount = result.get('players', 0)
            maxp = result.get('max_players', 0)
            pnames = []
            query_method = "ARK Status API"
            # API 只给人数、不给名单：只要名单为空就用 RCON listplayers 补全
            if not pnames:
                rcount, rn = await self._get_players_via_rcon("ASA", map_name)
                if rn or (rcount and rcount > 0):
                    pnames = rn or []
                    pcount = rcount or pcount
                    query_method = "ARK Status API + RCON玩家"
            footer = FOOTER_ASA
            usage = self.usage_cache.get("ASA", "")
            player_line = "  " + ("、".join(pnames[:20]) if pnames else "无（RCON 未返回名单）")
            lines = [
                f"🎮 服务器状态", f"📌 地址：{address}", f"🟢 状态：在线",
                f"🌐 地图：{map_display}", f"👥 在线人数：{pcount} / {maxp or '?'}",
                f"🕹️ 服务器名称：{custom_name}", f"📡 查询方式：{query_method}", "📋 服务器类型：非官方",
                "", "👥 在线玩家：", player_line,
                "", "🔗 直连方式：", f"【控制台】open {address}（按 Tab 或 ~ 打开控制台）",
                "⚠️ 请使用游戏端口（ASA默认7777）"
            ]
            if usage:
                lines.extend(["", "📖 如何加入：", usage])
            lines.append(footer)
            return "\n".join(lines)
        # ---------- RCON 回退 ----------
        logger.info("ARK Status 未命中，回退到 RCON")
        rcon_asa = self.rcon_cache.get("ASA", {})
        if not rcon_asa:
            return f"❌ ARK Status 查询失败，且 RCON 地址列表为空" + FOOTER_ASA
        rcon_addr_list = None
        if matched_key and matched_key in rcon_asa:
            rcon_addr_list = rcon_asa[matched_key]
        else:
            key = _fuzzy_key(rcon_asa, map_name)
            rcon_addr_list = rcon_asa[key] if key else None
        if not rcon_addr_list:
            return f"❌ ARK Status 查询失败，且未在 RCON 列表中找到地图 '{map_name}'" + FOOTER_ASA
        rcon_addr = rcon_addr_list[0]
        if ":" not in rcon_addr:
            rcon_addr += ":7777"
        host, port_str = rcon_addr.split(":")
        try:
            port = int(port_str)
        except ValueError:
            return f"❌ RCON 列表里的地址格式异常：{rcon_addr}" + FOOTER_ASA
        rcon_result = await self._query_via_rcon(host, port)
        if not rcon_result:
            return f"❌ ARK Status 查询失败，RCON 也失败" + FOOTER_ASA
        # 直连地址没拿到就不展示地址 —— 绝不能用 RCON 端点冒充：那是内网地址 + RCON 端口，既误导又泄露
        display_addr = direct_addr or ''
        custom_name = rcon_result.get('server_name', f"ZeroARK-{map_name}ASA")
        rcon_map = rcon_result.get('map_name', '')
        map_display = get_map_display(rcon_map if rcon_map else map_name, "ASA", lang)
        pnames = rcon_result.get('player_names', [])
        pcount = rcon_result.get('player_count', 0)
        maxp = rcon_result.get('max_players', 0)
        footer = FOOTER_ASA
        usage = self.usage_cache.get("ASA", "")
        lines = [
            f"🎮 服务器状态",
            f"📌 地址：{display_addr}" if display_addr else "📌 地址：暂未取到直连地址（发 /更新地址 可刷新）",
            f"🟢 状态：在线",
            f"🌐 地图：{map_display}", f"👥 在线人数：{pcount} / {maxp or '?'}",
            f"🕹️ 服务器名称：{custom_name}", "📡 查询方式：RCON (ARK Status 回退)",
            "", "👥 在线玩家：", "  " + ("、".join(pnames[:20]) if pnames else "无"),
        ]
        if display_addr:
            lines += ["", "🔗 直连方式：", f"【控制台】open {display_addr}（按 Tab 或 ~ 打开控制台）",
                      "⚠️ 请使用游戏端口（ASA默认7777）"]
        if usage:
            lines.extend(["", "📖 如何加入：", usage])
        lines.append(footer)
        return "\n".join(lines)

    # ======================== 全服列表（/ase、/asa 不带地图名时使用） ========================
    # ======================== 在线玩家查询 ========================
    def _query_players_detail_sync(self, host: str, port: int):
        """RCON 查询在线玩家明细：{map_name, server_name, max_players, players:[{name,id}]}；失败返回 None"""
        if not self.rcon_password:
            return None
        try:
            with RconClient(host, port, passwd=self.rcon_password, timeout=self.config.get('rcon_timeout', 10.0)) as client:
                raw = client.run("listplayers")
                players = []
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    low = line.lower()
                    if 'no players' in low or low.startswith('players:'):
                        continue
                    m = re.match(r'^\d+\.\s*(.+)$', line)
                    body = m.group(1) if m else (line if ',' in line else '')
                    if not body:
                        continue
                    parts = [x.strip() for x in body.split(',')]
                    name = re.sub(r'\s*\([^)]*\)$', '', parts[0]).strip()
                    pid = parts[1] if len(parts) > 1 else ''
                    if name:
                        players.append({"name": name, "id": pid})

                info_raw = client.run("getserverinfo")
                info = {}
                for ln in info_raw.splitlines():
                    if ': ' in ln:
                        k, v = ln.split(': ', 1)
                        info[k.strip()] = v.strip()

                def _iget(*names, default=""):
                    for k, v in info.items():
                        kk = re.sub(r'[\s_\-]', '', str(k)).lower()
                        if kk in names:
                            return v
                    return default

                try:
                    maxp = int(_iget('maxplayers', 'maxplayer', default='0'))
                except (TypeError, ValueError):
                    maxp = 0
                return {
                    "map_name": _iget('map', 'mapname', default='') or '',
                    "server_name": _iget('servername', 'name', default='') or '',
                    "max_players": maxp,
                    "players": players,
                }
        except Exception as e:
            logger.debug(f"RCON 玩家明细查询失败 {host}:{port}: {type(e).__name__}: {e}")
            return None

    async def _query_players_detail(self, host: str, port: int):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._query_players_detail_sync, host, port)

    async def _lookup_tribe(self, game: str, pid: str, cache: dict):
        """按玩家ID在聊天库里查最近一条记录，取部落名/地图/时间（RCON 不提供部落信息）"""
        if not pid:
            return None
        key = (game, pid)
        if key in cache:
            return cache[key]
        cache[key] = None
        src_id = 'asa_chat' if game == 'ASA' else 'ase_chat'
        src = next((s for s in (self.config.get('db_sources') or []) if s.get('id') == src_id), None)
        if not src:
            return None
        col = 'EOSid' if game == 'ASA' else 'SteamId'
        conn = None
        try:
            conn = await aiomysql.connect(
                host=src.get('host'), port=int(src.get('port', 3306)),
                user=src.get('user'), password=src.get('password'),
                db=src.get('database'), charset='utf8mb4', autocommit=True, connect_timeout=5)
            cur = await conn.cursor()
            tbl = src.get('table', 'cross_chat')
            await cur.execute(
                f"SELECT Sender, TribeName, Map, timestamp FROM `{tbl}` WHERE `{col}`=%s ORDER BY Id DESC LIMIT 1",
                (pid,))
            row = await cur.fetchone()
            # 最近一条可能没写部落名（旧行/空值）→ 再往前找最近一条有部落名的
            if row and not (row[1] or '').strip():
                await cur.execute(
                    f"SELECT Sender, TribeName, Map, timestamp FROM `{tbl}` "
                    f"WHERE `{col}`=%s AND TribeName IS NOT NULL AND TribeName<>'' ORDER BY Id DESC LIMIT 1",
                    (pid,))
                row2 = await cur.fetchone()
                if row2:
                    row = (row[0], row2[1], row[2] or row2[2], row[3])
            await cur.close()
            if row:
                cache[key] = {"sender": row[0], "tribe": row[1] or '', "map": row[2] or '', "time": row[3]}
        except Exception as e:
            logger.debug(f"部落信息查询失败 {game}/{pid}: {type(e).__name__}: {e}")
        finally:
            if conn is not None:
                try:
                    await conn.ensure_closed()
                except Exception:
                    pass
        return cache[key]

    async def _players_cmd(self, event):
        """在线玩家查询：不指定版本=同时查进化+飞升；指定版本/地图则只查该范围"""
        if not self._check_whitelist(event):
            return
        parts = event.message_str.strip().split()
        version = self._parse_game(parts[1]) if len(parts) >= 2 else ''
        if version:
            map_query = parts[2].strip() if len(parts) >= 3 else ''
            games = [version]
        else:
            map_query = parts[1].strip() if len(parts) >= 2 else ''
            games = ['ASE', 'ASA']

        jobs = []       # (game, map_key, addr)
        missing = []    # 指定了地图但该版本没有对应 RCON 地址
        for g in games:
            rv = self.rcon_cache.get(g, {}) or {}
            if map_query:
                key = _fuzzy_key(rv, map_query)
                if key and rv.get(key):
                    jobs.append((g, key, rv[key][0]))
                else:
                    missing.append(g)
            else:
                for k, v in rv.items():
                    if v:
                        jobs.append((g, k, v[0]))

        if not jobs:
            if map_query:
                yield event.plain_result(f"❌ 未找到地图「{map_query}」的 RCON 地址（进化/飞升均未命中，可先 /更新地址）")
            else:
                yield event.plain_result("❌ 暂无 RCON 地址，请先执行 /更新地址")
            return

        async def probe(game, k, addr):
            if ':' not in addr:
                return game, k, addr, None
            h, p = addr.split(':')
            try:
                res = await asyncio.wait_for(self._query_players_detail(h, int(p)), timeout=8.0)
            except Exception:
                res = None
            return game, k, addr, res

        results = await asyncio.gather(*(probe(g, k, a) for g, k, a in jobs))
        cache = {}
        title = self._game_cn(games[0]) if len(games) == 1 else "进化 + 飞升"
        lines = [f"🎮 在线玩家（{title}）"]
        total_all = 0
        for g in games:
            group = [r for r in results if r[0] == g]
            if not group:
                if g in missing:
                    lines.append("")
                    lines.append(f"━━ 【{self._game_cn(g)}】 ━━")
                    lines.append(f"  ❌ 未找到地图「{map_query}」")
                continue
            lines.append("")
            lines.append(f"━━ 【{self._game_cn(g)}】 ━━")
            gcount = 0
            offline = []
            for _, k, addr, res in group:
                if not res:
                    offline.append(k)
                    continue
                players = res.get("players") or []
                if not players:
                    continue
                gcount += len(players)
                lines.append(f"【{k}】{len(players)} 人在线")
                for i, pl in enumerate(players, 1):
                    pid = str(pl.get('id') or '')
                    if g == 'ASA':
                        pid = pid.lower()
                    info = await self._lookup_tribe(g, pid, cache) or {}
                    tribe = info.get('tribe') or ''
                    lastmap = info.get('map') or ''
                    bits = [f"部落：{tribe}" if tribe else "部落：未知"]
                    if lastmap:
                        bits.append(f"最近活动：{lastmap}")
                    mark = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"[i - 1] if 1 <= i <= 20 else f"{i}."
                    pid_show = self._mask_id(pid) if self.config.get('mask_player_ids', True) else pid
                    lines.append(f"  {mark} {pl.get('name')}  |  " + " | ".join(bits)
                                 + (f"  |  ID {pid_show}" if pid else ""))
            if gcount == 0:
                lines.append("  （当前没有在线玩家）")
            if offline:
                lines.append(f"⚠️ 未响应/无权限：{'、'.join(offline)}")
            total_all += gcount
        lines.append("")
        lines.append("💡 用法：/在线玩家 [进化|飞升] [地图名]（不给版本=同时查进化+飞升）")
        yield event.plain_result("\n".join(lines) + self.footer)

    @filter.command("在线玩家")
    async def players_command_cn(self, event):
        async for r in self._players_cmd(event):
            yield r

    @filter.command("在线")
    async def players_command_cn2(self, event):
        async for r in self._players_cmd(event):
            yield r

    @filter.command("players")
    async def players_command_en(self, event):
        async for r in self._players_cmd(event):
            yield r

    @filter.command("谁在线")
    async def players_command_cn3(self, event):
        async for r in self._players_cmd(event):
            yield r

    async def _list_ase_servers(self, lang: str = "zh") -> str:
        """列出所有进化（ASE）服务器及在线状态"""
        ase_map = self.map_cache.get("ASE", {})
        if not ase_map:
            return "⚠️ ASE 服务器列表为空，请先执行 /更新地址 刷新" + self.footer
        lines = ["🎮 【进化 ASE】全部服务器列表", ""]
        loop = asyncio.get_running_loop()

        async def query_one(name: str, addrs: list) -> str:
            display_name = get_map_display(name, "ASE", lang)
            addr = addrs[0] if addrs else ""
            if not addr:
                return f"  ❓ {display_name}：无地址"
            if ":" not in addr:
                addr += ":27015"
            host, port_str = addr.split(":")
            try:
                info = await loop.run_in_executor(None, lambda: a2s.info((host, int(port_str)), timeout=5.0))
                return (f"  🟢 {display_name}：{self._a2s_player_count(info)}/"
                        f"{self._a2s_max_players(info)} 人在线 | {addr}")
            except Exception as e:
                logger.debug(f"A2S 查询失败 {display_name} ({addr}): {type(e).__name__}: {e}")
            # A2S 不可用（查询端口不通/超时/字段差异）→ 回退 RCON，避免把在线服误判为离线
            if self.config.get('list_rcon_fallback', True):
                rcon_addr = None
                rv = self.rcon_cache.get("ASE", {}) or {}
                if rv.get(name):
                    rcon_addr = rv[name][0]
                else:
                    for k in rv:
                        if name in k or k in name:
                            rcon_addr = rv[k][0]
                            break
                if rcon_addr:
                    if ":" not in rcon_addr:
                        rcon_addr += ":7777"
                    try:
                        rh, rp = rcon_addr.split(":")
                        res = await self._query_via_rcon(rh, int(rp))
                        if res:
                            return (f"  🟢 {display_name}：{res.get('player_count', 0)}/"
                                    f"{res.get('max_players') or '?'} 人在线（RCON） | {addr}")
                    except Exception as e:
                        logger.debug(f"RCON 回退失败 {display_name}: {type(e).__name__}: {e}")
            return f"  🔴 {display_name}：离线 | {addr}"

        results = await asyncio.gather(*[query_one(n, a) for n, a in ase_map.items()])
        lines.extend(results)
        lines.append("")
        lines.append("💡 单服详情：/ase 或 /进化 <地图名>")
        lines.append(self.footer)
        return "\n".join(lines)

    async def _list_asa_servers(self, lang: str = "zh") -> str:
        """列出所有飞升（ASA）服务器及在线状态（ARK Status API，单次 ZeroARK 搜索 + 逐图匹配）"""
        asa_map = self.map_cache.get("ASA", {})
        if not asa_map:
            return "⚠️ ASA 服务器列表为空，请先执行 /更新地址 刷新" + self.footer
        lines = ["🎮 【飞升 ASA】全部服务器列表", ""]
        servers = await self._fetch_zeroark_servers()

        def _ports_of(addrs):
            ps = set()
            for a in addrs or []:
                if ":" in a:
                    p = a.split(":")[-1]
                    if p.isdigit():
                        ps.add(p)
            return ps

        entries = []
        for name, addrs in asa_map.items():
            is_pure = "纯净" in name
            entries.append({
                "name": name,
                "display": get_map_display(name, "ASA", lang),
                "addr": addrs[0] if addrs else "",
                "match": self._match_zeroark(servers, name, _ports_of(addrs), is_pure) if servers else None,
            })

        async def rcon_count(name):
            """RCON 补全某张图的在线人数（ARK Status 未命中/人数为0 时用），返回 (人数, 上限) 或 None"""
            rv = self.rcon_cache.get("ASA", {}) or {}
            rcon_addr = rv[name][0] if rv.get(name) else None
            if not rcon_addr:
                for k in rv:
                    if name in k or k in name:
                        rcon_addr = rv[k][0]
                        break
            if not rcon_addr:
                return None
            if ":" not in rcon_addr:
                rcon_addr += ":7777"
            try:
                rh, rp = rcon_addr.split(":")
                res = await self._query_via_rcon(rh, int(rp))
                if res:
                    return res.get('player_count', 0), res.get('max_players', 0)
            except Exception as e:
                logger.debug(f"ASA RCON 补全失败 {name}: {type(e).__name__}: {e}")
            return None

        need = [e for e in entries if (not e["match"]) or not e["match"].get("players")]
        if need and self.config.get('list_rcon_fallback', True):
            probed = await asyncio.gather(*(rcon_count(e["name"]) for e in need))
            fallback = {e["name"]: r for e, r in zip(need, probed)}
        else:
            fallback = {}

        for e in entries:
            m = e["match"]
            addr = e["addr"] if e["addr"] else "无地址"
            if m and m.get("players"):
                lines.append(f"  🟢 {e['display']}：{m.get('players', 0)}/{m.get('max_players', 0)} 人在线 | {m.get('ip')}:{m.get('port')}")
                continue
            fb = fallback.get(e["name"])
            if fb:
                # 飞升 RCON getserverinfo 常不返回人数上限：优先用 ARK Status 已匹配到的 max_players
                mp = (m.get('max_players') if m else 0) or fb[1] or '?'
                lines.append(f"  🟢 {e['display']}：{fb[0]}/{mp} 人在线（RCON） | {addr}")
                continue
            if m:
                lines.append(f"  🟢 {e['display']}：0/{m.get('max_players', 0)} 人在线 | {m.get('ip')}:{m.get('port')}")
            else:
                lines.append(f"  🔴 {e['display']}：离线/未知 | {addr}")
        lines.append("")
        lines.append("💡 单服详情：/asa 或 /飞升 <地图名>")
        lines.append(self.footer)
        return "\n".join(lines)

    @staticmethod
    def _event_group_id(event):
        """解析事件所在群号（兼容各适配器：get_group_id / group_id 属性 / message_obj / session_id）；
        私聊或无法确定时返回 None。注意：部分环境事件没有 group_id 属性，务必用此方法判断群聊/私聊。"""
        try:
            g = event.get_group_id()
            if g:
                return g
        except Exception:
            pass
        try:
            g = getattr(event, 'group_id', None)
            if g:
                return g
        except Exception:
            pass
        try:
            g = getattr(event.message_obj, 'group_id', None)
            if g:
                return g
        except Exception:
            pass
        try:
            m = re.search(r'group_?(\d+)', str(event.session_id))
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return None

    def _owner_ids(self) -> set:
        """主人 ID 集合：owner_qq + owner_ids（跨平台混用，QQ openid / KOOK 用户ID 均可）"""
        ids = set()
        main = str(self.config.get('owner_qq', '') or '').strip()
        if main:
            ids.add(main)
        extra = self.config.get('owner_ids') or []
        if isinstance(extra, (list, tuple)):
            for x in extra:
                s = str(x or '').strip()
                if s:
                    ids.add(s)
        return ids

    def _is_owner(self, event) -> bool:
        """判断发送者是否为主人（兼容各适配器的 ID 取法与 session 兜底）"""
        ids = self._owner_ids()
        if not ids:
            return False
        cands = []
        try:
            sid = str(event.get_sender_id() or '')
            if sid:
                cands.append(sid)
        except Exception:
            pass
        try:
            for tok in re.split(r'[_\s]', str(event.get_session_id() or '')):
                if tok.isdigit() and len(tok) >= 5:
                    cands.append(tok)
        except Exception:
            pass
        return any(c in ids for c in cands)

    def _admin_channels(self) -> set:
        """允许主人看到完整帮助的群/频道标识集合"""
        raw = self.config.get('admin_channels') or []
        if not isinstance(raw, (list, tuple)):
            return set()
        return {str(x).strip() for x in raw if str(x).strip()}

    def _check_whitelist(self, event: AstrMessageEvent) -> bool:
        """白名单检查：主人（owner_qq/owner_ids）任何场景放行；私聊放行；群聊按白名单"""
        # 主人在任何场景（含私聊）都可使用全部指令
        if self._is_owner(event):
            return True

        whitelist = self.config.get('whitelist_groups', [])
        if not whitelist:
            return True

        # 提取 group_id（私聊时为空/0/None）
        group_id = None
        if hasattr(event, 'group_id') and event.group_id:
            group_id = event.group_id
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id') and event.message_obj.group_id:
            group_id = event.message_obj.group_id
        elif hasattr(event, 'session_id'):
            m = re.search(r'group_(\d+)', event.session_id)
            if m:
                group_id = int(m.group(1))

        if not group_id:
            return True  # 私聊或无法获取 group_id 则放行

        return str(group_id) in [str(g) for g in whitelist]

    @filter.command("rcon")
    async def private_rcon_command(self, event: AstrMessageEvent):
        # 仅限私聊使用：能解析到群号即拦截（群聊不执行管理命令）
        if self._event_group_id(event):
            return
        sender_id = event.get_sender_id()
        if not sender_id:
            sid = event.get_session_id()
            if sid and '_' in sid:
                parts = sid.split('_')
                if len(parts) > 1 and parts[1].isdigit():
                    sender_id = parts[1]
        if not self._is_owner(event):
            return
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield event.plain_result("用法：\n"
                                     "1. /rcon <ASE|ASA> <命令>             对该版本全部服务器执行\n"
                                     "   例：/rcon ASE ArkShop.Reload\n"
                                     "2. /rcon <ASE|ASA> <地图名> <命令>     对指定地图那一台服务器执行\n"
                                     "   例：/rcon ASE 孤岛 listplayers\n"
                                     "3. /rcon <目标名> <命令>              对指定 RCON 目标执行\n"
                                     "   例：/rcon ASE-孤岛 listplayers")
            return

        async def _run(targets, command):
            loop = asyncio.get_running_loop()
            results = []
            for t in targets:
                host, port = t.get('host'), t.get('port')
                if host and port:
                    out = await loop.run_in_executor(None, self._execute_rcon_command_sync, host, port, command)
                    results.append(f"【{t.get('name', '未知')}】\n{out}")
            return results

        first = parts[1].upper()
        if first in ("ASE", "ASA"):
            version = first
            # 4 段及以上：先尝试 “版本 + 地图名 + 命令”（对那一台执行）
            if len(parts) >= 4:
                map_name = parts[2]
                addr_list = self.rcon_cache.get(version, {}).get(map_name)
                if not addr_list:
                    for key in self.rcon_cache.get(version, {}):
                        if map_name in key or key in map_name:
                            addr_list = self.rcon_cache[version][key]
                            break
                if addr_list:
                    command = " ".join(parts[3:])
                    if not command:
                        yield event.plain_result("❌ 命令不能为空")
                        return
                    rcon_addr = addr_list[0]
                    if ":" not in rcon_addr:
                        yield event.plain_result("❌ RCON 地址格式错误")
                        return
                    host, port_str = rcon_addr.split(":")
                    port = int(port_str)
                    out = await asyncio.get_running_loop().run_in_executor(None, self._execute_rcon_command_sync, host, port, command)
                    yield event.plain_result(f"📡 RCON 执行结果 ({version}-{map_name}):\n{out}")
                    return
            # 否则：/rcon <版本> <命令...> → 只对该版本全部服务器执行（绝不跨到另一版本）
            command = " ".join(parts[2:])
            if not command:
                yield event.plain_result("❌ 命令不能为空")
                return
            targets = [t for t in self.rcon_targets
                       if str(t.get('name', '')).startswith(version + "-") and t.get('host') and t.get('port')]
            if not targets:
                yield event.plain_result(f"❌ {version} 没有可用的 RCON 目标")
                return
            results = await _run(targets, command)
            yield event.plain_result(f"📡 RCON 执行结果（{version} 全部 {len(targets)} 台）:\n" + "\n\n".join(results))
            return

        # 指定目标名：/rcon <目标名> <命令>
        for t in self.rcon_targets:
            if t.get('name') == parts[1]:
                command = " ".join(parts[2:])
                if not command:
                    yield event.plain_result("❌ 命令不能为空")
                    return
                host, port = t.get('host'), t.get('port')
                if not (host and port):
                    yield event.plain_result(f"❌ 目标 '{t.get('name')}' 缺少地址")
                    return
                out = await asyncio.get_running_loop().run_in_executor(None, self._execute_rcon_command_sync, host, port, command)
                yield event.plain_result(f"📡 RCON 执行结果 ({self._target_label(t.get('name'))}):\n{out}")
                return
        # 裸命令且无法识别版本/目标：拒绝执行（防止误广播到全部服务器）
        yield event.plain_result("❌ 无法识别版本或目标，未执行任何命令（避免误发全部服务器）。\n请按上方用法指定 ASE/ASA 版本或具体目标名。")

    async def _owner_addpoints_cmd(self, event):
        """私聊 owner 专用：给玩家加 ArkShop 点数。
        只对该版本“一台在线服务器”执行一次 AddPoints，绝不广播，从机制上避免重复加点。"""
        # 仅限私聊
        if self._event_group_id(event):
            return
        sender_id = event.get_sender_id()
        if not sender_id:
            sid = event.get_session_id()
            if sid and '_' in sid:
                sp = sid.split('_')
                if len(sp) > 1 and sp[1].isdigit():
                    sender_id = sp[1]
        if not self._is_owner(event):
            return
        parts = event.message_str.strip().split()
        if len(parts) < 4:
            yield event.plain_result("用法：/加点 <进化|飞升> <ID> <点数>\n"
                                     "  例：/加点 飞升 <EOS 32位hex> 5\n"
                                     "  例：/加点 进化 <SteamID64 17位数字> 500\n"
                                     "说明：只对该版本一台在线服务器执行一次 AddPoints，绝不广播避免重复加点；加点后自动回读 GetPlayerPoints 确认到账。")
            return
        game = self._parse_game(parts[1])
        if not game:
            yield event.plain_result("❌ 版本需为 进化(ASE) 或 飞升(ASA)")
            return
        pid = parts[2].strip()
        try:
            points = int(parts[3])
        except ValueError:
            yield event.plain_result("❌ 点数必须是整数")
            return
        if points < 0:
            yield event.plain_result("❌ 想扣点请用 /rcon 执行 ChangePoints <ID> -<点数>（/加点仅支持正数）")
            return
        if not self._is_valid_id(game, pid):
            yield event.plain_result(f"❌ {self._game_cn(game)} ID 格式不正确：\n"
                                     f"  进化=SteamID64 17位数字（7656119开头）\n"
                                     f"  飞升=EOS 32位hex")
            return
        if game == 'ASA':
            pid = pid.lower()
        target = await self._pick_online_rcon_target(game)
        if not target:
            yield event.plain_result(f"❌ {self._game_cn(game)}当前没有在线服务器，加点未执行，请稍后重试")
            return
        cfg = self._signin_cfg()
        cmd_tpl = cfg.get('ase_cmd' if game == 'ASE' else 'asa_cmd') or 'AddPoints {id} {points}'
        command = cmd_tpl.format(id=pid, points=points)
        out = await self._exec_addpoints(target, command)
        low = out.lower()
        if out.startswith("❌") or "unknown" in low or "not found" in low:
            yield event.plain_result(f"❌ 加点命令执行异常（{out[:100]}），未加点")
            return
        logger.info(f"✅ 管理员加点: game={game} id={pid} +{points} server={target.get('name')} resp={out[:60]}")
        verify = await self._getpoints_text(target, pid) if cfg.get('verify_with_getpoints', True) else ""
        yield event.plain_result(f"✅ 已在 {self._target_label(target.get('name'))} 为{self._game_cn(game)}玩家 {pid} 加点 +{points}{verify}")

    @filter.command("addpoints")
    async def owner_addpoints_command(self, event: AstrMessageEvent):
        async for r in self._owner_addpoints_cmd(event):
            yield r

    @filter.command("加点")
    async def owner_addpoints_command_cn(self, event: AstrMessageEvent):
        async for r in self._owner_addpoints_cmd(event):
            yield r

    @filter.command("arkshop")
    async def owner_arkshop_command(self, event: AstrMessageEvent):
        async for r in self._owner_addpoints_cmd(event):
            yield r

    def _extract_at_qqs(self, event) -> list:
        """提取消息中被 @ 的 QQ 列表：兼容 AstrBot At 段对象、OneBot 原始 dict、CQ码、[At:QQ]、@QQ 等，深度扫描去重"""
        qqs = []
        seen = set()

        def add(q):
            s = str(q).strip()
            ok = (s.isdigit() and len(s) >= 5) or bool(re.fullmatch(r'[A-Za-z0-9_\-]{6,}', s))
            if ok and s not in seen:
                seen.add(s)
                qqs.append(s)

        def scan(obj, depth=0):
            if depth > 6 or obj is None:
                return
            if isinstance(obj, dict):
                typ = str(obj.get('type') or '').lower()
                if typ.startswith('at') and typ != 'atall':
                    for k in ('qq', 'user_id'):
                        v = obj.get(k)
                        if v is not None:
                            add(v)
                    data = obj.get('data')
                    if isinstance(data, dict):
                        for k in ('qq', 'user_id'):
                            if data.get(k) is not None:
                                add(data[k])
                    return
                for v in list(obj.values())[:40]:
                    scan(v, depth + 1)
                return
            if isinstance(obj, (list, tuple, set)):
                for it in list(obj)[:100]:
                    scan(it, depth + 1)
                return
            name = obj.__class__.__name__.lower()
            if name == 'atall':
                return
            if name == 'at' or hasattr(obj, 'qq'):
                q = getattr(obj, 'qq', None)
                if q is not None:
                    add(q)
                d = getattr(obj, 'data', None)
                if d is not None:
                    scan(d, depth + 1)
                return
            for attr in ('segments', 'chain', 'message'):
                try:
                    v = getattr(obj, attr)
                    if isinstance(v, (list, tuple)):
                        scan(v, depth + 1)
                except Exception:
                    pass
            try:
                for k, v in list(vars(obj).items()):
                    if k in ('qq', 'user_id'):
                        add(v)
            except Exception:
                pass

        try:
            mo = event.message_obj
        except Exception:
            mo = None
        if mo is not None:
            scan(mo)
        try:
            text = str(getattr(event, 'message_str', '') or '')
        except Exception:
            text = ''
        for m in re.finditer(r'\[CQ:at,qq=(\d+)\]|\[At:(\d+)\]|\[at:(\d+)\]|@(\d{5,12})', text):
            s = next((m.group(i) for i in range(1, 5) if m.group(i)), None)
            if s:
                add(s)
        return qqs

    async def _owner_group_atpoints_cmd(self, event):
        """群聊 Owner 专用：@ 已绑定的群友 → 帮其加 ArkShop 点数（只限绑定过该游戏的 QQ，未绑定者跳过）"""
        # 仅群聊
        if not self._event_group_id(event):
            yield event.plain_result("此指令用于群聊：/代加点 <进化|飞升> <点数> @群友…")
            return
        qq = self._sender_qq(event)
        if not qq or not self._is_owner(event):
            return
        text = re.sub(r'\[CQ:[^\]]*\]', '', str(event.message_str or ''))
        tokens = text.split()
        if len(tokens) < 3:
            yield event.plain_result("用法：/代加点 <进化|飞升> <点数> @群友1 @群友2…\n"
                                     "  例：/代加点 飞升 5 @小明 @小红\n"
                                     "  例：/代加点 进化 500 @小明\n"
                                     "说明：只给【已绑定该游戏】的群友加点；每个目标在单台在线服执行一次 AddPoints，绝不广播。")
            return
        game = self._parse_game(tokens[1])
        if not game:
            yield event.plain_result("❌ 版本需为 进化(ASE) 或 飞升(ASA)")
            return
        try:
            points = int(tokens[2])
        except ValueError:
            yield event.plain_result("❌ 点数必须是整数")
            return
        if points < 0:
            yield event.plain_result("❌ 点数须为非负整数")
            return
        targets = self._extract_at_qqs(event)
        # 兜底：@ 解析不出时，允许直接写 QQ 号（指令第 4 个 token 起，形如“/代加点 进化 500 2753038913”）
        if not targets:
            for tok in tokens[3:]:
                tok_clean = re.sub(r'^@', '', tok.strip())
                if (tok_clean.isdigit() and len(tok_clean) >= 5) or re.fullmatch(r'[A-Za-z0-9_\-]{6,}', tok_clean):
                    targets.append(tok_clean)
            targets = list(dict.fromkeys(targets))
        if not targets:
            yield event.plain_result("❌ 没有识别到目标。请用：/代加点 <进化|飞升> <点数> @群友…\n"
                                     "或直接写 QQ 号：/代加点 <进化|飞升> <点数> <QQ号>")
            return
        try:
            self_id = str(event.get_self_id())
        except Exception:
            self_id = ''
        targets = [t for t in targets if t != self_id]
        cn = self._game_cn(game)
        # 该版本选一台在线服务器即可，多个目标共用同一台
        online = await self._pick_online_rcon_target(game)
        cfg = self._signin_cfg()
        cmd_tpl = cfg.get('ase_cmd' if game == 'ASE' else 'asa_cmd') or 'AddPoints {id} {points}'
        results = []
        for tqq in targets:
            try:
                binds = await self._get_bindings(tqq)
            except Exception as e:
                logger.error(f"代加点查询绑定失败: qq={tqq}: {e}")
                results.append(f"❌ @{self._mask_id(tqq)}：查询绑定失败，跳过")
                continue
            row = binds.get(game)
            if not row:
                results.append(f"⏭️ @{self._mask_id(tqq)}：未绑定{cn}，已跳过")
                continue
            pid = row['player_id']
            if not online:
                results.append(f"❌ @{self._mask_id(tqq)}：{cn}当前无在线服务器，未加点")
                continue
            command = cmd_tpl.format(id=pid, points=points)
            out = await self._exec_addpoints(online, command)
            low = out.lower()
            if out.startswith("❌") or "unknown" in low or "not found" in low:
                logger.error(f"代加点失败: qq={tqq} game={game} cmd={command} resp={out}")
                results.append(f"❌ @{self._mask_id(tqq)}：加点命令执行异常（{out[:60]}），未加点")
                continue
            logger.info(f"✅ 群聊代加点: 由owner为 qq={tqq} game={game} +{points} server={online.get('name')}")
            verify = await self._getpoints_text(online, pid) if cfg.get('verify_with_getpoints', True) else ""
            role = f"（{row['player_name']}）" if row.get('player_name') else ""
            results.append(f"✅ @{self._mask_id(tqq)}{role}：{cn} +{points} 已完成（{self._target_label(online.get('name'))}）{verify}")
        if not results:
            yield event.plain_result("⚠️ 没有可处理的目标")
            return
        yield event.plain_result("\n".join(results))

    @filter.command("代加点")
    async def owner_group_atpoints_cn(self, event: AstrMessageEvent):
        async for r in self._owner_group_atpoints_cmd(event):
            yield r

    @filter.command("atpoints")
    async def owner_group_atpoints_command(self, event: AstrMessageEvent):
        async for r in self._owner_group_atpoints_cmd(event):
            yield r

    @filter.command("帮加")
    async def owner_group_help_add(self, event: AstrMessageEvent):
        async for r in self._owner_group_atpoints_cmd(event):
            yield r

    async def _whoami_cmd(self, event):
        """显示当前会话的平台标识（openid/QQ号、群标识），用于填写 owner_qq / 白名单 / 通知群。
        不校验白名单：迁移期必须保证任何群/私聊都能拿到自己的 openid。"""
        try:
            sender = event.get_sender_id()
        except Exception:
            sender = None
        try:
            session_id = event.get_session_id()
        except Exception:
            session_id = ''
        try:
            platform_name = event.get_platform_name()
        except Exception:
            platform_name = ''
        # 原始 payload 里的 openid（QQ 官方机器人群消息可能同时带 member_openid 与 user_openid）
        raw_member = raw_user = ''
        try:
            raw = getattr(event.message_obj, 'raw_message', None)
            author = getattr(raw, 'author', None)
            raw_member = str(getattr(author, 'member_openid', '') or '')
            raw_user = str(getattr(author, 'user_openid', '') or '')
        except Exception:
            pass
        group = self._event_group_id(event)
        masked = bool(group)   # 群/频道属公共区域：ID 打码，私聊给全量
        lines = [
            "🪪 会话标识（用于 config.json 配置）",
            f"· 平台：{platform_name or '(未知)'}",
            f"· 你的ID（openid/QQ号）：{self._mask_id(sender) if masked else sender}",
            f"· 会话ID：{session_id}",
            f"· 群/频道标识：{group or '（私聊）'}",
            f"· member_openid：{self._mask_id(raw_member) if (masked and raw_member) else (raw_member or '（无）')}",
            f"· user_openid：{self._mask_id(raw_user) if (masked and raw_user) else (raw_user or '（无）')}",
            "",
            "对照填写：你的ID → owner_qq / owner_ids；群标识 → whitelist_groups / notify_group / admin_channels；",
            "玩家绑定主键即「你的ID」（QQ 官方机器人下为 openid，无法换成真实 QQ 号）。",
        ]
        if masked:
            lines += ["🔒 公共区域已对你的 ID 打码；需要完整 ID 请私聊机器人再发 /我是谁。"]
        yield event.plain_result("\n".join(lines))

    async def _status_cmd(self, event):
        """查看各服务器在线/离线一览"""
        if not self._check_whitelist(event):
            return
        yield event.plain_result(self._status_summary())

    @filter.command("状态")
    async def status_cmd_cn(self, event: AstrMessageEvent):
        async for r in self._status_cmd(event):
            yield r

    @filter.command("serverstatus")
    async def status_cmd_en(self, event: AstrMessageEvent):
        async for r in self._status_cmd(event):
            yield r

    async def _test_push_cmd(self, event):
        """Owner 专用：让机器人在通知群主动发一条消息，验证官方机器人的主动发言权限/配额"""
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq or not self._is_owner(event):
            return
        targets = self._broadcast_targets()
        if not targets:
            yield event.plain_result("❌ 未配置 broadcast_targets / notify_group")
            return
        names = [t['label'] or self._target_key(t['platform'], t['id']) for t in targets]
        sent_n = await self._broadcast("🔔 测试推送：机器人主动消息通道正常（此消息为主动发送）")
        if sent_n >= len(targets):
            yield event.plain_result(f"✅ 已向 {sent_n} 个目标发送测试推送：{'、'.join(names)}")
        elif sent_n:
            yield event.plain_result(f"⚠️ 仅 {sent_n}/{len(targets)} 个目标成功：{'、'.join(names)}\n请看日志确认失败的平台")
        else:
            yield event.plain_result("❌ 测试推送全部失败，请看日志（可能触发了主动消息配额/权限限制）")

    @filter.command("测试推送")
    async def test_push_cmd_cn(self, event: AstrMessageEvent):
        async for r in self._test_push_cmd(event):
            yield r

    @filter.command("testpush")
    async def test_push_cmd_en(self, event: AstrMessageEvent):
        async for r in self._test_push_cmd(event):
            yield r

    @filter.command("whoami")
    async def whoami_command(self, event: AstrMessageEvent):
        async for r in self._whoami_cmd(event):
            yield r

    @filter.command("我是谁")
    async def whoami_command_cn(self, event: AstrMessageEvent):
        async for r in self._whoami_cmd(event):
            yield r

    async def _myid_cmd(self, event):
        """查自己的身份 ID（用于 /关联 打通多平台、以及与客服核对身份；绑定游戏账号请用 /绑定 <游戏> <ID>）"""
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq:
            yield event.plain_result("❌ 无法获取你的身份 ID，请确认适配器")
            return
        plat = self._event_platform(event) or '未知平台'
        own_id = str(qq)
        main_id = str(await self._resolve_identity(qq) or '')
        linked = bool(main_id) and main_id != own_id
        # 公共区域（群/频道）一律打码，与 /我是谁 保持一致；完整 ID 只在私聊给。
        # 例外：QQ 官方个人认证**没有私聊**（平台限制），群里也打码的话玩家就永远看不到自己的 ID → 这种情况如实给全。
        plat_now = (self._event_platform(event) or '')
        in_group_now = bool(self._event_group_id(event))
        no_dm = plat_now == 'qq_official'
        masked = in_group_now and not no_dm
        lines = [
            f"🆔 你的 {plat} 身份 ID：",
            self._mask_id(own_id) if masked else own_id,
        ]
        if linked:
            lines += [
                f"🔗 已关联到主身份：{self._mask_id(main_id) if masked else main_id}（两边共用绑定与签到）",
            ]
        lines += [
            "",
            "这串 ID 的用途：",
            "· /关联 开码 → 在另一个平台发 /关联 <码>，把 QQ 与 KOOK 打通",
            "· 排查绑定/签到问题时给管理员核对身份",
            "",
            self.config.get('id_source_hint')
            or "绑定游戏账号：/绑定 飞升 <EOS 32位ID>（游戏里打开 ArkShop 商店能看到）或 /绑定 进化 <SteamID64>",
            "",
            "🔒 这串 ID 等于你的身份凭证，别发给别人。",
        ]
        if masked:
            lines += ["（公共区域已打码；要看完整的请私聊机器人再发 /我的ID，或找管理员核对）"]
        elif in_group_now and no_dm:
            lines += ["（QQ 个人认证机器人没有私聊功能，所以这里直接给完整 ID；请勿外传）"]
        yield event.plain_result("\n".join(lines))

    @filter.command("我的ID")
    async def myid_cmd_cn(self, event: AstrMessageEvent):
        async for r in self._myid_cmd(event):
            yield r

    @filter.command("我的id")
    async def myid_cmd_cn2(self, event: AstrMessageEvent):
        async for r in self._myid_cmd(event):
            yield r

    @filter.command("myid")
    async def myid_cmd_en(self, event: AstrMessageEvent):
        async for r in self._myid_cmd(event):
            yield r

    def _help_lines(self, show_admin_help: bool, platform_name: str = "", in_group: bool = True,
                    section: str = "") -> list:
        """构建帮助文本。
        section 为空 → 只给精简总览（最常用 + 分类入口）；section 有值 → 给该分类完整清单。"""
        sc = self._signin_cfg()
        ase_pts = sc.get('ase_points', 50)
        asa_pts = sc.get('asa_points', 50)
        is_kook = (platform_name or '').strip() == 'kook'
        has_onebot = self._find_platform_inst('aiocqhttp') is not None
        sec = (section or '').strip().lower()

        if sec in ('查询', '查', 'query', 'q'):
            lines = [
                "📖 查询类指令",
                "· /在线玩家 [进化|飞升] [地图名] → 在线人数 + 部落名",
                "· /进化 [地图名] ｜ /飞升 [地图名] → 服务器状态（不给地图名=列全部）",
                "· /查服 <IP:端口 或 地图名> [进化|飞升] → 通用查询",
                "· /倍率 → 当前动态倍率",
                "· /直连 → 所有地图直连地址",
                "· /状态 → 各服务器在线 / 离线一览",
            ]
        elif sec in ('绑定', '账号', 'bind', 'signin'):
            lines = [
                "📖 绑定 / 签到",
                "· /绑定 飞升 <EOS 32位ID> ｜ /绑定 进化 <SteamID64> → 直接绑定（推荐）",
                "·   飞升的 EOS ID 在游戏里打开商店（ArkShop）就能看到",
                "· /绑定 <进化|飞升> 开绑 → 拿 6 位验证码 → 游戏公屏 zsbind <验证码>（换绑也走这条）",
                "· 换绑：先 /解绑 <进化|飞升>，再重新绑定",
                f"· /签到 → 每日领点数（进化 +{ase_pts} / 飞升 +{asa_pts}，每天各一次）",
                "· /查绑定 → 查看我的绑定 ｜ /解绑 <进化|飞升> → 解除绑定",
                "· /关联 → QQ ↔ KOOK 身份打通（同一游戏账号自动关联，也可 /关联 开码 手动）",
                "· 一个游戏账号每天只加一次点数（两边都签到也不会双倍）",
            ]
        elif sec in ('管理', 'admin', 'owner'):
            if not show_admin_help:
                lines = ["ℹ️ 管理指令只有主人可见：请在私聊机器人里发 /帮助 管理"]
            else:
                lines = [
                    "📖 管理员指令",
                    "· /rcon <进化|飞升> [地图名] <命令> → 执行 RCON 命令",
                    "· /加点 <进化|飞升> <ID> <点数> → 加 ArkShop 点数",
                    "· /代加点 <进化|飞升> <点数> @群友… → 给已绑定群友加点",
                    "· /测试推送 → 测试主动消息通道 ｜ /更新地址 → 刷新直连地址缓存",
                    "· /关联 列表 → 查看身份关联 ｜ /关联 解除 @某人 → 强制解除他人关联",
                    "· /我是谁 → 查看自己的平台ID / 群标识",
                    "· /测试按钮 → 试验：QQ 群消息带可点按钮",
                ]
        else:
            lines = [
                "📖 ZeroARK 指令（进化=ASE / 飞升=ASA）",
                "· /在线玩家 [进化|飞升] [地图名] → 在线人数 + 部落",
                "· /进化 [地图名] ｜ /飞升 [地图名] → 服务器状态",
                "· /签到 ｜ /查绑定 ｜ /绑定 ｜ /解绑 ｜ /关联",
                "· 完整清单：/帮助 查询 ｜ /帮助 绑定"
                + (" ｜ /帮助 管理" if show_admin_help else ""),
                "· 懒得记指令？发 /菜单 用编号（/1 就是在线玩家）",
            ]
            if is_kook and in_group:
                lines.append("· KOOK 频道：直接发 /指令 即可，不用 @机器人")
            elif in_group:
                lines.append("· QQ 群：发 /指令 即可（带 / 前缀就会响应），@机器人 也可以")
            else:
                lines.append("· 私聊：直接发 /指令 即可")
            if self.config.get('bridge_enabled', False) and len(self._broadcast_targets()) > 1:
                labels = "、".join(t['label'] or t['platform'] for t in self._broadcast_targets())
                lines.append(f"· 消息互通：{labels}（含游戏内聊天）")
        invite = self._invite_line(platform_name)
        if invite:
            lines += ["", invite]
        return lines

    # ==================== 公共消息审计（发往公共区域前先过一遍） ====================
    AUDIT_ID_RE = re.compile(r'\b(?:[0-9A-Fa-f]{32}|7656\d{13})\b')          # EOS/openid、SteamID64
    AUDIT_SECRET_RE = re.compile(r'\b(?:ark_|sk-)[A-Za-z0-9_\-]{16,}\b'
                                 r'|\bpassword\b\s*[:=]\s*\S{4,}', re.IGNORECASE)
    AUDIT_INTERNAL_RE = re.compile(
        r'\b(?:10|100|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}(?:\.\d{1,3}){1,2}\b')
    AUDIT_CODE_RE = re.compile(r'\bzsbind\s+\d{4,8}\b', re.IGNORECASE)      # 验证码不能出现在公共区域
    AUDIT_ADDR_RE = re.compile(r'[A-Za-z0-9_.\-]+:\d{2,5}')

    def _audit_public_text(self, text: str, is_public: bool) -> tuple:
        """发往公共区域前的自审：返回 (命中的类别列表, 处理后的文本)。
        log 模式只报告不改动；redact 模式把命中片段替换成 ***。私聊只查"硬凭据"。"""
        mode = str(self.config.get('public_msg_audit') or 'log').strip().lower()
        if mode in ('off', '0', 'false', 'no') or not text:
            return [], text
        do_mask = mode in ('redact', 'mask', 'block')
        hits, out = [], text

        checks = [('密钥/口令', self.AUDIT_SECRET_RE)]
        if is_public:
            # 直连地址是允许公开的，所以这里不搞"见 host:port 就报"，
            # 只报内网 IP、身份 ID、验证码，以及**命中自己 rcon_targets 的端点**（下面单独判）
            checks += [('身份ID', self.AUDIT_ID_RE), ('内网IP', self.AUDIT_INTERNAL_RE),
                       ('验证码', self.AUDIT_CODE_RE)]
        for name, rx in checks:
            if rx.search(out):
                hits.append(name)
                if do_mask:
                    out = rx.sub('***', out)

        if is_public:
            rcon_set = {f"{t.get('host')}:{t.get('port')}"
                        for t in (self.rcon_targets or []) if t.get('host')}
            if rcon_set:
                for m in self.AUDIT_ADDR_RE.finditer(out):
                    if m.group(0) in rcon_set:
                        hits.append('RCON端点')
                        if do_mask:
                            out = out.replace(m.group(0), '***')
                        break
        return hits, out

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """发送前钩子：①新人欢迎；②补互推入口；③**公共消息审计**（红线：公共区域的内容先过审）"""
        try:
            result = event.get_result()
            if result is None or not getattr(result, 'chain', None):
                return
            from astrbot.api.message_components import Plain
            texts = [c for c in result.chain if isinstance(c, Plain) and getattr(c, 'text', '')]

            # ① 新人首次互动欢迎（插件收不到"入群事件"，用首次交互代替）
            if self.config.get('welcome_new_user', True) and not self._is_owner(event):
                try:
                    sid = str(event.get_sender_id() or '')
                except Exception:
                    sid = ''
                if sid and self._mark_user_seen(self._target_key(self._event_platform(event), sid)):
                    welcome = str(self.config.get('welcome_text') or '').strip()
                    if welcome:
                        result.chain.append(Plain("\n\n" + welcome))
                        logger.info(f"👋 首次互动欢迎: {self._mask_id(sid)}")

            # ③ 公共消息审计（用户红线：发往公共区域的内容必须全部审核后才发送）
            #    默认 log 模式：只记日志、不改内容（dry-run 观察是否有误报）；配置切 redact 才自动打码
            try:
                is_public = bool(self._event_group_id(event))
                for comp in texts:
                    hits, new_text = self._audit_public_text(comp.text, is_public)
                    if hits:
                        self._audit_hit_count = getattr(self, '_audit_hit_count', 0) + 1
                        logger.warning(
                            f"🔎 公共消息审计命中 {sorted(set(hits))}"
                            f"（{'已自动打码' if new_text != comp.text else 'dry-run 仅记录'}）"
                            f"，累计 {self._audit_hit_count} 次")
                        if new_text != comp.text:
                            comp.text = new_text
            except Exception as e:
                logger.debug(f"公共消息审计异常: {e}")

            # ② 互推入口行
            if not self.config.get('invite_on_reply', True):
                return
            line = self._invite_line(self._event_platform(event))
            if not line:
                return
            if any(line in c.text for c in texts):
                return                      # /帮助 等回复里已经带了，不重复
            footer = self.footer or ''
            for comp in reversed(texts):
                if footer.strip() and footer in comp.text:
                    comp.text = comp.text.replace(footer, "\n\n" + line + footer, 1)
                    return
            result.chain.append(Plain("\n\n" + line))
        except Exception as e:
            logger.debug(f"回复装饰失败: {e}")

    def _welcome_file(self) -> str:
        return os.path.join(os.path.dirname(__file__), "seen_users.json")

    def _load_seen_users(self) -> set:
        """已互动过的用户集合（持久化到 seen_users.json）"""
        if getattr(self, '_seen_users', None) is not None:
            return self._seen_users
        self._seen_users = set()
        try:
            p = self._welcome_file()
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    self._seen_users = set(json.load(f) or [])
        except Exception as e:
            logger.debug(f"seen_users.json 读取失败: {e}")
        return self._seen_users

    def _mark_user_seen(self, key: str) -> bool:
        """首次见到该用户返回 True（并落盘）"""
        seen = self._load_seen_users()
        if key in seen:
            return False
        seen.add(key)
        try:
            with open(self._welcome_file(), "w", encoding="utf-8") as f:
                json.dump(sorted(seen), f, ensure_ascii=False)
        except OSError as e:
            logger.debug(f"seen_users.json 写入失败: {e}")
        return True

    @staticmethod
    def _kb_payload(buttons: list) -> dict:
        """构造 QQ 消息按钮（action.type=2：点击后把 data 里的文本当指令发出去），每行两个"""
        rows = []
        for i in range(0, len(buttons), 2):
            row = []
            for label, data in buttons[i:i + 2]:
                row.append({
                    "id": f"b{abs(hash(data)) % 1000000}",
                    "render_data": {"label": label, "visited_label": label, "style": 1},
                    "action": {"type": 2, "permission": {"type": 2}, "click_limit": 10,
                               "data": data, "at_bot_show_channel_list": False},
                })
            rows.append({"buttons": row})
        return {"rows": rows}

    async def _qq_send_keyboard(self, event, group_openid: str, content: str, buttons: list,
                                variant: int = 1) -> str:
        """实验功能：绕过 AstrBot 消息链，直接调 botpy 发一条带按钮的 QQ 群消息。
        variant 1=文本+按钮  2=markdown+按钮  3=文本+按钮(不带 msg_id，走主动消息)"""
        inst = self._find_platform_inst('qq_official')
        if inst is None:
            return "❌ 未找到 QQ 官方机器人适配器"
        api = getattr(getattr(inst, 'client', None), 'api', None)
        if api is None:
            return "❌ 适配器上取不到 botpy api（版本差异）"
        raw = getattr(getattr(event, 'message_obj', None), 'raw_message', None)
        msg_id = str(getattr(raw, 'id', '') or '') or None
        kb = self._kb_payload(buttons)
        tpl = str(self.config.get('qq_keyboard_template_id') or '').strip()
        if tpl:
            # 平台审核通过的「消息按钮模板」：直接用模板 id 发送
            kwargs = {"group_openid": str(group_openid), "msg_type": 0,
                      "content": content, "keyboard": {"id": tpl}}
        elif variant == 2:
            kwargs = {"group_openid": str(group_openid), "msg_type": 2,
                      "markdown": {"content": content}, "keyboard": kb}
        else:
            kwargs = {"group_openid": str(group_openid), "msg_type": 0, "keyboard": kb}
            if variant == 1:
                kwargs["content"] = content
            else:
                kwargs["content"] = content
        try:
            if msg_id and variant != 3:
                kwargs["msg_id"] = msg_id      # 被动回复，走 msg_id 不消耗主动额度
            ret = await api.post_group_message(**kwargs)
            logger.info(f"🧪 QQ 按钮(v{variant})返回: {str(ret)[:200]}")
            return f"✅ 变体 {variant} 发送成功（API 接受，无报错）\n返回：{str(ret)[:200]}"
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            logger.warning(f"🧪 QQ 按钮(v{variant})失败: {detail}")
            return (f"❌ 变体 {variant} 失败：{detail[:260]}\n"
                    f"（多半是没开通「按钮」能力，或该群/该机器人不允许使用）")

    async def _test_kb_cmd(self, event):
        """Owner 实验指令：在当前群发一条带按钮的消息（可指定变体 1/2/3/全试）"""
        if not self._check_whitelist(event):
            return
        if not self._is_owner(event):
            yield event.plain_result("ℹ️ 仅主人可用的实验指令")
            return
        if self._event_platform(event) != 'qq_official':
            yield event.plain_result("ℹ️ 这个实验只针对 QQ 官方机器人（KOOK 请用指令面板）")
            return
        group_id = self._event_group_id(event) or self.config.get('notify_group')
        if not group_id:
            yield event.plain_result("❌ 拿不到群标识，请在群里发这个指令")
            return
        arg = event.message_str.strip().split()
        want = arg[1].strip() if len(arg) > 1 else "1"
        buttons = [("在线玩家", "/在线玩家"), ("签到", "/签到"),
                   ("查绑定", "/查绑定"), ("帮助", "/帮助查询")]
        variants = [1, 2, 3] if want.lower() in ("all", "全部", "0") else [int(want) if want.isdigit() else 1]
        out = []
        for v in variants:
            out.append(await self._qq_send_keyboard(
                event, group_id, f"变体{v}：👇 试试点按钮（实验功能）", buttons, variant=v))
        yield event.plain_result("\n\n".join(out) + "\n\n发 /测试按钮 2 或 3 可换变体")

    @filter.command("测试按钮")
    async def test_kb_cmd_cn(self, event: AstrMessageEvent):
        async for r in self._test_kb_cmd(event):
            yield r

    @filter.command("testkb")
    async def test_kb_cmd_en(self, event: AstrMessageEvent):
        async for r in self._test_kb_cmd(event):
            yield r

    @filter.command("help")
    async def help_command(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        group = self._event_group_id(event)
        show_admin = self._is_owner(event) and (not group or str(group) in self._admin_channels())
        parts = event.message_str.strip().split(None, 1)
        section = parts[1].strip() if len(parts) > 1 else ''
        yield event.plain_result("\n".join(
            self._help_lines(show_admin, self._event_platform(event), bool(group), section)) + self.footer)

    @filter.command("帮助")
    async def help_command_cn(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        async for result in self.help_command(event):
            yield result

    # ======================== 编号菜单（QQ 个人认证下没有消息按钮，用 /数字 代替） ========================
    MENU_ITEMS = [
        ("1", "在线玩家", "查在线人数 + 部落"),
        ("2", "状态", "各服务器在线/离线"),
        ("3", "签到", "每日领点数"),
        ("4", "查绑定", "查看我的绑定"),
        ("5", "帮助 查询", "查询类指令清单"),
        ("6", "帮助 绑定", "绑定 / 换绑方式"),
    ]

    async def _menu_cmd(self, event):
        """显示编号菜单；之后发 /1 ... /6 即可（带斜杠在群里也能唤醒指令）"""
        if not self._check_whitelist(event):
            return
        lines = ["📋 菜单（直接发 /数字 就行）"]
        for num, name, desc in self.MENU_ITEMS:
            lines.append(f"/{num} {name} — {desc}")
        lines.append("")
        lines.append("💡 也可以直接发完整指令：/帮助 查询 ｜ /帮助 绑定")
        yield event.plain_result("\n".join(lines))

    @filter.command("菜单")
    async def menu_cmd_cn(self, event: AstrMessageEvent):
        async for r in self._menu_cmd(event):
            yield r

    @filter.command("menu")
    async def menu_cmd_en(self, event: AstrMessageEvent):
        async for r in self._menu_cmd(event):
            yield r

    async def _menu_pick(self, event, num: str):
        """编号菜单分发：把 /N 映射到对应内部命令"""
        if not self._check_whitelist(event):
            return
        if num == "1":
            async for r in self._players_cmd(event):
                yield r
            return
        if num == "2":
            yield event.plain_result(self._status_summary())
            return
        if num == "3":
            async for r in self._signin_cmd(event):
                yield r
            return
        if num == "4":
            async for r in self._mybind_cmd(event):
                yield r
            return
        if num in ("5", "6"):
            group = self._event_group_id(event)
            show_admin = self._is_owner(event) and (not group or str(group) in self._admin_channels())
            section = "查询" if num == "5" else "绑定"
            yield event.plain_result("\n".join(
                self._help_lines(show_admin, self._event_platform(event), bool(group), section)) + self.footer)
            return
        async for r in self._menu_cmd(event):
            yield r

    @filter.command("1")
    async def menu_pick_1(self, event: AstrMessageEvent):
        async for r in self._menu_pick(event, "1"):
            yield r

    @filter.command("2")
    async def menu_pick_2(self, event: AstrMessageEvent):
        async for r in self._menu_pick(event, "2"):
            yield r

    @filter.command("3")
    async def menu_pick_3(self, event: AstrMessageEvent):
        async for r in self._menu_pick(event, "3"):
            yield r

    @filter.command("4")
    async def menu_pick_4(self, event: AstrMessageEvent):
        async for r in self._menu_pick(event, "4"):
            yield r

    @filter.command("5")
    async def menu_pick_5(self, event: AstrMessageEvent):
        async for r in self._menu_pick(event, "5"):
            yield r

    @filter.command("6")
    async def menu_pick_6(self, event: AstrMessageEvent):
        async for r in self._menu_pick(event, "6"):
            yield r

    async def _ase_query(self, event: AstrMessageEvent, lang: str = "zh"):
        if not self._check_whitelist(event):
            return
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            # 不带地图名 → 列出所有进化服务器
            yield event.plain_result(await self._list_ase_servers(lang=lang))
            return
        map_name = parts[1].strip()
        ase_map = self.map_cache.get("ASE", {})
        if not ase_map:
            yield event.plain_result("⚠️ ASE 直连列表为空，请先执行 /更新地址" + self.footer)
            return
        key = _fuzzy_key(ase_map, map_name)
        addr_list = ase_map[key] if key else None
        if not addr_list:
            available = "、".join(list(ase_map.keys())[:20]) + ("..." if len(ase_map) > 20 else "")
            yield event.plain_result(f"未在进化(ASE)中找到地图 '{map_name}'，可用地图：{available}" + self.footer)
            return
        result = await self._query_ase_a2s(addr_list[0], map_name, version="ASE", lang=lang)
        yield event.plain_result(result)

    @filter.command("ase")
    async def ase_command(self, event: AstrMessageEvent):
        # 英文指令 → 显示英文（标准）地图名
        async for result in self._ase_query(event, lang="en"):
            yield result

    @filter.command("进化")
    async def ase_command_cn(self, event: AstrMessageEvent):
        # 中文指令 → 显示中文地图名
        async for result in self._ase_query(event, lang="zh"):
            yield result

    async def _asa_query(self, event: AstrMessageEvent, lang: str = "zh"):
        if not self._check_whitelist(event):
            return
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            # 不带地图名 → 列出所有飞升服务器
            yield event.plain_result(await self._list_asa_servers(lang=lang))
            return
        map_name = parts[1].strip()
        result = await self._query_asa(map_name, lang=lang)
        yield event.plain_result(result)

    @filter.command("asa")
    async def asa_command(self, event: AstrMessageEvent):
        # 英文指令 → 显示英文（标准）地图名
        async for result in self._asa_query(event, lang="en"):
            yield result

    @filter.command("飞升")
    async def asa_command_cn(self, event: AstrMessageEvent):
        # 中文指令 → 显示中文地图名
        async for result in self._asa_query(event, lang="zh"):
            yield result

    async def _ark_query(self, event: AstrMessageEvent, lang: str = "zh"):
        if not self._check_whitelist(event):
            return
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield event.plain_result("用法：/ark 或 /查服 <IP:端口> 或 <地图名> [ASE|ASA]" + self.footer)
            return
        query = parts[1]
        args = parts[2:] if len(parts) > 2 else []
        if ':' in query and re.match(r'^[\d.]+:\d+$', query):
            result = await self._query_ase_a2s(query, "未知服务器", "", lang=lang)
            yield event.plain_result(result)
            return
        version = None
        if args and args[0].upper() in ['ASE', 'ASA']:
            version = args[0].upper()
        else:
            in_ase = query in self.map_cache.get("ASE", {})
            in_asa = query in self.rcon_cache.get("ASA", {})
            if in_ase and in_asa:
                yield event.plain_result(f"找到多个版本的地图 '{query}'，请指定版本：/ark {query} ASE 或 /ark {query} ASA" + self.footer)
                return
            elif in_ase:
                version = "ASE"
            elif in_asa:
                version = "ASA"
            else:
                yield event.plain_result(f"未找到地图 '{query}'" + self.footer)
                return
        if version == "ASE":
            addr_list = self.map_cache.get("ASE", {}).get(query)
            if not addr_list:
                yield event.plain_result(f"地图 '{query}' 在 ASE 中无直连地址" + self.footer)
                return
            result = await self._query_ase_a2s(addr_list[0], query, version="ASE", lang=lang)
        else:
            result = await self._query_asa(query, lang=lang)
        yield event.plain_result(result)

    @filter.command("ark")
    async def ark_command(self, event: AstrMessageEvent):
        # 英文指令 → 显示英文（标准）地图名
        async for result in self._ark_query(event, lang="en"):
            yield result

    @filter.command("查服")
    async def ark_command_cn(self, event: AstrMessageEvent):
        # 中文指令 → 显示中文地图名
        async for result in self._ark_query(event, lang="zh"):
            yield result

    @filter.command("rate")
    async def rate_command(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.config.get('dynamic_ini_url') or DYNAMIC_INI_URL)
                resp.encoding = 'utf-8'
                content = resp.text
            rate_dict = _parse_dynamic_ini(content)
            if not rate_dict:
                yield event.plain_result("未解析到倍率数据" + self.footer)
                return
            lines = ["📊 当前服务器完整倍率列表:"]
            for key, value in rate_dict.items():
                cn = RATE_NAMES.get(key, key)
                lines.append(f"{cn}: {value}")
            lines.append(self.footer)
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"获取倍率失败: {e}" + self.footer)

    @filter.command("倍率")
    async def rate_command_cn(self, event: AstrMessageEvent):
        async for result in self.rate_command(event):
            yield result

    @filter.command("direct")
    async def direct_command(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        if not self.map_cache.get("ASE") and not self.map_cache.get("ASA"):
            yield event.plain_result("⚠️ 地址缓存为空，请稍后重试或执行 /更新地址 手动刷新。" + self.footer)
            return
        lines = ["📡 方舟服务器直连地址列表：\n"]
        if self.map_cache.get("ASE"):
            lines.append("【ASE 方舟生存进化】")
            for name, addrs in self.map_cache["ASE"].items():
                if addrs:
                    lines.append(f"{name}：{' 或 '.join(addrs[:3])}")
            lines.append("")
        if self.map_cache.get("ASA"):
            lines.append("【ASA 方舟生存飞升】")
            for name, addrs in self.map_cache["ASA"].items():
                if addrs:
                    display = name.replace("_nomod", "(无mods)")
                    lines.append(f"{display}：{' 或 '.join(addrs[:3])}")
            lines.append("")
        lines.append("💡 使用方法：在游戏控制台输入 open <地址> 即可直连。")
        lines.append(self.footer)
        yield event.plain_result("\n".join(lines))

    @filter.command("直连")
    async def direct_command_cn(self, event: AstrMessageEvent):
        async for result in self.direct_command(event):
            yield result

    @filter.command("update_address")
    async def update_address_command(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        await self._fetch_servers()
        await self._fetch_rcon_data()
        self._build_rcon_targets()
        yield event.plain_result("✅ 地址缓存已更新！（直连地址来自 Servers.html，RCON 来自 RCON.html）\n\n" + GAME_CMD_TIPS + self.footer)

    @filter.command("更新地址")
    async def update_address_command_cn(self, event: AstrMessageEvent):
        async for result in self.update_address_command(event):
            yield result

    # ======================== QQ 绑定 & 每日签到 ========================
    # 进化(ASE)用 SteamID64，飞升(ASA)用 EOS(32位hex)。
    # 签到通过 RCON 只对“该版本某台在线服务器”执行一次加点命令（绝不广播，天然防止重复加点）；
    # “每天一次”由 qq 库 qq_checkin 的 (qq, game, day) 唯一键保证，跨重启/并发都不会重复发放。

    def _bind_cfg(self) -> dict:
        return self.config.get('bind_db') or {}

    def _signin_cfg(self) -> dict:
        return self.config.get('signin') or {}

    async def _qq_db(self):
        cfg = self._bind_cfg()
        if not (cfg.get('host') and cfg.get('user')):
            raise RuntimeError("bind_db 未配置（config.json -> bind_db）")
        return await aiomysql.connect(
            host=cfg.get('host'), port=int(cfg.get('port', 3306)),
            user=cfg.get('user'), password=cfg.get('password'),
            db=cfg.get('database', 'qq'), charset='utf8mb4',
            autocommit=False, connect_timeout=5)

    async def _ensure_qq_tables(self, force: bool = False):
        """确保绑定/签到表存在（幂等），并自动迁移旧库：qq BIGINT → VARCHAR(64) 以支持 openid。
        首次检查通过后置 _qq_tables_ready=True，后续调用直接返回（避免每条命令都查一遍元数据）"""
        if self._qq_tables_ready and not force:
            return
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            with warnings.catch_warnings():
                # 抑制 aiomysql 对 CREATE TABLE IF NOT EXISTS 打出的 "Table ... already exists" 噪音
                warnings.simplefilter("ignore")
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS qq_bind (
                        qq VARCHAR(64) NOT NULL,
                        platform VARCHAR(16) NOT NULL DEFAULT '',
                        game VARCHAR(8) NOT NULL,
                        player_id VARCHAR(64) NOT NULL,
                        player_name VARCHAR(100) NOT NULL DEFAULT '',
                        last_map VARCHAR(50) NOT NULL DEFAULT '',
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (qq, game),
                        KEY idx_game_player (game, player_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS qq_checkin (
                        qq VARCHAR(64) NOT NULL,
                        game VARCHAR(8) NOT NULL,
                        player_id VARCHAR(64) NOT NULL DEFAULT '',
                        day CHAR(10) NOT NULL,
                        points INT NOT NULL DEFAULT 0,
                        server_name VARCHAR(100) NOT NULL DEFAULT '',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (qq, game, day),
                        KEY idx_game_player_day (game, player_id, day)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS qq_link (
                        ident VARCHAR(64) NOT NULL,
                        alias_of VARCHAR(64) NOT NULL,
                        platform VARCHAR(16) NOT NULL DEFAULT '',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ident)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            async def _col_type(table, col):
                await cur.execute(
                    "SELECT DATA_TYPE FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                    (table, col))
                r = await cur.fetchone()
                return r[0] if r else ''

            for tbl in ('qq_bind', 'qq_checkin'):
                t = str(await _col_type(tbl, 'qq') or '').lower()
                if t and t not in ('varchar', 'char', 'text'):
                    await cur.execute(f"ALTER TABLE `{tbl}` MODIFY COLUMN qq VARCHAR(64) NOT NULL")
                    logger.info(f"🔧 {tbl}.qq 已从 {t} 迁移为 VARCHAR(64)（支持 openid）")
            if not await _col_type('qq_bind', 'platform'):
                await cur.execute("ALTER TABLE qq_bind ADD COLUMN platform VARCHAR(16) NOT NULL DEFAULT '' AFTER qq")
                logger.info("🔧 qq_bind 已补充 platform 列")
            # qq_checkin 增加 player_id：同一个游戏账号每天只能领一次，防止 QQ/KOOK 两边各签一次刷双倍
            if not await _col_type('qq_checkin', 'player_id'):
                await cur.execute("ALTER TABLE qq_checkin ADD COLUMN player_id VARCHAR(64) NOT NULL DEFAULT '' AFTER game")
                logger.info("🔧 qq_checkin 已补充 player_id 列（按游戏账号防重复签到）")
            await cur.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='qq_checkin' AND INDEX_NAME='idx_game_player_day'")
            if not (await cur.fetchone())[0]:
                await cur.execute("ALTER TABLE qq_checkin ADD KEY idx_game_player_day (game, player_id, day)")
                logger.info("🔧 qq_checkin 已补充索引 idx_game_player_day")
            # 回填历史记录的 player_id（按同样的 qq+game 从 qq_bind 取）
            await cur.execute(
                "UPDATE qq_checkin c JOIN qq_bind b ON c.qq=b.qq AND c.game=b.game "
                "SET c.player_id=b.player_id WHERE (c.player_id IS NULL OR c.player_id='') AND b.player_id<>''")
            if cur.rowcount:
                logger.info(f"🔧 已回填 {cur.rowcount} 条签到的 player_id")
            # 仅当运行在 QQ 官方机器人下：把 OneBot 时代的旧绑定（纯数字 QQ 号主键）标记为 legacy。
            # 这些主键在 openid 体系下永远匹配不到，玩家需重新走一次"开绑 + 游戏内 zsbind"，
            # 届时按游戏ID自动接回原账号（见 _claim_legacy_binding）。
            if self._platform_tag() == 'qq_official':
                await cur.execute(
                    "UPDATE qq_bind SET platform='legacy' "
                    "WHERE (platform IS NULL OR platform='') AND qq REGEXP '^[0-9]{5,12}$'")
                if cur.rowcount:
                    logger.info(f"🔖 已标记 {cur.rowcount} 条旧 QQ 号绑定为 legacy（可自动迁移）")
                await cur.execute("SELECT COUNT(*) FROM qq_bind WHERE platform='legacy'")
                _legacy_n = (await cur.fetchone())[0] or 0
                if _legacy_n:
                    logger.info(f"ℹ️ qq_bind 仍有 {_legacy_n} 条旧 QQ 号绑定(legacy)，这些玩家需重新绑定一次")
            await conn.commit()
            await cur.close()
            self._qq_tables_ready = True
            logger.info("✅ qq 数据库表结构已就绪 (qq_bind / qq_checkin)")
        finally:
            conn.close()

    async def _safe_ensure_qq_tables(self):
        try:
            await self._ensure_qq_tables()
        except Exception as e:
            logger.error(f"❌ 初始化 qq 数据库表失败: {e}")

    def _today_str(self) -> str:
        offset = float(self._signin_cfg().get('timezone_offset_hours', 8))
        return (datetime.utcnow() + timedelta(hours=offset)).strftime('%Y-%m-%d')

    @staticmethod
    def _parse_game(token: str) -> str:
        t = (token or '').strip().upper()
        if t in ("ASE", "进化", "EVO"):
            return "ASE"
        if t in ("ASA", "飞升", "ASCEND"):
            return "ASA"
        return ""

    @staticmethod
    def _game_cn(game: str) -> str:
        return "进化" if game == "ASE" else "飞升"

    def _is_valid_id(self, game: str, pid: str) -> bool:
        pid = pid.strip()
        if game == "ASE":
            return bool(re.fullmatch(r"7656119\d{10}", pid))
        return bool(re.fullmatch(r"[0-9a-fA-F]{32}", pid))

    def _sender_qq(self, event: AstrMessageEvent) -> str:
        """发送者标识：OneBot 下是 QQ 号，QQ 官方机器人下是 user_openid（字符串）"""
        try:
            qq = event.get_sender_id()
        except Exception:
            qq = None
        if qq:
            return str(qq)
        try:
            sid = str(event.get_session_id() or '')
        except Exception:
            sid = ''
        for tok in re.split(r'[_\s]', sid):
            if tok.isdigit() and len(tok) >= 5:
                return tok
        return ""

    async def _bind_upsert(self, qq, game, pid, pname="", pmap="", platform=""):
        qq = await self._resolve_identity(qq)
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute(
                "INSERT INTO qq_bind (qq, platform, game, player_id, player_name, last_map) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE platform=VALUES(platform), player_id=VALUES(player_id), "
                "player_name=VALUES(player_name), last_map=VALUES(last_map)",
                (str(qq), platform or self._platform_tag(), game, pid, pname, pmap))
            await conn.commit()
            await cur.close()
        finally:
            conn.close()

    async def _claim_legacy_binding(self, qq, game, pid) -> dict:
        """重新绑定时若当前游戏ID命中一条 legacy 旧绑定（OneBot 时代的 QQ 号主键），
        删除旧行、由本次绑定接替（同一游戏ID，绑定数据不丢），返回被迁移的旧行。
        只在带游戏内身份证明的路径（zsbind / qqbind）调用。"""
        try:
            conn = await self._qq_db()
        except Exception as e:
            logger.debug(f"legacy 绑定迁移跳过: {e}")
            return {}
        try:
            cur = await conn.cursor(aiomysql.DictCursor)
            await cur.execute(
                "SELECT qq, player_id FROM qq_bind "
                "WHERE game=%s AND player_id=%s AND platform='legacy' LIMIT 1",
                (game, str(pid)))
            row = await cur.fetchone()
            if not row or str(row.get('qq')) == str(qq):
                await cur.close()
                return {}
            await cur.execute("DELETE FROM qq_bind WHERE qq=%s AND game=%s AND platform='legacy'",
                              (str(row.get('qq')), game))
            await conn.commit()
            await cur.close()
            logger.info(f"🔁 旧绑定已迁移: 旧QQ={row.get('qq')} → 新标识={str(qq)[:12]}… ({game}, {pid})")
            return dict(row)
        except Exception as e:
            logger.warning(f"legacy 绑定迁移失败: {e}")
            return {}
        finally:
            conn.close()

    async def _resolve_identity(self, qq) -> str:
        """把当前身份解析到"主身份"：QQ 与 KOOK 用 /关联 打通后，两边共用同一份绑定与签到记录"""
        cur_ident = str(qq or '')
        if not cur_ident:
            return cur_ident
        try:
            conn = await self._qq_db()
        except Exception:
            return cur_ident
        try:
            c = await conn.cursor()
            for _ in range(5):
                await c.execute("SELECT alias_of FROM qq_link WHERE ident=%s", (cur_ident,))
                r = await c.fetchone()
                if not r or not r[0] or str(r[0]) == cur_ident:
                    break
                cur_ident = str(r[0])
            await c.close()
            return cur_ident
        except Exception:
            return str(qq or '')
        finally:
            conn.close()

    async def _link_identities(self, ident, main, platform='') -> bool:
        """把 ident 关联到 main（ident 之后与 main 共用绑定/签到）"""
        ident, main = str(ident or ''), str(main or '')
        if not ident or not main or ident == main:
            return False
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute(
                "INSERT INTO qq_link (ident, alias_of, platform) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE alias_of=VALUES(alias_of), platform=VALUES(platform)",
                (ident, main, str(platform or '')[:16]))
            # 绑定行也搬到主身份下（同游戏已有不同ID则保留主身份的，避免覆盖）
            await cur.execute(
                "UPDATE IGNORE qq_bind SET qq=%s WHERE qq=%s", (main, ident))
            await cur.execute("DELETE FROM qq_bind WHERE qq=%s", (ident,))
            # 签到记录同样迁移（(qq,game,day) 冲突时以主身份那行为准）
            await cur.execute(
                "UPDATE IGNORE qq_checkin SET qq=%s WHERE qq=%s", (main, ident))
            await cur.execute("DELETE FROM qq_checkin WHERE qq=%s", (ident,))
            await conn.commit()
            await cur.close()
            return True
        finally:
            conn.close()

    async def _unlink_identity(self, ident) -> bool:
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute("DELETE FROM qq_link WHERE ident=%s", (str(ident),))
            n = cur.rowcount
            await conn.commit()
            await cur.close()
            return n > 0
        finally:
            conn.close()

    async def _list_links(self, limit: int = 30):
        """列出身份关联（别名 → 主身份）"""
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute("SELECT ident, alias_of, platform FROM qq_link ORDER BY created_at DESC LIMIT %s",
                              (int(limit),))
            rows = await cur.fetchall()
            await cur.close()
            return [(str(r[0]), str(r[1]), str(r[2] or '')) for r in rows]
        finally:
            conn.close()

    async def _auto_link_by_binding(self, qq, game, pid) -> str:
        """同一游戏账号已绑在另一个身份上时，自动把当前身份关联过去（返回主身份，无则空串）"""
        pid = str(pid or '').strip()
        if not pid:
            return ''
        me = await self._resolve_identity(qq)
        try:
            conn = await self._qq_db()
        except Exception:
            return ''
        try:
            cur = await conn.cursor()
            await cur.execute(
                "SELECT qq FROM qq_bind WHERE game=%s AND player_id=%s AND qq<>%s LIMIT 5",
                (game, pid, me))
            rows = await cur.fetchall()
            await cur.close()
        except Exception:
            return ''
        finally:
            conn.close()
        for r in rows or []:
            main = await self._resolve_identity(str(r[0]))
            if not main or main == me:
                continue
            if await self._link_identities(me, main, platform='auto'):
                logger.info(f"🔗 同一游戏账号自动关联: {self._mask_id(me)} → {self._mask_id(main)} ({game})")
                return main
        return ''

    async def _get_bindings(self, qq) -> dict:
        qq = await self._resolve_identity(qq)
        conn = await self._qq_db()
        try:
            cur = await conn.cursor(aiomysql.DictCursor)
            await cur.execute(
                "SELECT game, player_id, player_name, last_map, platform FROM qq_bind WHERE qq=%s",
                (str(qq),))
            rows = await cur.fetchall()
            await cur.close()
            return {r['game']: r for r in rows}
        finally:
            conn.close()

    async def _unbind(self, qq, game) -> bool:
        qq = await self._resolve_identity(qq)
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute("DELETE FROM qq_bind WHERE qq=%s AND game=%s", (str(qq), game))
            await conn.commit()
            deleted = cur.rowcount > 0
            await cur.close()
            return deleted
        finally:
            conn.close()

    async def _checkin_exists(self, qq, game, day) -> bool:
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute("SELECT COUNT(*) FROM qq_checkin WHERE qq=%s AND game=%s AND day=%s",
                              (str(qq), game, day))
            n = (await cur.fetchone())[0]
            await cur.close()
            return bool(n)
        finally:
            conn.close()

    async def _claim_checkin(self, qq, game, day, points, server_name, player_id='') -> bool:
        """先占坑（(qq,game,day) 唯一键防并发/防重复）；返回 False 表示今天已签过或冲突"""
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            try:
                await cur.execute(
                    "INSERT INTO qq_checkin (qq, game, player_id, day, points, server_name) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (str(qq), game, str(player_id or '')[:64], day, int(points), (server_name or '')[:100]))
            except Exception:
                await conn.rollback()
                return False
            await conn.commit()
            await cur.close()
            return True
        finally:
            conn.close()

    async def _checkin_exists_for_player(self, game, player_id, day) -> bool:
        """同一个游戏账号当天是否已被领过（防 QQ / KOOK 两个身份各签一次、同账号双倍点数）"""
        pid = str(player_id or '').strip()
        if not pid:
            return False
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute("SELECT COUNT(*) FROM qq_checkin WHERE game=%s AND player_id=%s AND day=%s",
                              (game, pid, day))
            n = (await cur.fetchone())[0]
            await cur.close()
            return bool(n)
        finally:
            conn.close()

    async def _revoke_checkin(self, qq, game, day):
        """加点执行失败时回滚占坑，允许当天重试"""
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            await cur.execute("DELETE FROM qq_checkin WHERE qq=%s AND game=%s AND day=%s", (str(qq), game, day))
            await conn.commit()
            await cur.close()
        finally:
            conn.close()

    async def _lookup_chat_player(self, game: str, pid: str):
        """在聊天记录里反查 (角色名, 地图)，用于绑定展示/校验；查不到返回 None"""
        src_id = 'asa_chat' if game == 'ASA' else 'ase_chat'
        src = next((s for s in (self.config.get('db_sources') or []) if s.get('id') == src_id), None)
        if not src:
            return None
        col = 'EOSid' if game == 'ASA' else 'SteamId'
        try:
            conn = await aiomysql.connect(
                host=src.get('host'), port=int(src.get('port', 3306)),
                user=src.get('user'), password=src.get('password'),
                db=src.get('database'), charset='utf8mb4', autocommit=True, connect_timeout=5)
            cur = await conn.cursor()
            tbl = src.get('table', 'cross_chat')
            await cur.execute(f"SELECT Sender, Map FROM `{tbl}` WHERE `{col}`=%s AND Sender<>'' ORDER BY Id DESC LIMIT 1", (pid,))
            row = await cur.fetchone()
            await cur.close()
            conn.close()
            return row if row else None
        except Exception as e:
            logger.warning(f"查询聊天记录玩家信息失败: {e}")
            return None

    def _rcon_online_sync(self, host, port) -> bool:
        """探测某 RCON 目标是否在线可用"""
        if not self.rcon_password:
            return False
        try:
            with RconClient(host, port, passwd=self.rcon_password, timeout=3.0) as client:
                client.run("getserverinfo")
            return True
        except Exception:
            return False

    async def _pick_online_rcon_target(self, version: str):
        """并发探测，返回该版本第一台响应 RCON 的在线服务器；无则返回 None
        （跳过没装 ArkShop 的服务器，否则加点命令会打到没有插件的服上）"""
        targets = [t for t in (self.rcon_targets or [])
                   if str(t.get('name', '')).startswith(version + "-") and t.get('host') and t.get('port')]
        targets = self._arkshop_targets(targets)
        if not targets:
            return None
        loop = asyncio.get_running_loop()

        async def probe(t):
            try:
                ok = await asyncio.wait_for(
                    loop.run_in_executor(None, self._rcon_online_sync, t.get('host'), t.get('port')),
                    timeout=3.5)
                return t if ok else None
            except Exception:
                return None

        tasks = [asyncio.ensure_future(probe(t)) for t in targets]
        try:
            for fut in asyncio.as_completed(tasks, timeout=10):
                r = await fut
                if r:
                    for f in tasks:
                        if not f.done():
                            f.cancel()
                    return r
        except Exception:
            pass
        for f in tasks:
            if not f.done():
                f.cancel()
        return None

    async def _exec_addpoints(self, target, cmd: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._execute_rcon_command_sync, target['host'], target['port'], cmd)

    async def _signin_game(self, qq: str, game: str, bind_row: dict, in_group: bool = False) -> str:
        """对单个游戏执行一次签到：成功才落账，失败回滚可当天重试。返回展示文本"""
        cfg = self._signin_cfg()
        cn = self._game_cn(game)
        key_prefix = 'ase' if game == 'ASE' else 'asa'
        points = int(cfg.get(f'{key_prefix}_points', 50 if game == 'ASE' else 50))
        cmd_tpl = (cfg.get(f'{key_prefix}_cmd') or '').strip()
        if not cmd_tpl:
            return f"❌ 未配置{cn}加点命令（config.json → signin.{key_prefix}_cmd），本次未加点"
        if not bind_row.get('player_id'):
            hint = "；若你已在私聊绑定，请改在私聊签到（群/私聊的用户标识可能不同）" if in_group else ""
            return f"❌ 未查询到{cn}绑定，请先 /绑定 {cn} <ID>{hint}"
        day = self._today_str()
        main_qq = await self._resolve_identity(qq)   # 已 /关联 的话两边共用主身份
        if await self._checkin_exists(main_qq, game, day):
            return f"ℹ️ {cn}今天已签到过，明天再来吧"
        if await self._checkin_exists_for_player(game, str(bind_row['player_id']), day):
            return (f"ℹ️ 这个{cn}游戏账号今天已经领过了（每个游戏账号每天只能领一次）\n"
                    f"可能你在另一个平台或另一个聊天身份已经签过了，同一账号不会重复加点。")
        target = await self._pick_online_rcon_target(game)
        if not target:
            return f"❌ {cn}当前没有在线服务器，本次未加点，请稍后重试"
        if not await self._claim_checkin(main_qq, game, day, points, str(target.get('name', '')),
                                         str(bind_row['player_id'])):
            return f"ℹ️ {cn}今天已签到过，明天再来吧"
        command = cmd_tpl.format(id=bind_row['player_id'], points=points)
        out = await self._exec_addpoints(target, command)
        low = out.lower()
        if out.startswith("❌") or "unknown" in low or "not found" in low:
            await self._revoke_checkin(main_qq, game, day)
            logger.error(f"签到加点失败: qq={qq} game={game} cmd={command} resp={out}")
            return f"❌ {cn}加点命令执行异常（{out[:80]}），已回滚可重新签到。请检查 config.json signin.{key_prefix}_cmd 命令模板"
        logger.info(f"✅ 签到加点成功: qq={qq} game={game} +{points} server={target.get('name')} cmd={command} resp={out[:60]}")
        verify = await self._getpoints_text(target, bind_row['player_id']) if cfg.get('verify_with_getpoints', True) else ""
        pid_show = self._mask_id(bind_row['player_id']) if in_group else str(bind_row['player_id'])[:16]
        return f"✅ {cn}签到成功：已在 {self._target_label(target.get('name'))} 加点 +{points} 点（ID: {pid_show}）{verify}"

    async def _getpoints_text(self, target, pid) -> str:
        """用 ArkShop GetPlayerPoints 回读玩家余额，返回用于拼接的提示片段；无输出/失败返回空串"""
        try:
            bal = await self._exec_addpoints(target, f"GetPlayerPoints {pid}")
            low = bal.lower()
            if not bal.startswith("❌") and 'unknown' not in low and 'no response' not in low and bal.strip():
                nums = re.findall(r'-?\d+', bal)
                if nums:
                    return f"，GetPlayerPoints 返回: {nums[-1]}"
                return f"，GetPlayerPoints 返回: {bal.strip()[:40]}"
        except Exception as e:
            logger.debug(f"GetPlayerPoints 校验失败: {e}")
        return ""

    async def _bind_watcher(self):
        """监听游戏内聊天记录中的绑定指令（公屏 qqbind <QQ> / zsbind <验证码>）并自动完成绑定"""
        gb = self.config.get('game_bind') or {}
        if not gb.get('enable', True):
            logger.info("⏭️ 游戏内绑定监听未启用（game_bind.enable=false）")
            return
        interval = float(gb.get('poll_interval', 1.5))
        sources = {s.get('id'): s for s in (self.config.get('db_sources') or [])}
        if 'asa_chat' not in sources and 'ase_chat' not in sources:
            logger.warning("⚠️ 无聊天数据库源，游戏内绑定监听停用")
            return
        last_ids = {}
        fail_until = 0.0
        logger.info("✅ 游戏内绑定监听已启动（游戏公屏 qqbind / zsbind）")
        # 首次启动：把各源水位线初始化为当前最大ID，避免回放历史消息导致误绑
        for src_id in ('asa_chat', 'ase_chat'):
            src = sources.get(src_id)
            if not src:
                continue
            try:
                conn = await self._get_bind_chat_conn(src)
                cur = await conn.cursor()
                tbl = src.get('table', 'cross_chat')
                await cur.execute(f"SELECT COALESCE(MAX(Id), 0) FROM `{tbl}`")
                last_ids[src_id] = (await cur.fetchone())[0] or 0
                await cur.close()
                logger.info(f"📌 绑定监听源 {src_id} 初始水位线 = {last_ids[src_id]}")
            except Exception as e:
                await self._drop_bind_chat_conn(src_id)
                logger.warning(f"⚠️ 绑定监听初始化源 {src_id} 水位线失败: {e}")
        while True:
            try:
                now = time.time()
                # 清理过期验证码
                if self._pending_codes:
                    for c in [k for k, v in self._pending_codes.items() if v.get('expire', 0) <= now]:
                        self._pending_codes.pop(c, None)
                if now < fail_until:
                    await asyncio.sleep(interval)
                    continue
                for src_id in ('asa_chat', 'ase_chat'):
                    src = sources.get(src_id)
                    if not src:
                        continue
                    game = 'ASA' if src_id == 'asa_chat' else 'ASE'
                    col = 'EOSid' if game == 'ASA' else 'SteamId'
                    last_id = last_ids.get(src_id, 0)
                    try:
                        conn = await self._get_bind_chat_conn(src)
                        cur = await conn.cursor(aiomysql.DictCursor)
                        tbl = src.get('table', 'cross_chat')
                        await cur.execute(
                            f"SELECT Id, Map, Sender, Message, `{col}` AS pid FROM `{tbl}` "
                            f"WHERE Id > %s ORDER BY Id ASC LIMIT 500", (last_id,))
                        rows = await cur.fetchall()
                        await cur.close()
                        if rows:
                            last_ids[src_id] = max(r.get('Id', 0) for r in rows)
                            await self._handle_bind_rows(rows, game)
                    except Exception as e:
                        await self._drop_bind_chat_conn(src_id)
                        logger.error(f"绑定监听读取失败 ({src_id}): {e}")
                        fail_until = time.time() + 10
            except Exception as e:
                logger.error(f"游戏内绑定监听异常: {e}")
            await asyncio.sleep(interval)

    async def _get_bind_chat_conn(self, src):
        """获取/复用绑定监听的聊天库连接（避免每轮新建连接）；断线自动重建"""
        key = src.get('id', 'default')
        conn = self._bind_chat_conns.get(key)
        if conn is not None:
            try:
                if conn.open:
                    return conn
            except Exception:
                pass
            await self._drop_bind_chat_conn(key)
        conn = await aiomysql.connect(
            host=src.get('host'), port=int(src.get('port', 3306)),
            user=src.get('user'), password=src.get('password'),
            db=src.get('database'), charset='utf8mb4', autocommit=True, connect_timeout=5)
        self._bind_chat_conns[key] = conn
        return conn

    async def _drop_bind_chat_conn(self, key):
        conn = self._bind_chat_conns.pop(key, None)
        if conn is not None:
            try:
                await conn.ensure_closed()
            except Exception:
                pass

    async def _handle_bind_rows(self, rows, game):
        """处理一批游戏聊天记录：识别 qqbind / zsbind 并执行绑定"""
        for r in rows:
            msg = str(r.get('Message') or '')
            pid = str(r.get('pid') or '').strip()
            sender = str(r.get('Sender') or '')[:80]
            pmap = str(r.get('Map') or '')[:50]
            if not pid or not _is_direct_game_chat(msg):
                continue  # 跳过机器人自己转发回来的带标记消息 / 无玩家ID的行
            m = QQBIND_RE.match(msg)
            if m:
                if (self.config.get('game_bind') or {}).get('qq_cmd', False):
                    await self._bind_by_qq_direct(m.group(1), game, pid, sender, pmap)
                else:
                    # 通道已停用：留一条日志便于排查"玩家说在游戏里发了没反应"
                    logger.info(f"⏭️ 游戏内 qqbind 已停用（game_bind.qq_cmd=false），忽略 [{sender}] 的绑定请求")
                continue
            m = ZSBIND_RE.match(msg)
            if m:
                pend = self._pending_codes.get(m.group(1).lower())
                if not pend or pend.get('game') != game or time.time() > pend.get('expire', 0):
                    continue
                self._pending_codes.pop(m.group(1).lower(), None)  # 一次性
                await self._apply_bind(pend['qq'], game, pid, sender, pmap,
                                       source='游戏内验证码', platform=str(pend.get('platform') or ''))
                continue

    async def _notify_bind_result(self, qq, text: str, platform: str = '') -> bool:
        """优先私聊通知（按绑定所在平台）；私聊失败且开启群内兜底（game_bind.dm_fallback='@'）时，
        在通知群以文本公告播报（调用方必须保证 text 不含验证码等敏感内容）"""
        try:
            if await self._send_private_msg(qq, text, platform=platform):
                return True
        except Exception as e:
            logger.debug(f"绑定结果私聊发送异常: {e}")
        gb = self.config.get('game_bind') or {}
        if str(gb.get('dm_fallback', '@')).lower() in ('@', 'on', 'true', '1'):
            try:
                if await self._broadcast(f"📢 [{self._mask_id(qq)}] {text}") > 0:
                    logger.info(f"绑定结果私聊失败，已在广播目标公告给 QQ {qq}")
                    return True
            except Exception as e:
                logger.debug(f"绑定结果群内兜底发送异常: {e}")
        logger.warning(f"绑定结果通知失败（私聊与群兜底均失败）: qq={qq}")
        return False

    async def _bind_by_qq_direct(self, qq, game, pid, sender, pmap):
        """游戏公屏 qqbind <QQ号>：未绑过才直接绑；已绑其它号则拒绝（防冒绑，需验证码换绑）"""
        try:
            binds = await self._get_bindings(qq)
        except Exception as e:
            logger.error(f"qqbind 查询绑定失败: {e}")
            return
        cur_row = binds.get(game)
        if cur_row:
            if str(cur_row.get('player_id')) == pid:
                return  # 同一账号重复绑定，忽略
            await self._notify_bind_result(
                qq,
                f"🔒 检测到游戏内玩家「{sender}」用你的QQ在{self._game_cn(game)}尝试绑定新账号，但你已绑定 {str(cur_row.get('player_id'))[:16]}…。已忽略（防冒绑）。\n如需换绑：QQ里发 /绑定 {self._game_cn(game)} 开绑 走验证码流程，或先 /解绑 {self._game_cn(game)}。")
            logger.info(f"游戏内绑定被拒(已绑不同号): qq={qq} game={game} new_pid={pid}")
            return
        await self._apply_bind(qq, game, pid, sender, pmap, source='游戏公屏qqbind',
                               platform=('legacy' if str(qq).isdigit() else 'qq_official'))

    async def _apply_bind(self, qq, game, pid, sender, pmap, source='', platform=''):
        """写入绑定并私聊通知（验证码流程允许直接换绑）"""
        try:
            existing = (await self._get_bindings(qq)).get(game)
            await self._ensure_qq_tables()
            migrated = await self._claim_legacy_binding(qq, game, pid)
            await self._bind_upsert(qq, game, pid, sender, pmap, platform=platform)
        except Exception as e:
            logger.error(f"游戏内绑定写入失败: qq={qq} game={game} pid={pid}: {e}")
            return
        if existing and str(existing.get('player_id')) != pid:
            verb = "换绑成功"
        elif existing:
            verb = "已确认绑定（无变化）"
        else:
            verb = "绑定成功"
        points = int(self._signin_cfg().get('ase_points' if game == 'ASE' else 'asa_points',
                                             50 if game == 'ASE' else 50))
        legacy_line = (f"\n🔁 已接回你原「{migrated.get('qq')}」的绑定记录（同一游戏账号，数据保留）。"
                       if migrated else "")
        await self._notify_bind_result(
            qq,
            f"✅ {self._game_cn(game)}游戏内{verb}：{self._mask_id(qq)} ↔ 角色「{sender}」（{pmap}），"
            f"ID {self._mask_id(pid)}（来源：{source}）\n"
            f"现在可用 /签到 每日领取 {points} 点。{legacy_line}",
            platform=platform)

    def _gen_bind_code(self) -> str:
        now = time.time()
        for _ in range(30):
            code = f"{random.randint(0, 999999):06d}"
            if code not in self._pending_codes:
                return code
        # 兜底：清理过期后重试
        self._pending_codes = {c: v for c, v in self._pending_codes.items() if v.get('expire', 0) > now}
        return f"{random.randint(0, 999999):06d}"

    async def _bind_cmd(self, event):
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq:
            yield event.plain_result("❌ 无法获取你的QQ，请私聊机器人或确认适配器")
            return
        parts = event.message_str.strip().split(None, 2)
        game = self._parse_game(parts[1]) if len(parts) >= 2 else ""
        if len(parts) < 3 or not game:
            yield event.plain_result("用法：\n/bind 或 /绑定 <进化|飞升> <ID>\n"
                                     "  飞升(ASA)填 EOS ID（32位，如 0002…）→ 在游戏里打开商店（ArkShop）能看到\n"
                                     "  进化(ASE)填 SteamID64（17位数字，7656119开头）\n"
                                     "不知道自己的 ID / 要换绑：/绑定 <进化|飞升> 开绑 → 拿 6 位验证码 → 游戏公屏发 zsbind <验证码>\n"
                                     "绑定后可用 /签到 每天领一次点数（进化+50 / 飞升+50，各游戏每天一次）")
            return
        # 验证码开绑：/绑定 <游戏> 开绑|验证码|code|换绑
        if parts[2].strip().lower() in ('code', '开绑', '验证码', '换绑'):
            gb = self.config.get('game_bind') or {}
            if not gb.get('code_cmd', True):
                yield event.plain_result("❌ 验证码绑定功能未启用（config.json → game_bind.code_cmd）")
                return
            code = self._gen_bind_code()
            ttl = int(gb.get('code_ttl_seconds', 180))
            if len(self._pending_codes) >= 100:
                self._pending_codes = {c: v for c, v in self._pending_codes.items()
                                       if v.get('expire', 0) > time.time()}
            self._pending_codes[code] = {'qq': qq, 'game': game, 'expire': time.time() + ttl,
                                         'platform': self._platform_tag_for(event)}
            hint = f"在游戏（{self._game_cn(game)}）公屏输入：zsbind {code}"
            ok = await self._send_private_msg(
                qq,
                f"🎫 {self._game_cn(game)} 游戏内绑定验证码：{code}\n\n{hint}\n\n"
                f"有效期 {ttl} 秒、仅限一次，验证码只发给你本人请勿外传；若该游戏已绑过其它号，用验证码可直接换绑。",
                platform=self._event_platform(event))
            if not ok:
                if self.config.get('bind_code_public_fallback', True):
                    # QQ 个人认证收不到私聊：直接在会话里给码（一次性、限时），否则玩家完全没法走验证码流程
                    logger.info(f"🎫 私聊不可达，验证码已在会话内下发（{self._platform_tag_for(event)}）")
                    yield event.plain_result(
                        f"🎫 {self._game_cn(game)} 开绑验证码：\n"
                        f"zsbind {code}\n\n"
                        f"（机器人暂时无法私聊你，所以直接发在这里；{ttl} 秒内有效、仅一次）\n"
                        f"下一步：进游戏，在公屏发上面整行；绑好后回这里发 /签到\n"
                        f"🔒 请勿外传，别人用了会绑到他自己的角色上。")
                    return
                self._pending_codes.pop(code, None)
                yield event.plain_result(
                    "❌ 验证码私发失败：机器人无法私聊到你。\n"
                    "· QQ 开放平台的「允许被其他 QQ 用户添加使用」目前只对企业开发者灰度开放，个人认证账号开不了 → 普通玩家收不到私聊\n"
                    "· 请改用直接绑定（无需私聊）：/绑定 飞升 <EOS 32位ID>（游戏里打开商店 ArkShop 能看到）　或　/绑定 进化 <SteamID64>\n"
                    "· 换绑：先 /解绑 飞升，再重新绑定")
                return
            yield event.plain_result(
                f"🎫 {self._game_cn(game)} 开绑成功，验证码已私发给你（{ttl} 秒有效，请勿外传）。\n"
                f"下一步：在游戏（{self._game_cn(game)}）公屏输入 zsbind <验证码>（验证码看你我私聊）")
            return
        pid = parts[2].strip()
        if not self._is_valid_id(game, pid):
            yield event.plain_result(f"❌ {self._game_cn(game)} ID 格式不正确：\n"
                                     f"  进化=SteamID64 17位数字（7656119开头）\n"
                                     f"  飞升=EOS 32位hex")
            return
        if game == 'ASA':
            pid = pid.lower()
        await self._safe_ensure_qq_tables()
        try:
            existing = (await self._get_bindings(qq)).get(game)
        except Exception as e:
            yield event.plain_result(f"❌ 查询绑定失败: {e}")
            return
        cur_pid = str((existing or {}).get('player_id') or '')
        if existing and cur_pid.lower() != pid.lower():
            # 已绑定且不是同一个游戏账号 → 必须走验证码换绑（防冒绑/误覆盖）
            logger.info(f"QQ侧绑定被拒(已绑不同号): qq={qq} game={game} old={cur_pid[:16]} new={pid[:16]}")
            yield event.plain_result(
                f"🔒 你已经绑定过{self._game_cn(game)}（ID {self._mask_id(cur_pid)}），换绑需要验证码：\n"
                f"· /绑定 {self._game_cn(game)} 开绑 → 验证码私发给你 → 游戏公屏发 zsbind <验证码>\n"
                f"· 或先 /解绑 {self._game_cn(game)}，再重新绑定")
            return
        info = await self._lookup_chat_player(game, pid)
        pname = info[0] if info else ''
        pmap = info[1] if info else ''
        try:
            await self._bind_upsert(qq, game, pid, pname, pmap, platform=self._platform_tag_for(event))
        except Exception as e:
            yield event.plain_result(f"❌ 绑定写入失败: {e}")
            return
        extra = f"（角色：{pname} @ {pmap}）" if pname else "（⚠️ 该ID暂未在ZeroARK聊天记录中出现，请确认ID正确）"
        auto_main = await self._auto_link_by_binding(qq, game, pid)
        auto_line = (f"\n🔗 检测到同一游戏账号已绑定在另一个平台，已自动关联（两边共用绑定与签到）"
                     if auto_main else "")
        public = bool(self._event_group_id(event))   # 群里展示一律打码
        qq_show = self._mask_id(qq) if public else qq
        pid_show = self._mask_id(pid) if public else pid
        if existing:
            yield event.plain_result(f"ℹ️ {self._game_cn(game)}已绑定同一账号（ID {pid_show}），信息已刷新 {extra}{auto_line}")
        else:
            yield event.plain_result(
                f"✅ {self._game_cn(game)}绑定成功：{self._event_platform(event) or '本平台'} ID={qq_show} → {pid_show} {extra}\n"
                f"提示：QQ 与 KOOK 是两套身份，另一边可发 /关联 开码 打通（同一游戏账号会自动关联）。{auto_line}")

    async def _link_cmd(self, event):
        """跨平台身份关联（QQ ↔ KOOK）：/关联 开码 | /关联 <码> | /关联 状态 | /关联 解除"""
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq:
            yield event.plain_result("❌ 无法获取你的用户ID，请私聊机器人或确认适配器")
            return
        arg = event.message_str.strip().split(None, 1)[1].strip() if len(event.message_str.strip().split(None, 1)) > 1 else ""
        platform = self._event_platform(event)
        public = bool(self._event_group_id(event))
        now = time.time()
        self._pending_links = {c: v for c, v in (self._pending_links or {}).items()
                               if v.get('expire', 0) > now}
        if not arg or arg.lower() in ('help', '用法', '?'):
            yield event.plain_result(
                "🔗 跨平台身份关联（QQ ↔ KOOK）\n"
                "· /关联 开码 → 生成 6 位关联码（3 分钟有效）\n"
                "· 到另一个平台发 /关联 <关联码> → 两边共用同一份绑定与签到\n"
                "· /关联 状态 → 查看当前关联情况\n"
                "· /关联 解除 → 取消关联｜主人：/关联 列表、/关联 解除 @某人")
            return
        if arg in ('开码', 'code', '开'):
            code = self._gen_bind_code()
            self._pending_links[code] = {'qq': qq, 'platform': platform, 'expire': now + 180}
            text = (f"🔗 关联码：{code}（3 分钟内有效、仅一次）\n"
                    f"请到另一个平台（QQ 或 KOOK）发：/关联 {code}\n"
                    f"成功后两边共用绑定与签到；同一游戏账号每天仍然只加一次点数。")
            if public:
                # 公共区域：优先私聊发码，避免被他人拿去关联
                if await self._send_private_msg(qq, text, platform=platform):
                    yield event.plain_result("🔗 关联码已私聊发给你，请到另一个平台发：/关联 <关联码>")
                    return
                yield event.plain_result("⚠️ 私聊发码失败（可能是陌生人限制/未加好友），已直接发在这里：\n"
                                         "（请勿外传，3 分钟内用完即失效）\n\n" + text)
                return
            yield event.plain_result(text)
            return
        if arg in ('状态', 'status'):
            main = await self._resolve_identity(qq)
            linked = str(main) != str(qq)
            if linked:
                yield event.plain_result(
                    f"🔗 当前身份 {self._mask_id(qq)}（{platform or '未知平台'}）\n"
                    f"已关联到主身份 {self._mask_id(main)}，两平台共用绑定与签到。")
            else:
                yield event.plain_result(
                    f"🔗 当前身份 {self._mask_id(qq)}（{platform or '未知平台'}）尚未关联其它平台。\n"
                    f"用 /关联 开码 然后在另一个平台发 /关联 <码> 即可打通。")
            return
        if arg in ('解除', 'unlink', '取消') or arg.startswith('解除'):
            targets = self._extract_at_qqs(event)
            if targets:
                # 主人可解除他人的关联：/关联 解除 @某人
                if not self._is_owner(event):
                    yield event.plain_result("ℹ️ 仅主人可解除他人的关联")
                    return
                done = []
                for t in targets:
                    if await self._unlink_identity(t):
                        done.append(self._mask_id(t))
                yield event.plain_result(("✅ 已解除关联：" + "、".join(done)) if done else "ℹ️ 这些身份没有关联")
                return
            ok = await self._unlink_identity(qq)
            yield event.plain_result("✅ 已解除关联（绑定记录留在了主身份下，如需可重新绑定）"
                                     if ok else "ℹ️ 当前身份没有关联")
            return
        if arg in ('列表', 'list'):
            if not self._is_owner(event):
                yield event.plain_result("ℹ️ 仅主人可查看关联列表")
                return
            links = await self._list_links()
            if not links:
                yield event.plain_result("📋 目前没有任何身份关联")
                return
            out = [f"📋 身份关联（别名 → 主身份，共 {len(links)} 条）："]
            for a, m, plat in links:
                out.append(f"· {self._mask_id(a)}（{plat or '?'}） → {self._mask_id(m)}")
            out.append("用 /关联 解除 @某人 可强制解除")
            yield event.plain_result("\n".join(out))
            return
        pend = (self._pending_links or {}).get(arg)
        if not pend or now > pend.get('expire', 0):
            yield event.plain_result("❌ 关联码无效或已过期，请在另一个平台重新 /关联 开码")
            return
        if str(pend['qq']) == str(qq):
            yield event.plain_result("ℹ️ 这是你自己的身份，请到另一个平台发这个码")
            return
        self._pending_links.pop(arg, None)
        main = await self._resolve_identity(pend['qq'])
        if not await self._link_identities(qq, main, platform=platform):
            yield event.plain_result("❌ 关联失败，请稍后重试")
            return
        logger.info(f"🔗 身份关联成功: {self._mask_id(qq)}({platform}) → {self._mask_id(main)}")
        yield event.plain_result(
            f"✅ 关联成功：你的 {platform or '本平台'} 身份已关联到主身份 {self._mask_id(main)}。\n"
            f"现在两个平台共用绑定与签到（以主身份的绑定为准）；同一游戏账号每天仍只加一次点数。")

    @filter.command("关联")
    async def link_cmd_cn(self, event: AstrMessageEvent):
        async for r in self._link_cmd(event):
            yield r

    @filter.command("link")
    async def link_cmd_en(self, event: AstrMessageEvent):
        async for r in self._link_cmd(event):
            yield r

    async def _unbind_cmd(self, event):
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq:
            yield event.plain_result("❌ 无法获取你的QQ")
            return
        parts = event.message_str.strip().split(None, 1)
        if len(parts) < 2:
            yield event.plain_result("用法：/unbind 或 /解绑 <进化|飞升>")
            return
        game = self._parse_game(parts[1])
        if not game:
            yield event.plain_result("❌ 版本需为 进化(ASE) 或 飞升(ASA)")
            return
        try:
            ok = await self._unbind(qq, game)
        except Exception as e:
            yield event.plain_result(f"❌ 解绑失败: {e}")
            return
        public = bool(self._event_group_id(event))
        yield event.plain_result(
            f"✅ 已解绑{self._game_cn(game)}（{self._mask_id(qq) if public else qq}）" if ok
            else f"ℹ️ 你未绑定{self._game_cn(game)}")

    async def _mybind_cmd(self, event):
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq:
            yield event.plain_result("❌ 无法获取你的QQ")
            return
        try:
            binds = await self._get_bindings(qq)
        except Exception as e:
            yield event.plain_result(f"❌ 查询失败: {e}")
            return
        if not binds:
            yield event.plain_result("ℹ️ 你还没有绑定任何游戏账号。" + BIND_GUIDE)
            return
        public = bool(self._event_group_id(event))   # 公共区域打码，私聊给完整 ID
        lines = [f"📋 {'你的' if public else ''}绑定（{self._mask_id(qq) if public else qq}）："]
        for game in ("ASE", "ASA"):
            if game in binds:
                b = binds[game]
                pid_show = self._mask_id(b['player_id']) if public else b['player_id']
                plat_cn = self._platform_tag_cn(b.get('platform'))
                lines.append(f"  {self._game_cn(game)}：{pid_show}（{plat_cn}）"
                             + (f"（角色 {b['player_name']} @ {b['last_map']}）" if b.get('player_name') else ""))
        if public:
            lines.append("🔒 公共区域已打码；完整 ID 请私聊机器人再发 /查绑定。")
        yield event.plain_result("\n".join(lines))

    async def _signin_cmd(self, event):
        if not self._check_whitelist(event):
            return
        in_group = bool(self._event_group_id(event))
        qq = self._sender_qq(event)
        if not qq:
            yield event.plain_result("❌ 无法获取你的QQ，请私聊机器人或确认适配器")
            return
        await self._safe_ensure_qq_tables()
        try:
            binds = await self._get_bindings(qq)
        except Exception as e:
            yield event.plain_result(f"❌ 查询绑定失败: {e}")
            return
        if not binds:
            if in_group:
                yield event.plain_result("ℹ️ 群里没有查到你的绑定，绑定后就能每天领点数。" + BIND_GUIDE)
            else:
                yield event.plain_result("ℹ️ 请先绑定游戏账号再签到。" + BIND_GUIDE)
            return
        msgs = []
        async with self._signin_lock:
            for game in ("ASE", "ASA"):
                if game in binds:
                    msgs.append(await self._signin_game(qq, game, binds[game], in_group=in_group))
        if any(str(m).startswith("✅") for m in msgs):
            msgs.append(GAME_CMD_TIPS)
        miss = [self._game_cn(g) for g in ("ASE", "ASA") if g not in binds]
        if miss:
            tip = "（群/私聊身份可能不同，建议私聊机器人绑定并签到）" if in_group else ""
            msgs.append(f"ℹ️ 未绑定 {'、'.join(miss)}，绑定后也可每日领取{tip}")
        yield event.plain_result("\n\n".join(msgs))

    @filter.command("bind")
    async def bind_command(self, event: AstrMessageEvent):
        async for r in self._bind_cmd(event):
            yield r

    @filter.command("绑定")
    async def bind_command_cn(self, event: AstrMessageEvent):
        async for r in self._bind_cmd(event):
            yield r

    @filter.command("unbind")
    async def unbind_command(self, event: AstrMessageEvent):
        async for r in self._unbind_cmd(event):
            yield r

    @filter.command("解绑")
    async def unbind_command_cn(self, event: AstrMessageEvent):
        async for r in self._unbind_cmd(event):
            yield r

    @filter.command("mybind")
    async def mybind_command(self, event: AstrMessageEvent):
        async for r in self._mybind_cmd(event):
            yield r

    @filter.command("查绑定")
    async def mybind_command_cn(self, event: AstrMessageEvent):
        async for r in self._mybind_cmd(event):
            yield r

    @filter.command("signin")
    async def signin_command(self, event: AstrMessageEvent):
        async for r in self._signin_cmd(event):
            yield r

    @filter.command("签到")
    async def signin_command_cn(self, event: AstrMessageEvent):
        async for r in self._signin_cmd(event):
            yield r

    @filter.command("每日签到")
    async def signin_command_cn2(self, event: AstrMessageEvent):
        async for r in self._signin_cmd(event):
            yield r

    # ======================== QQ->游戏 消息转发 ========================
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        logger.debug("🔍 on_message 被调用，事件类型: %s", type(event).__name__)

        if not isinstance(event, AstrMessageEvent):
            return

        if event.is_at_or_wake_command:
            return
        # 忽略机器人自己发出的消息（部分适配器 get_self_id 不可用，需兜底）
        try:
            if event.get_sender_id() and event.get_self_id() and event.get_sender_id() == event.get_self_id():
                return
        except (AttributeError, NotImplementedError):
            pass
        if not self.config.get('qq_to_game_enabled', True):
            return
        if not self._check_whitelist(event):
            return
        message = event.message_str.strip()
        if not message:
            return
        group_id = event.get_group_id()
        if not group_id:
            return  # 仅群聊/频道消息转发，私聊不转发
        # 带转发标记的消息（游戏跨服转发 / 群间互通副本）不再二次转发，防循环
        if any(mk in message for mk in RELAY_SKIP_MARKERS):
            logger.debug(f"⏭️ 消息含转发标记，跳过转发: {message[:40]}")
            return
        self._last_umo = event.unified_msg_origin
        if str(group_id) == str(self.config.get('notify_group')):
            self._notify_umo = event.unified_msg_origin
        platform_name = self._event_platform(event)
        sender_name = event.get_sender_name() or "用户"
        src_key = self._target_key(platform_name, group_id)
        targets = self._broadcast_targets()
        in_targets = src_key in [self._target_key(t['platform'], t['id']) for t in targets]
        logger.info(f"📨 收到 {platform_name or '未知平台'} {group_id} 消息: {sender_name}: {message}")
        # 只处理配置里的互通目标：其它群/频道（谁都能拉机器人）不往游戏公屏刷消息
        if targets and not in_targets:
            logger.debug(f"⏭️ {src_key} 不在 broadcast_targets 内，不转发到游戏")
            return

        # 群里没 @机器人 就发指令：AstrBot 不会把它派发给指令处理器，这里给一次提示（KOOK 频道不需要 @）
        # 另外：@机器人 的消息 / 像指令的消息一律**不转发**到游戏公屏与互通目标
        # （适配器的 @ 有时没被识别成 wake，只靠 is_at_or_wake_command 会漏判，导致指令被刷进游戏）
        addressed = self._at_bot(event)
        looks_cmd = self._looks_like_command(message)
        if addressed or looks_cmd:
            logger.info(f"⏭️ 判定为对机器人的指令（@={addressed} 疑似指令={looks_cmd}），不转发: {message[:40]}")
            if looks_cmd and not addressed and platform_name != 'kook':
                logger.info(f"💡 群内未 @机器人 的指令，已回提示: {message[:30]}")
                await self._send_group_text(platform_name, group_id,
                                            "💡 群里发指令要先 @机器人 哦～\n例如：@机器人 /帮助")
            return

        # ---------- LLM 自动回复（可选） ----------
        llm_enabled = self.config.get('llm_enabled', False)
        if llm_enabled:
            # 1. 过滤规则：只对 @机器人 或特定触发词响应
            bot_name = "ZeroARK"  # 机器人名称
            at_bot = f"@{bot_name}" in message
            # 触发词：可配置（config.json -> llm_trigger_keywords）
            trigger_keywords = self.config.get('llm_trigger_keywords') or ["报告", "总结", "解释", "帮忙", "ZeroARK", "指令", "绑定", "签到", "怎么", "使用", "倍率", "查服", "直连"]
            has_trigger = any(k in message for k in trigger_keywords)

            # 2. 排除纯数字/短消息（避免刷屏）
            if re.match(r'^[\d\s！。]+$', message):
                logger.info(f"🤖 LLM: 纯数字/短消息，跳过")
                return

            # 3. 只在以下情况回复
            if at_bot or has_trigger:
                # 4. 频率限制（同一服务器 5 分钟内最多 1 条，避免刷屏）
                now = time.time()
                last_llm_reply = getattr(self, '_last_llm_reply_time', 0)
                if now - last_llm_reply < 300:  # 5 分钟
                    logger.info(f"🤖 LLM 回复冷却中，跳过")
                    return
                self._last_llm_reply_time = now

                # 5. 调用 LLM（放后台任务，别挡住同一条消息的"转进游戏/群间互通"）
                logger.info(f"🤖 LLM 回复触发: {message[:50]}...")

                async def _llm_reply_async(_msg=message, _plat=platform_name, _gid=group_id):
                    try:
                        _reply = await self._call_llm(_msg)
                        if _reply:
                            await self._send_group_text(_plat, _gid, _reply)
                            logger.info(f"🤖 LLM 回复成功: {_reply[:50]}...")
                    except Exception as _e:
                        logger.error(f"LLM 回复任务异常: {_e}")

                self._background_tasks.append(asyncio.create_task(_llm_reply_async()))

        # ---------- 群间互通：把本条消息同步到其它广播目标（QQ群 ↔ KOOK 频道） ----------
        if self.config.get('bridge_enabled', False):
            # 跨平台互通也把 @提及里的真实 ID 换掉（QQ 的 <@openid> / KOOK 的 (met)id(met)）
            bridge_text = f"🔀 [{self._platform_label(platform_name)}] {sender_name}: {self.MENTION_RE.sub('@某人', message)}"
            sent_n = await self._broadcast(bridge_text, exclude=src_key)
            if sent_n:
                logger.info(f"🔀 群间互通已转发到 {sent_n} 个目标")

        # ---------- QQ/KOOK → 游戏（RCON / CCA / 彩色插件 三条通道；并发，避免单服超时阻塞整条链路） ----------
        via = str(self.config.get('game_send_via') or 'rcon').strip().lower()
        if via in ('plugin', 'rcon_color', 'color'):
            # 走 AsaApi 插件 ZeroARKMsg 的 RCON 命令：能上色（RCON 的 serverchat 本身不支持颜色）
            cmd_name = str(self.config.get('plugin_msg_cmd') or 'ZeroARKMsgSend').strip() or 'ZeroARKMsgSend'
            chat_cmd = str(self.config.get('plugin_chat_cmd') or 'ZeroARKMsgChat').strip() or 'ZeroARKMsgChat'
            color = str(self.config.get(f'plugin_msg_color_{platform_name}')
                        or self.config.get('plugin_msg_color') or '0.2,0.85,1').strip()
            prefix = (self.config.get('kook_forward_prefix', '[KOOK]') if platform_name == 'kook'
                      else self.config.get('qq_forward_prefix', '[QQ群]'))
            safe_sender = self._game_safe(sender_name)
            safe_msg = self._game_safe(message)
            plain_text = f"{prefix} {safe_sender}: {safe_msg}"
            # 富文本模板（可留空则退回"整条单色"）：{c}=平台颜色 {tag}=前缀 {sender}=发送者 {message}=内容
            rich_text = ''
            fmt = str(self.config.get('plugin_chat_format') or '').strip()
            if fmt:
                try:
                    rich_text = fmt.format(c=color, tag=prefix, sender=safe_sender, message=safe_msg)
                except Exception as e:
                    logger.error(f"plugin_chat_format 模板不合法（{e}），本条第色回退为单色发送")
                    rich_text = ''
            targets = [t for t in self.rcon_targets if t.get('host') and t.get('port')]
            if not targets:
                logger.warning("⚠️ 没有可用的 RCON 目标，彩色消息发不出去")
                return
            # 只有装了彩色插件（ZeroARKMsg）的服务器才走彩色命令，其余服务器仍用 serverchat，
            # 避免"插件没装 → 命令不认 → 那条服一条消息都收不到"
            only = [str(x).strip().lower() for x in (self.config.get('plugin_msg_servers') or []) if str(x).strip()]

            def _has_plugin(t):
                name = str(t.get('name') or '').lower()
                return bool(only) and any(x in name for x in only)

            colored = [t for t in targets if _has_plugin(t)]
            plain = [t for t in targets if not _has_plugin(t)]
            if colored:
                if rich_text:
                    await self._send_rcon_concurrent(colored, f"{chat_cmd} {rich_text}")
                else:
                    await self._send_rcon_concurrent(colored, f"{cmd_name} {color} {plain_text}")
            if plain:
                await self._send_rcon_concurrent(plain, f"serverchat {plain_text}")
            mode = "富文本" if rich_text else "单色"
            logger.info(f"🎨 [{mode}] 彩色 {len(colored)} 台 / 纯文本 {len(plain)} 台：{plain_text[:40]}")
            return
        if via == 'cca':
            if await self._cca_send(platform_name, sender_name, message):
                return
            if not self.config.get('cca_fallback_rcon', True):
                logger.warning("⚠️ CCA 通道失败，且 cca_fallback_rcon=false，本条不再发往游戏")
                return
            logger.warning("⚠️ CCA 通道失败，回退 RCON 发送")
        prefix = (self.config.get('kook_forward_prefix', '[KOOK]') if platform_name == 'kook'
                  else self.config.get('qq_forward_prefix', '[QQ群]'))
        game_message = f"{prefix} {sender_name}: {message}"
        targets = [t for t in self.rcon_targets if t.get('host') and t.get('port')]
        if not targets:
            logger.warning("⚠️ 没有可用的 RCON 目标，无法转发消息到游戏")
            return
        await self._send_rcon_concurrent(targets, f"serverchat {self._game_safe(game_message)}")

    def _send_rcon_command_sync(self, host: str, port: int, command: str):
        if not self.rcon_password:
            logger.warning("⚠️ RCON密码未获取，无法发送命令")
            return
        try:
            with RconClient(host, port, passwd=self.rcon_password, timeout=self.config.get('rcon_timeout', 10.0)) as client:
                client.run(command)
        except Exception as e:
            logger.error(f"RCON发送命令失败: {e}")
            raise
