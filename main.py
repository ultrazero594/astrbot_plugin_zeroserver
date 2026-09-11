import asyncio
import hashlib
import json
import re
import copy
import os
import random
import time
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
LEGACY_BIND_HINT = (
    "\n\n👤 老玩家提示：官方机器人拿不到真实 QQ 号，以前用 QQ 号绑定的记录已经失效，需要重新绑定一次。\n"
    "做法：QQ 里发 /绑定 进化|飞升 开绑 拿到验证码 → 在游戏公屏（保持你的角色在线）发 zsbind <验证码>，"
    "系统会自动接回你原来的账号。")

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
RELAY_SKIP_MARKERS = ("[飞升]", "[进化]", "[QQ群]", "[跨服]")
QQBIND_RE = re.compile(r'^\s*qqbind\s+(\d{5,12})\s*$', re.IGNORECASE)
ZSBIND_RE = re.compile(r'^\s*zsbind\s+([a-z0-9]{4,12})\s*$', re.IGNORECASE)

def _is_direct_game_chat(text: str) -> bool:
    """是否机器人转发回来（含转发标记）的消息：是则不是玩家直接在游戏里输入的"""
    if not text:
        return False
    return not any(mk in text for mk in RELAY_SKIP_MARKERS)

def _is_bind_chat(text: str) -> bool:
    """判断是否为游戏内绑定指令消息（qqbind/zsbind），用于转发时静默吞掉、仅由绑定监听消费"""
    if not text or not _is_direct_game_chat(text):
        return False
    return bool(QQBIND_RE.search(text) or ZSBIND_RE.search(text))

# 游戏内指令提示（帮助/签到成功/更新地址等处复用）
GAME_CMD_TIPS = (
    "【游戏内绑定（在游戏公屏输入）】\n"
    "· qqbind <你的QQ号> —— 直接把当前游戏账号绑到该QQ（该QQ未绑过此游戏时）\n"
    "· zsbind <验证码> —— 先 QQ 里发 /绑定 <进化|飞升> 开绑 拿验证码，再到游戏里输入完成绑定/换绑\n"
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
    "check_interval_minutes": 10,             # 地址/倍率定时刷新间隔（分钟）
    "official_site": "https://example.com/",  # 官网，显示在部分消息底部
    "rcon_timeout": 5.0,
    "arkstatus_api_key": "",                  # 可选：ARK Status API Key
    "chat_forward_enabled": False,            # 跨服聊天转发开关
    "chat_check_interval": 1.0,
    "list_rcon_fallback": True,               # 列表查询失败时用 RCON 回退判定在线/人数
    "db_sources": [],                         # 游戏聊天库源（见 README 数据库一节）
    "qq_to_game_enabled": True,               # QQ 群消息转发进游戏（RCON serverchat）
    "qq_forward_prefix": "💬 [QQ群]",
    "rcon_targets": [],                       # 手动 RCON 目标（也可由 rcon_html_url 自动构建）
    "cache_mirror_url": "",                   # 【抓取】缓存更新检测的目录列表页
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
        "qq_cmd": True,
        "code_cmd": True,
        "poll_interval": 1.5,
        "code_ttl_seconds": 180,
        "dm_fallback": "@"
    },
    "llm_trigger_keywords": ["报告", "总结", "解释", "帮忙", "ZeroARK", "指令", "绑定", "签到", "怎么", "使用", "倍率", "查服", "直连"],
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
                    fresh = [m for m in messages
                             if not self._is_relayed(str(m.get('Message', '')))
                             and not _is_bind_chat(str(m.get('Message', '')))]
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
        group_id = self.plugin.config.get('notify_group')
        for msg in messages:
            server = msg.get('Map', '未知地图')
            player = msg.get('Sender', '未知玩家') or '匿名'
            content = msg.get('Message', '')
            if not content:
                continue
            chat_text = f"{prefix}【{server}】{player}: {content}"
            # 1) 发到 QQ 群
            if group_id:
                logger.info(f"📤 转发到群 {group_id}: {chat_text[:50]}...")
                ok = await self.plugin._send_group_msg(group_id, chat_text)
                if not ok:
                    logger.error(f"❌ 发送消息到群 {group_id} 失败")
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
        await self.plugin._send_rcon_concurrent(targets, f"serverchat {text}")

    def stop(self):
        self.running = False

@register("astrbot_plugin_zeroserver", "ZeroARK", "方舟服务器查询机器人", "1.3.1", "https://github.com/ultrazero594/astrbot_plugin_zeroserver")
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

        self.seen_cache_files = set()
        self._background_tasks.append(asyncio.create_task(self._check_cache_updates()))
        logger.info("✅ 缓存更新检测任务已创建")

        # QQ 绑定 / 签到：初始化数据表（幂等；失败只记日志，不影响主流程）
        self._background_tasks.append(asyncio.create_task(self._safe_ensure_qq_tables()))

        # 游戏内绑定监听（玩家在游戏公屏输入 qqbind/zsbind）
        self._pending_codes = {}
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
            self.context.scheduler.add_job(self._check_updates, 'interval', seconds=interval, id='check_updates')

    async def _check_updates(self):
        await self._fetch_servers()
        await self._fetch_rcon_data()
        self._build_rcon_targets()
        await self._check_rate_update()

    async def _send_rcon_command_to_all(self, command: str):
        """向全部 RCON 目标并发发送命令（单个失败不影响其它目标）"""
        await self._send_rcon_concurrent(self.rcon_targets, command)

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
                    await self._send_rcon_command_to_all("ForceUpdateDynamicConfig")
                    # 游戏内广播（精简摘要）
                    short = []
                    for c in changes[:5]:
                        parts = c.split("：")
                        if len(parts) == 2:
                            short.append(parts[0].replace("🔄 ", "") + ":" + parts[1].split("→")[-1].strip())
                    broadcast = "服务器倍率已更新: " + " | ".join(short)
                    await self._send_rcon_command_to_all(f"serverchat {broadcast}")
                    msg = "📊 【服务器倍率更新提醒】\n" + "\n".join(changes)
                    await self._send_notify(msg + self.footer)
                    self.last_rate_hash = new_hash
                    self.last_rate_content = current
        except Exception as e:
            logger.error(f"检查倍率失败: {e}")

    async def _send_notify(self, message: str):
        await self._send_group_msg(self.config['notify_group'], message)

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

    async def _wait_qq_adapter(self, purpose: str = "发送消息"):
        """等待任一可用 QQ 平台就绪：优先 QQ 官方机器人，其次 OneBot；返回 (kind, obj)"""
        logger.info(f"⏳ 等待 QQ 适配器连接（{purpose}）...")
        while True:
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
            logger.info(f"✅ QQ 官方机器人已发送（{message_type}:{str(session_id)[:12]}...）")
            return True
        except Exception as e:
            logger.error(f"❌ QQ 官方机器人发送失败（{message_type}:{str(session_id)[:12]}...）: {type(e).__name__}: {e}")
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
        kind, obj = await self._wait_qq_adapter("群消息发送")
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

    async def _send_private_msg(self, user_id, message: str) -> bool:
        """主动发送私聊消息：优先 QQ 官方机器人（openid），其次 OneBot（QQ号）"""
        kind, obj = await self._wait_qq_adapter("私聊消息发送")
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
                    # 群通知
                    notify_group = self.config.get('notify_group')
                    if notify_group:
                        ok = await self._send_group_msg(notify_group, msg)
                        if not ok:
                            logger.error(f"❌ 发送群更新通知到 {notify_group} 失败")
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

    async def _execute_rcon_command(self, command: str) -> str:
        targets = self.rcon_targets
        if not targets:
            return "❌ 没有可用的 RCON 目标"
        loop = asyncio.get_running_loop()
        results = []
        for t in targets:
            host, port = t.get('host'), t.get('port')
            if host and port:
                out = await loop.run_in_executor(None, self._execute_rcon_command_sync, host, port, command)
                results.append(f"【{t.get('name', '未知')}】\n{out}")
        return "\n\n".join(results)

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
            info = a2s.info((host, port), timeout=5.0)
            try:
                players = a2s.players((host, port), timeout=5.0)
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
        port = int(port_str)
        rcon_result = await self._query_via_rcon(host, port)
        if not rcon_result:
            return f"❌ ARK Status 查询失败，RCON 也失败" + FOOTER_ASA
        display_addr = direct_addr if direct_addr else rcon_addr
        custom_name = rcon_result.get('server_name', f"ZeroARK-{map_name}ASA")
        rcon_map = rcon_result.get('map_name', '')
        map_display = get_map_display(rcon_map if rcon_map else map_name, "ASA", lang)
        pnames = rcon_result.get('player_names', [])
        pcount = rcon_result.get('player_count', 0)
        maxp = rcon_result.get('max_players', 0)
        footer = FOOTER_ASA
        usage = self.usage_cache.get("ASA", "")
        lines = [
            f"🎮 服务器状态", f"📌 地址：{display_addr}", f"🟢 状态：在线",
            f"🌐 地图：{map_display}", f"👥 在线人数：{pcount} / {maxp or '?'}",
            f"🕹️ 服务器名称：{custom_name}", "📡 查询方式：RCON (ARK Status 回退)",
            "", "👥 在线玩家：", "  " + ("、".join(pnames[:20]) if pnames else "无"),
            "", "🔗 直连方式：", f"【控制台】open {display_addr}（按 Tab 或 ~ 打开控制台）",
            "⚠️ 请使用游戏端口（ASA默认7777）"
        ]
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
            await cur.close()
            conn.close()
            if row:
                cache[key] = {"sender": row[0], "tribe": row[1] or '', "map": row[2] or '', "time": row[3]}
        except Exception as e:
            logger.debug(f"部落信息查询失败 {game}/{pid}: {type(e).__name__}: {e}")
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
                lines.append(f"【{k}】{addr}（{len(players)} 人）")
                for i, pl in enumerate(players, 1):
                    pid = str(pl.get('id') or '')
                    if g == 'ASA':
                        pid = pid.lower()
                    info = await self._lookup_tribe(g, pid, cache) or {}
                    tribe = info.get('tribe') or ''
                    lastmap = info.get('map') or ''
                    bits = [f"部落：{tribe}" if tribe else "部落：未知（近期无聊天记录）"]
                    if lastmap:
                        bits.append(f"最近活动：{lastmap}")
                    mark = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"[i - 1] if 1 <= i <= 20 else f"{i}."
                    lines.append(f"  {mark} {pl.get('name')}  |  " + " | ".join(bits) + (f"  |  ID {pid}" if pid else ""))
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

    def _check_whitelist(self, event: AstrMessageEvent) -> bool:
        """白名单检查：主人（owner_qq）任何场景放行；私聊放行；群聊按白名单"""
        # 主人在任何场景（含私聊）都可使用全部指令
        owner_qq = str(self.config.get('owner_qq', '') or '')
        if owner_qq:
            try:
                sender_id = event.get_sender_id()
                if sender_id and str(sender_id) == owner_qq:
                    return True
            except Exception:
                pass

        if hasattr(event, "session_id") and "kook" in event.session_id.lower():
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
        owner_qq = str(self.config.get('owner_qq', ''))
        if sender_id != owner_qq:
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
                yield event.plain_result(f"📡 RCON 执行结果 ({t.get('name')}):\n{out}")
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
        owner_qq = str(self.config.get('owner_qq', ''))
        if str(sender_id) != owner_qq:
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
        yield event.plain_result(f"✅ 已在 {target.get('name')} 为{self._game_cn(game)}玩家 {pid} 加点 +{points}{verify}")

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
        if not qq or qq != str(self.config.get('owner_qq', '')):
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
                results.append(f"❌ @{tqq}：查询绑定失败，跳过")
                continue
            row = binds.get(game)
            if not row:
                results.append(f"⏭️ @{tqq}：未绑定{cn}，已跳过")
                continue
            pid = row['player_id']
            if not online:
                results.append(f"❌ @{tqq}：{cn}当前无在线服务器，未加点")
                continue
            command = cmd_tpl.format(id=pid, points=points)
            out = await self._exec_addpoints(online, command)
            low = out.lower()
            if out.startswith("❌") or "unknown" in low or "not found" in low:
                logger.error(f"代加点失败: qq={tqq} game={game} cmd={command} resp={out}")
                results.append(f"❌ @{tqq}：加点命令执行异常（{out[:60]}），未加点")
                continue
            logger.info(f"✅ 群聊代加点: 由owner为 qq={tqq} game={game} +{points} server={online.get('name')}")
            verify = await self._getpoints_text(online, pid) if cfg.get('verify_with_getpoints', True) else ""
            role = f"（{row['player_name']}）" if row.get('player_name') else ""
            results.append(f"✅ @{tqq}{role}：{cn} +{points} 已完成（{online.get('name')}）{verify}")
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
        lines = [
            "🪪 会话标识（用于 config.json 配置）",
            f"· 平台：{platform_name or '(未知)'}",
            f"· 你的ID（openid/QQ号）：{sender}",
            f"· 会话ID：{session_id}",
            f"· 群/频道标识：{group or '（私聊）'}",
            f"· member_openid：{raw_member or '（无）'}",
            f"· user_openid：{raw_user or '（无）'}",
            "",
            "对照填写：你的ID → owner_qq；群标识 → whitelist_groups / notify_group；",
            "玩家绑定主键即「你的ID」（QQ 官方机器人下为 openid，无法换成真实 QQ 号）。",
        ]
        yield event.plain_result("\n".join(lines))

    async def _test_push_cmd(self, event):
        """Owner 专用：让机器人在通知群主动发一条消息，验证官方机器人的主动发言权限/配额"""
        if not self._check_whitelist(event):
            return
        qq = self._sender_qq(event)
        if not qq or qq != str(self.config.get('owner_qq', '')):
            return
        group_id = self.config.get('notify_group')
        if not group_id:
            yield event.plain_result("❌ 未配置 notify_group")
            return
        ok = await self._send_group_msg(group_id, "🔔 测试推送：机器人主动消息通道正常（此消息为主动发送）")
        yield event.plain_result("✅ 已发送测试推送到通知群" if ok else "❌ 测试推送失败，请看日志（可能触发了主动消息配额/权限限制）")

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

    def _help_lines(self, is_owner_private: bool) -> list:
        """构建帮助文本（分组清晰；Owner 私聊额外显示管理指令）"""
        sc = self._signin_cfg()
        ase_pts = sc.get('ase_points', 50)
        asa_pts = sc.get('asa_points', 50)
        has_onebot = self._find_platform_inst('aiocqhttp') is not None
        lines = [
            "📖 ZeroARK 指令帮助（进化=ASE，飞升=ASA）",
            "",
            "【服务器查询】",
            "· /进化 或 /ase [地图名] → 进化(ASE)服务器；不带地图名=列出全部",
            "· /飞升 或 /asa [地图名] → 飞升(ASA)服务器；不带地图名=列出全部",
            "· /查服 或 /ark <IP:端口 或 地图名> [ASE|ASA] → 通用查询",
            "· /倍率 或 /rate → 当前动态倍率",
            "· /直连 或 /direct → 所有地图直连地址",
            "· /更新地址 或 /update_address → 手动刷新地址缓存",
            "",
            "【在线玩家】",
            "· /在线玩家 或 /players [进化|飞升] [地图名] → 在线玩家+部落名（不给版本=进化+飞升一起查）",
            "",
            "【账号绑定与签到】",
            "· /绑定 进化 <SteamID64> → 绑定进化账号（17位数字，7656119开头）",
            "· /绑定 飞升 <EOS ID> → 绑定飞升账号（32位hex）",
            "  （已绑定过其它账号时不能直接覆盖：换绑须走下面的“开绑”验证码流程，或先 /解绑）",
            "· /绑定 <进化|飞升> 开绑 → 生成绑定验证码，再回游戏公屏发 zsbind <验证码>",
            "· /解绑 <进化|飞升> → 解除该游戏绑定",
            "· /查绑定 或 /mybind → 查看我的绑定",
            f"· /签到 或 /signin → 每日签到（进化 +{ase_pts} / 飞升 +{asa_pts}，每天各一次；群内查不到绑定时请改私聊签到）",
            "",
            "【游戏内指令（在游戏公屏输入）】",
            "· zsbind <验证码> → 用 QQ 里“开绑”拿到的验证码完成绑定/换绑",
            "· qqbind <QQ号> → 仅 OneBot 渠道可用；QQ 官方机器人下请用上面的验证码流程",
            "· 商店指令（/points、/shop、/buy）由游戏内 ArkShop 提供，机器人不处理",
        ]
        if is_owner_private:
            lines += [
                "",
                "【管理员（仅 Owner 私聊）】",
                "· /rcon <ASE|ASA> <命令> → 对该版本全部服务器执行",
                "· /rcon <ASE|ASA> <地图名> <命令> → 对指定地图那一台执行",
                "· /rcon <目标名> <命令> → 对指定 RCON 目标执行",
                "· /加点 或 /addpoints <进化|飞升> <ID> <点数> → 加 ArkShop 点数（单台在线服一次，自动回读余额）",
                "· /代加点 或 /atpoints <进化|飞升> <点数> @群友… → 群聊中给已绑定的群友加点",
                "· /测试推送 或 /testpush → 在通知群主动发一条测试消息（验证主动消息权限/配额）",
            ]
        lines += [
            "",
            "【其它】",
            "· /我是谁 或 /whoami → 查看你的平台ID（openid/QQ号）与群标识（配置/排查用）",
            "· /帮助 或 /help → 显示本帮助",
            "· 群聊里请先 @机器人 再发指令；绑定主键是当前渠道的用户ID（QQ 官方机器人下为 openid）",
        ]
        if not has_onebot:
            # 未启用 OneBot 时，帮助里不出现 qqbind / OneBot 字样
            lines = [ln for ln in lines if 'OneBot' not in ln and 'qqbind' not in ln]
            lines = [ln.replace('绑定主键是当前渠道的用户ID（QQ 官方机器人下为 openid）',
                                '绑定主键是 openid（QQ 官方机器人无法获取真实 QQ 号）') for ln in lines]
        return lines

    @filter.command("help")
    async def help_command(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        owner_qq = str(self.config.get('owner_qq', ''))
        sender_id = event.get_sender_id()
        if not sender_id:
            try:
                sid = event.get_session_id()
                if sid and '_' in sid:
                    sp = sid.split('_')
                    if len(sp) > 1 and sp[1].isdigit():
                        sender_id = sp[1]
            except Exception:
                pass
        is_owner_private = bool(sender_id) and str(sender_id) == owner_qq and not self._event_group_id(event)
        yield event.plain_result("\n".join(self._help_lines(is_owner_private)) + self.footer)

    @filter.command("帮助")
    async def help_command_cn(self, event: AstrMessageEvent):
        if not self._check_whitelist(event):
            return
        async for result in self.help_command(event):
            yield result

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

    async def _ensure_qq_tables(self):
        """确保绑定/签到表存在（幂等），并自动迁移旧库：qq BIGINT → VARCHAR(64) 以支持 openid"""
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
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
                    day CHAR(10) NOT NULL,
                    points INT NOT NULL DEFAULT 0,
                    server_name VARCHAR(100) NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (qq, game, day)
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

    async def _get_bindings(self, qq) -> dict:
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

    async def _claim_checkin(self, qq, game, day, points, server_name) -> bool:
        """先占坑（(qq,game,day) 唯一键防并发/防重复）；返回 False 表示今天已签过或冲突"""
        conn = await self._qq_db()
        try:
            cur = await conn.cursor()
            try:
                await cur.execute(
                    "INSERT INTO qq_checkin (qq, game, day, points, server_name) VALUES (%s,%s,%s,%s,%s)",
                    (str(qq), game, day, int(points), (server_name or '')[:100]))
            except Exception:
                await conn.rollback()
                return False
            await conn.commit()
            await cur.close()
            return True
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
        """并发探测，返回该版本第一台响应 RCON 的在线服务器；无则返回 None"""
        targets = [t for t in (self.rcon_targets or [])
                   if str(t.get('name', '')).startswith(version + "-") and t.get('host') and t.get('port')]
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
        if await self._checkin_exists(qq, game, day):
            return f"ℹ️ {cn}今天已签到过，明天再来吧"
        target = await self._pick_online_rcon_target(game)
        if not target:
            return f"❌ {cn}当前没有在线服务器，本次未加点，请稍后重试"
        if not await self._claim_checkin(qq, game, day, points, str(target.get('name', ''))):
            return f"ℹ️ {cn}今天已签到过，明天再来吧"
        command = cmd_tpl.format(id=bind_row['player_id'], points=points)
        out = await self._exec_addpoints(target, command)
        low = out.lower()
        if out.startswith("❌") or "unknown" in low or "not found" in low:
            await self._revoke_checkin(qq, game, day)
            logger.error(f"签到加点失败: qq={qq} game={game} cmd={command} resp={out}")
            return f"❌ {cn}加点命令执行异常（{out[:80]}），已回滚可重新签到。请检查 config.json signin.{key_prefix}_cmd 命令模板"
        logger.info(f"✅ 签到加点成功: qq={qq} game={game} +{points} server={target.get('name')} cmd={command} resp={out[:60]}")
        verify = await self._getpoints_text(target, bind_row['player_id']) if cfg.get('verify_with_getpoints', True) else ""
        return f"✅ {cn}签到成功：已在 {target.get('name')} 加点 +{points} 点（ID: {bind_row['player_id'][:16]}）{verify}"

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
                if (self.config.get('game_bind') or {}).get('qq_cmd', True):
                    await self._bind_by_qq_direct(m.group(1), game, pid, sender, pmap)
                continue
            m = ZSBIND_RE.match(msg)
            if m:
                pend = self._pending_codes.get(m.group(1).lower())
                if not pend or pend.get('game') != game or time.time() > pend.get('expire', 0):
                    continue
                self._pending_codes.pop(m.group(1).lower(), None)  # 一次性
                await self._apply_bind(pend['qq'], game, pid, sender, pmap, source='游戏内验证码')
                continue

    async def _notify_bind_result(self, qq, text: str) -> bool:
        """优先私聊通知；私聊失败且开启群内兜底（game_bind.dm_fallback='@'）时，
        在通知群以文本公告播报（调用方必须保证 text 不含验证码等敏感内容）"""
        try:
            if await self._send_private_msg(qq, text):
                return True
        except Exception as e:
            logger.debug(f"绑定结果私聊发送异常: {e}")
        gb = self.config.get('game_bind') or {}
        if str(gb.get('dm_fallback', '@')).lower() in ('@', 'on', 'true', '1'):
            group_id = self.config.get('notify_group')
            if group_id:
                try:
                    ok = await self._send_group_msg(group_id, f"📢 [QQ:{qq}] {text}")
                    if ok:
                        logger.info(f"绑定结果私聊失败，已在群 {group_id} 公告给 QQ {qq}")
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
        await self._apply_bind(qq, game, pid, sender, pmap, source='游戏公屏QQ号')

    async def _apply_bind(self, qq, game, pid, sender, pmap, source=''):
        """写入绑定并私聊通知（验证码流程允许直接换绑）"""
        try:
            existing = (await self._get_bindings(qq)).get(game)
            await self._ensure_qq_tables()
            migrated = await self._claim_legacy_binding(qq, game, pid)
            await self._bind_upsert(qq, game, pid, sender, pmap)
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
            f"✅ {self._game_cn(game)}游戏内{verb}：QQ={qq} ↔ 角色「{sender}」（{pmap}），ID {pid}（来源：{source}）\n"
            f"现在可用 /签到 每日领取 {points} 点。{legacy_line}")

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
                                     "  进化(ASE)填 SteamID64（17位数字，7656119开头）\n"
                                     "  飞升(ASA)填 EOS ID（32位hex，如0002...）\n"
                                     "或游戏内绑定：\n"
                                     "  方式1：直接在游戏公屏发 qqbind <你的QQ号>（该QQ未绑过此游戏时）\n"
                                     "  方式2：/绑定 <进化|飞升> 开绑 → 验证码私发给你 → 游戏公屏发 zsbind <验证码>\n"
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
            self._pending_codes[code] = {'qq': qq, 'game': game, 'expire': time.time() + ttl}
            hint = f"在游戏（{self._game_cn(game)}）公屏输入：zsbind {code}"
            ok = await self._send_private_msg(
                qq,
                f"🎫 {self._game_cn(game)} 游戏内绑定验证码：{code}\n\n{hint}\n\n"
                f"有效期 {ttl} 秒、仅限一次，验证码只发给你本人请勿外传；若该游戏已绑过其它号，用验证码可直接换绑。")
            if not ok:
                self._pending_codes.pop(code, None)
                yield event.plain_result("❌ 验证码私发失败：机器人无法私聊到你。请先添加机器人为好友（若机器人侧有私聊白名单/陌生人限制，请把该QQ加入白名单）后重试；验证码不会发到群里以防冒绑。")
                return
            yield event.plain_result(f"🎫 {self._game_cn(game)} 开绑成功，验证码已私发给你（{ttl} 秒有效，请勿外传）。\n下一步：{hint}")
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
                f"🔒 你已经绑定过{self._game_cn(game)}（ID {cur_pid[:16]}…），换绑需要验证码：\n"
                f"· /绑定 {self._game_cn(game)} 开绑 → 验证码私发给你 → 游戏公屏发 zsbind <验证码>\n"
                f"· 或先 /解绑 {self._game_cn(game)}，再重新绑定")
            return
        info = await self._lookup_chat_player(game, pid)
        pname = info[0] if info else ''
        pmap = info[1] if info else ''
        try:
            await self._bind_upsert(qq, game, pid, pname, pmap)
        except Exception as e:
            yield event.plain_result(f"❌ 绑定写入失败: {e}")
            return
        extra = f"（角色：{pname} @ {pmap}）" if pname else "（⚠️ 该ID暂未在ZeroARK聊天记录中出现，请确认ID正确）"
        if existing:
            yield event.plain_result(f"ℹ️ {self._game_cn(game)}已绑定同一账号（ID {pid}），信息已刷新 {extra}")
        else:
            yield event.plain_result(f"✅ {self._game_cn(game)}绑定成功：QQ={qq} → {pid} {extra}")

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
        yield event.plain_result(f"✅ 已解绑{self._game_cn(game)}（QQ={qq}）" if ok else f"ℹ️ 你未绑定{self._game_cn(game)}")

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
            yield event.plain_result("ℹ️ 你还没有绑定任何游戏。\n用 /绑定 进化 <SteamID64> 或 /绑定 飞升 <EOS32位hex> 绑定"
                                     + LEGACY_BIND_HINT)
            return
        lines = [f"📋 QQ={qq} 的绑定："]
        for game in ("ASE", "ASA"):
            if game in binds:
                b = binds[game]
                lines.append(f"  {self._game_cn(game)}：{b['player_id']}"
                             + (f"（角色 {b['player_name']} @ {b['last_map']}）" if b.get('player_name') else ""))
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
                yield event.plain_result(
                    "ℹ️ 群里没有查到你的绑定。\n"
                    "请**私聊机器人**完成绑定与签到：\n"
                    "· /绑定 进化 <SteamID64>  或  /绑定 飞升 <EOS 32位hex>\n"
                    "· 之后在私聊发 /签到 即可\n"
                    "（群与私聊的用户标识可能不同，绑定/签到建议都在私聊完成；两边签到记录共用，同一天不会重复发点）"
                    + LEGACY_BIND_HINT)
            else:
                yield event.plain_result("ℹ️ 请先绑定游戏ID再签到：\n/bind 或 /绑定 进化 <SteamID64>\n/bind 或 /绑定 飞升 <EOS 32位hex>"
                                         + LEGACY_BIND_HINT)
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
        if not message or message.startswith('/'):
            return
        group_id = event.get_group_id()
        if not group_id:
            return  # 仅群聊消息转发到游戏，私聊不转发
        self._last_umo = event.unified_msg_origin
        if str(group_id) == str(self.config.get('notify_group')):
            self._notify_umo = event.unified_msg_origin
        sender_name = event.get_sender_name() or "QQ用户"
        logger.info(f"📨 收到群 {group_id} 消息: {sender_name}: {message}")

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

                # 5. 调用 LLM
                logger.info(f"🤖 LLM 回复触发: {message[:50]}...")
                reply = await self._call_llm(message)
                if reply:
                    await self._send_group_msg(group_id, reply)
                    logger.info(f"🤖 LLM 回复成功: {reply[:50]}...")

        # ---------- QQ → 游戏（RCON）转发（并发，避免单服超时阻塞整条链路） ----------
        prefix = self.config.get('qq_forward_prefix', '💬 [QQ群]')
        game_message = f"{prefix} {sender_name}: {message}"
        targets = [t for t in self.rcon_targets if t.get('host') and t.get('port')]
        if not targets:
            logger.warning("⚠️ 没有可用的 RCON 目标，无法转发消息到游戏")
            return
        await self._send_rcon_concurrent(targets, f"serverchat {game_message}")

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
