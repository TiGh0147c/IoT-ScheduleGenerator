"""三级效果叶的环境对应组（执行主签名 / 连带 / 观察 / 禁标）。

related_o_ids / related_e_ids 由此反演写入环境目录，供匹配旁证。
Hang 先验只用 primary。送风没有独立效果叶，室内气流不得作为通风换气主签名。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROLE_PRIMARY = "primary"
ROLE_SIDE = "side"
ROLE_OBSERVE = "observe"
ROLE_FORBID = "forbid"
LINK_ROLES = (ROLE_PRIMARY, ROLE_SIDE, ROLE_OBSERVE)
ROLE_RANK = {ROLE_PRIMARY: 0, ROLE_OBSERVE: 1, ROLE_SIDE: 2, ROLE_FORBID: 3}

EFFECT_META: Dict[int, Dict[str, Any]] = {
    1: {"name": "制冷", "o_id": 1},
    11: {"name": "制热", "o_id": 1},
    12: {"name": "温度数据获取", "o_id": 1},
    13: {"name": "除湿", "o_id": 7},
    14: {"name": "加湿", "o_id": 7},
    15: {"name": "湿度数据获取", "o_id": 7},
    16: {"name": "通风换气", "o_id": 8},
    17: {"name": "香薰", "o_id": 8},
    18: {"name": "空气质量数据获取", "o_id": 8},
    2: {"name": "开关门", "o_id": 2},
    3: {"name": "贵重物品保管", "o_id": 2},
    4: {"name": "视频监控", "o_id": 3},
    5: {"name": "户外信息获取", "o_id": 3},
    6: {"name": "异常检测报警", "o_id": 4},
    7: {"name": "物品位置获取", "o_id": 4},
    8: {"name": "人体检测", "o_id": 5},
    9: {"name": "活动检测", "o_id": 5},
    10: {"name": "门窗状态获取", "o_id": 6},
    19: {"name": "洗衣", "o_id": 9},
    20: {"name": "干燥", "o_id": 9},
    21: {"name": "个人清洁", "o_id": 10},
    22: {"name": "扫地", "o_id": 10},
    23: {"name": "除尘", "o_id": 10},
    24: {"name": "冷藏", "o_id": 11},
    25: {"name": "冷冻", "o_id": 11},
    26: {"name": "消毒", "o_id": 11},
    27: {"name": "净水供应", "o_id": 12},
    28: {"name": "热水供应", "o_id": 12},
    29: {"name": "环境维护", "o_id": 13},
    30: {"name": "辅助工作", "o_id": 13},
    31: {"name": "烹饪器具", "o_id": 14},
    32: {"name": "咖啡制作", "o_id": 14},
    33: {"name": "宠物喂食", "o_id": 15},
    34: {"name": "植物种植", "o_id": 15},
    35: {"name": "环境杀菌", "o_id": 15},
    36: {"name": "宠物清洁", "o_id": 15},
    37: {"name": "鱼类饲养", "o_id": 15},
    38: {"name": "床上用品", "o_id": 16},
    39: {"name": "梳妆镜面", "o_id": 16},
    40: {"name": "沙发座椅", "o_id": 16},
    41: {"name": "物品存储", "o_id": 16},
    42: {"name": "照明", "o_id": 17},
    43: {"name": "灯具开关", "o_id": 17},
    44: {"name": "窗户开合", "o_id": 18},
    45: {"name": "窗帘开合", "o_id": 18},
    46: {"name": "亮度数据获取", "o_id": 19},
    47: {"name": "音频输出", "o_id": 20},
    48: {"name": "音频输入", "o_id": 20},
    49: {"name": "视频输出", "o_id": 21},
    50: {"name": "办公桌椅", "o_id": 22},
    51: {"name": "文件打印", "o_id": 22},
    52: {"name": "信息输入", "o_id": 22},
    53: {"name": "辅助设备", "o_id": 22},
    54: {"name": "时间数据获取", "o_id": 23},
    55: {"name": "日程提醒", "o_id": 23},
    56: {"name": "多功能", "o_id": 24},
    57: {"name": "血压检测", "o_id": 25},
    58: {"name": "睡眠质量检测", "o_id": 25},
    59: {"name": "体重检测", "o_id": 25},
    60: {"name": "体温检测", "o_id": 25},
    61: {"name": "综合参数检测", "o_id": 25},
    62: {"name": "运动", "o_id": 26},
    63: {"name": "按摩", "o_id": 26},
    64: {"name": "健身锻炼", "o_id": 26},
}


def _ref(key: str, polarity: str = "") -> Dict[str, str]:
    return {"match_key": key, "polarity": polarity}


def _combo(
    *,
    empty: bool = False,
    primary: Sequence[Tuple[str, str]] = (),
    side: Sequence[Tuple[str, str]] = (),
    observe: Sequence[Tuple[str, str]] = (),
    forbid: Sequence[str] = (),
    note: str = "",
) -> Dict[str, Any]:
    return {
        "empty": empty,
        "primary": [_ref(k, p) for k, p in primary],
        "side": [_ref(k, p) for k, p in side],
        "observe": [_ref(k, p) for k, p in observe],
        "forbid": list(forbid),
        "note": note,
    }


# e_id -> combo。空签叶 empty=True，不反演到 related_e_ids。
COMBOS: Dict[int, Dict[str, Any]] = {
    1: _combo(
        primary=[("air_temperature", "lower")],
        side=[("noise_level", "change"), ("air_circulation", "change")],
        forbid=("air_exchange", "fridge_temperature", "freezer_temperature", "convertible_temperature", "water_temperature", "cooking_temperature"),
        note="降低室内空气温度。送风/风扇不是本叶；气流只作风速连带。",
    ),
    11: _combo(
        primary=[("air_temperature", "raise")],
        side=[("noise_level", "change"), ("air_circulation", "change")],
        forbid=("contact_temperature", "water_temperature", "color_temperature"),
        note="向室内空气输出热量。接触面温度留给床品或个护。",
    ),
    12: _combo(
        observe=[("air_temperature", "observe")],
        forbid=("fridge_temperature", "freezer_temperature", "convertible_temperature", "water_temperature", "cooking_temperature", "body_temperature", "contact_temperature", "aquarium_temperature", "air_circulation"),
        note="只读室内空气温度。",
    ),
    13: _combo(
        primary=[("air_humidity", "lower")],
        side=[("noise_level", "change"), ("air_temperature", "change")],
        forbid=("dry_state", "laundry", "soil_moisture"),
        note="降低房间空气含水量。干衣不是本叶。",
    ),
    14: _combo(
        primary=[("air_humidity", "raise")],
        side=[("water_level", "change")],
        forbid=("soil_moisture", "laundry", "dry_state"),
        note="向空气加水汽。水位只连带，不作主效果。",
    ),
    15: _combo(
        observe=[("air_humidity", "observe")],
        forbid=("soil_moisture", "water_level"),
        note="只读房间相对湿度。",
    ),
    16: _combo(
        primary=[("air_exchange", "change")],
        side=[("noise_level", "change")],
        forbid=("air_circulation", "laundry", "cooking_fume"),
        note="室内外空气交换。送风/摆风/洗衣机新风去味不是本叶。",
    ),
    17: _combo(
        empty=True,
        forbid=("pm25", "tvoc", "hcho"),
        note="释放气味。目录无香味行，保持空签。",
    ),
    18: _combo(
        observe=[
            ("pm25", "observe"),
            ("pm10", "observe"),
            ("co2", "observe"),
            ("tvoc", "observe"),
            ("hcho", "observe"),
            ("smoke", "observe"),
            ("gas", "observe"),
        ],
        forbid=("noise_level",),
        note="读污染物/危险气体。净化执行没有独立叶子，开机本身不标。",
    ),
    2: _combo(
        primary=[("opening_state", "change"), ("passage_state", "change")],
        side=[("entrance", "")],
        observe=[("opening_state", "observe")],
        forbid=("video_feed", "curtain_position"),
        note="门体开闭与放行。门锁读门状态用门窗开合，不要抢走开关门。",
    ),
    3: _combo(
        primary=[("safe_state", "change")],
        side=[("storage_space", "")],
        observe=[("safe_state", "observe")],
        forbid=("opening_state", "video_feed"),
        note="防非法开启的存放，不是频繁通行。",
    ),
    4: _combo(
        primary=[("video_feed", "start")],
        side=[("visible_space", "")],
        observe=[("video_feed", "observe")],
        forbid=("illuminance", "outdoor", "light_brightness"),
        note="室内或指定区域画面采集。不要标成照度。",
    ),
    5: _combo(
        primary=[("video_feed", "start"), ("outdoor", "")],
        side=[("visible_space", ""), ("occupancy", "")],
        observe=[("video_feed", "observe")],
        note="门外/入口来访画面。开锁动作不要挂成本叶。",
    ),
    6: _combo(
        primary=[("anomaly_event", "start"), ("protection_state", "change")],
        side=[("smoke", ""), ("gas", ""), ("reminder", "")],
        observe=[("smoke", "observe"), ("gas", "observe")],
        forbid=("illuminance",),
        note="异常告警。消音/自检空签；烟雾燃气仅探测器通道。",
    ),
    7: _combo(
        primary=[("bound_item", "")],
        observe=[("location", "observe")],
        forbid=("occupancy", "opening_state"),
        note="防丢器定位绑定物。",
    ),
    8: _combo(
        observe=[("occupancy", "observe")],
        forbid=("occupancy_motion",),
        note="有人/无人。灵敏度等参数不标。",
    ),
    9: _combo(
        observe=[("occupancy_motion", "observe")],
        side=[("occupancy", "observe")],
        forbid=("video_feed",),
        note="移动/体动，可与有人并存。",
    ),
    10: _combo(
        observe=[("opening_state", "observe")],
        forbid=("curtain_position",),
        note="感知门窗开闭。执行开窗走窗户开合。",
    ),
    19: _combo(
        primary=[("laundry", "process"), ("wash_state", "start")],
        side=[("water_temperature", "set")],
        forbid=("tableware", "dry_state", "air_exchange"),
        note="水洗衣物。洗碗机是辅助工作；筒清洁不要标衣物。",
    ),
    20: _combo(
        primary=[("laundry", "process"), ("footwear", "process"), ("dry_state", "start")],
        side=[("drying_temperature", "set")],
        forbid=("air_humidity", "air_exchange"),
        note="去衣物或鞋类水分，不是房间除湿。",
    ),
    21: _combo(
        primary=[("body_interaction", "process")],
        side=[("waste_handling", ""), ("contact_temperature", "set"), ("water_temperature", "set")],
        forbid=("laundry", "wash_state", "air_temperature"),
        note="如厕、口腔、毛发等个体卫生。清洗状态不要当马桶主签。",
    ),
    22: _combo(
        primary=[("floor", "process"), ("cleaning", "start")],
        forbid=("laundry", "surface", "cleanliness_state"),
        note="清扫地面。不要同时标清洁与清洁状态。",
    ),
    23: _combo(
        primary=[("cleaning", "start"), ("floor", "process"), ("surface", "process")],
        side=[("noise_level", "change")],
        forbid=("laundry", "cooking_fume"),
        note="吸尘除尘，地面或台面。",
    ),
    24: _combo(
        primary=[("fridge_temperature", "set")],
        side=[("food", "process"), ("storage", "")],
        observe=[("fridge_temperature", "observe")],
        forbid=("air_temperature", "freezer_temperature", "convertible_temperature"),
        note="低温不结冰保存。变温室不要默认本叶。",
    ),
    25: _combo(
        primary=[("freezer_temperature", "set"), ("freezing_state", "start")],
        side=[("food", "process"), ("storage", "")],
        observe=[("freezer_temperature", "observe")],
        forbid=("air_temperature", "fridge_temperature", "convertible_temperature"),
        note="冻结保存。变温看设定区间，不要默认冷冻。",
    ),
    26: _combo(
        primary=[("tableware", "process"), ("sterile_state", "start")],
        side=[("storage", "")],
        forbid=("illuminance", "laundry", "cleanliness_state"),
        note="对存放物杀菌。紫外不是照度。",
    ),
    27: _combo(
        primary=[("water_source", "process"), ("tds_out", ""), ("tds_in", ""), ("water_quality", "")],
        side=[("water_level", "change")],
        observe=[("tds_out", "observe"), ("tds_in", "observe"), ("water_quality", "observe"), ("water_level", "observe")],
        forbid=("water_temperature", "air_humidity"),
        note="过滤软化。主签名是 TDS/水质，水温留给热水供应。",
    ),
    28: _combo(
        primary=[("water_source", "process"), ("water_temperature", "raise")],
        side=[("beverage", "process")],
        observe=[("water_temperature", "observe")],
        forbid=("air_temperature", "air_exchange"),
        note="把水加热到可用温度。零冷水循环不是换气。",
    ),
    29: _combo(
        primary=[("cooking_fume", "lower"), ("kitchen_waste", "process")],
        side=[("noise_level", "change")],
        observe=[("cooking_fume", "observe")],
        forbid=("air_circulation", "light_brightness", "cooking_scene"),
        note="排油烟或处理厨余，二者按设备互斥。风机档位可连带油烟。",
    ),
    30: _combo(
        primary=[("tableware", "process"), ("wash_state", "start"), ("ingredient", "process"), ("food_prep", "start"), ("mass", "observe")],
        side=[("water_temperature", "set")],
        observe=[("mass", "observe")],
        forbid=("laundry",),
        note="洗碗、榨汁、称重。洗碗机是餐具+清洗状态，不是洗衣。",
    ),
    31: _combo(
        primary=[("cooking_scene", "process")],
        side=[("ingredient", ""), ("food", ""), ("cooking_temperature", "set")],
        observe=[("cooking_temperature", "observe")],
        forbid=("air_temperature",),
        note="加热蒸煮炸烤。养生壶冲奶更偏水温+饮品。",
    ),
    32: _combo(
        primary=[("beverage", "process")],
        side=[("water_temperature", "set"), ("cooking_scene", "")],
        forbid=("cooking_temperature",),
        note="咖啡饮品流程。冲煮用水温优于腔体烹饪温度。",
    ),
    33: _combo(
        primary=[("pet", "process"), ("feeding", "start")],
        side=[("water_level", "change")],
        observe=[("water_level", "observe")],
        forbid=("body_interaction", "cooking_scene"),
        note="按时定量喂食饮水。",
    ),
    34: _combo(
        primary=[("plant", "process"), ("planting", "start")],
        side=[("soil_moisture", "set"), ("water_level", "change"), ("aquarium_temperature", "set")],
        observe=[("soil_moisture", "observe"), ("aquarium_temperature", "observe"), ("water_level", "observe")],
        forbid=("air_humidity",),
        note="家庭种植器。空气湿度不能代替土壤湿度。",
    ),
    35: _combo(
        primary=[("sterile_state", "start")],
        side=[("pet", "")],
        forbid=("illuminance", "tableware"),
        note="降低宠物活动环境病原。紫外严禁标照度。",
    ),
    36: _combo(
        primary=[("pet", "process"), ("waste_handling", "")],
        side=[("drying_temperature", "set"), ("dry_state", "start")],
        forbid=("laundry", "air_humidity"),
        note="宠物本体清洁或猫砂处理。不要借衣物叶。",
    ),
    37: _combo(
        primary=[("pet", "process"), ("feeding", ""), ("aquarium_temperature", "set")],
        side=[("water_level", "change")],
        observe=[("aquarium_temperature", "observe"), ("water_level", "observe")],
        forbid=("water_temperature", "air_temperature"),
        note="鱼缸水体环境。洗浴水温不要标进来。",
    ),
    38: _combo(
        primary=[("contact_temperature", "set")],
        side=[("occupancy", "observe")],
        observe=[("contact_temperature", "observe")],
        forbid=("air_temperature",),
        note="睡眠家具。电热毯只有档位则空签温度。",
    ),
    39: _combo(
        empty=True,
        side=[("light_brightness", "set")],
        forbid=("illuminance",),
        note="梳妆镜。有灯再借用光源亮度，不要新建镜面环境。",
    ),
    40: _combo(
        empty=True,
        forbid=("air_temperature",),
        note="座椅承载。按摩沙发才借用按摩，不要为沙发发明环境行。",
    ),
    41: _combo(
        primary=[("storage_space", "change")],
        forbid=("safe_state",),
        note="床头柜等收纳。保险箱走贵重物品保管。",
    ),
    42: _combo(
        primary=[("light_brightness", "set"), ("color_temperature", "set"), ("light_color", "set")],
        forbid=("illuminance",),
        note="光源持续发光或场景光。空间 lux 不是本叶。",
    ),
    43: _combo(
        empty=True,
        side=[("light_brightness", "set")],
        forbid=("illuminance",),
        note="开/关灯。写入 brightness 才标光源亮度。",
    ),
    44: _combo(
        primary=[("opening_state", "change")],
        side=[("air_exchange", "change"), ("outdoor_illuminance", "observe")],
        forbid=("illuminance", "curtain_position"),
        note="执行开窗。空气交换只作连带，主叶仍是开合。",
    ),
    45: _combo(
        primary=[("curtain_position", "set")],
        observe=[("curtain_position", "observe")],
        forbid=("illuminance", "opening_state"),
        note="遮挡自然光，不改窗户。",
    ),
    46: _combo(
        observe=[("illuminance", "observe"), ("outdoor_illuminance", "observe")],
        forbid=("light_brightness", "curtain_position"),
        note="空间 lux 传感器。灯亮度百分比不是本叶。",
    ),
    47: _combo(
        primary=[("media_output", "start"), ("sound", "start")],
        forbid=("noise_level",),
        note="把声音播放出来。音量不是环境噪声。",
    ),
    48: _combo(
        primary=[("media_input", "start"), ("sound", "start")],
        forbid=("noise_level",),
        note="采集外部声音。",
    ),
    49: _combo(
        primary=[("visual", "start"), ("media_output", "start")],
        forbid=("visible_space", "illuminance", "video_feed"),
        note="电视/投影显示，不是摄像头采集。",
    ),
    50: _combo(empty=True, note="升降桌等物理支撑。高度是参数，无对应环境量。"),
    51: _combo(primary=[("document", "start")], note="数字到纸。"),
    52: _combo(empty=True, note="手写板等非键盘输入，可保持空签。"),
    53: _combo(
        empty=True,
        forbid=("air_temperature",),
        note="散热背夹等。散热辅助已停用，不要抽成室温。",
    ),
    54: _combo(
        observe=[("time", "observe")],
        forbid=("reminder",),
        note="读当前时间。设备预约倒计时不要标成本叶。",
    ),
    55: _combo(
        primary=[("reminder", "start"), ("time", "set")],
        forbid=("anomaly_event",),
        note="到点提醒，不是安防告警。",
    ),
    56: _combo(empty=True, note="融合形态过粗。不要启用已停用的机器人总称环境。"),
    57: _combo(
        observe=[("vitals", "observe")],
        forbid=("air_temperature",),
        note="采集血压。体征总称即可。",
    ),
    58: _combo(
        observe=[("vitals", "observe")],
        side=[("occupancy", "observe")],
        forbid=("air_temperature",),
        note="评估睡眠。在床占用可连带。",
    ),
    59: _combo(
        observe=[("mass", "observe"), ("vitals", "observe")],
        note="人体体重。厨房秤走辅助工作。",
    ),
    60: _combo(
        observe=[("body_temperature", "observe"), ("vitals", "observe")],
        forbid=("air_temperature", "contact_temperature"),
        note="人体体温。不要标成室内气温。",
    ),
    61: _combo(
        observe=[("vitals", "observe")],
        side=[("exercise", "observe"), ("body_temperature", "observe")],
        note="手环手表多维体征。停用总称环境保持停用。",
    ),
    62: _combo(
        primary=[("exercise", "start")],
        note="步行/跑步类有氧。与健身锻炼共用环境量，靠叶子区分。",
    ),
    63: _combo(
        primary=[("massage", "start")],
        side=[("body_interaction", "")],
        forbid=("exercise",),
        note="机械放松刺激。",
    ),
    64: _combo(
        primary=[("exercise", "start")],
        note="力量或专项训练。走步机不要挂成本叶。",
    ),
}

# 有对象旁证、但不默认挂到效果叶的环境量
ENV_LINK_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "convertible_temperature": {"o_ids": [11], "e_ids": [], "roles": {}},
    "cleanliness_state": {"o_ids": [10], "e_ids": [], "roles": {}},
}


def combo_of(e_id: int) -> Dict[str, Any]:
    return COMBOS.get(int(e_id)) or _combo(empty=True, note="尚未定义对应组。")


@lru_cache(maxsize=1)
def inverted_links() -> Dict[str, Dict[str, Any]]:
    """match_key -> related_o_ids / related_e_ids / roles[e_id]=role。不含 forbid。"""
    out: Dict[str, Dict[str, Any]] = {}
    for e_id, combo in COMBOS.items():
        o_id = int(EFFECT_META[e_id]["o_id"])
        for role in LINK_ROLES:
            if combo.get("empty") and role == ROLE_PRIMARY:
                continue
            for ref in combo.get(role) or []:
                key = str(ref.get("match_key") or "").strip()
                if not key:
                    continue
                slot = out.setdefault(key, {"o_ids": [], "e_ids": [], "roles": {}})
                prev = slot["roles"].get(e_id)
                if prev is None or ROLE_RANK[role] < ROLE_RANK[prev]:
                    slot["roles"][e_id] = role
                if e_id not in slot["e_ids"]:
                    slot["e_ids"].append(e_id)
                if o_id not in slot["o_ids"]:
                    slot["o_ids"].append(o_id)
    for key, slot in list(out.items()):
        slot["e_ids"] = sorted(slot["e_ids"])
        slot["o_ids"] = sorted(slot["o_ids"])
    for key, override in ENV_LINK_OVERRIDES.items():
        out[key] = {
            "o_ids": list(override.get("o_ids") or []),
            "e_ids": list(override.get("e_ids") or []),
            "roles": dict(override.get("roles") or {}),
        }
    return out


def related_ids_for_key(match_key: str, o_ids: Sequence[int], e_ids: Sequence[int]) -> Tuple[List[int], List[int]]:
    key = str(match_key or "").strip()
    if not key:
        return list(o_ids), list(e_ids)
    hit = inverted_links().get(key)
    if hit is None:
        return list(o_ids), list(e_ids)
    return list(hit["o_ids"]), list(hit["e_ids"])


def hang_effect_priors_by_key() -> Dict[str, Tuple[str, ...]]:
    """环境主键 → 效果名（仅 primary，供 hang L3 提示）。"""
    acc: Dict[str, List[str]] = {}
    for e_id, combo in COMBOS.items():
        if combo.get("empty"):
            continue
        name = str(EFFECT_META[e_id]["name"])
        for ref in combo.get(ROLE_PRIMARY) or []:
            key = str(ref.get("match_key") or "").strip()
            if not key:
                continue
            names = acc.setdefault(key, [])
            if name not in names:
                names.append(name)
    return {key: tuple(names) for key, names in acc.items()}


def role_for_env_effect(match_key: str, e_id: int) -> Optional[str]:
    key = str(match_key or "").strip()
    if not key:
        return None
    return inverted_links().get(key, {}).get("roles", {}).get(int(e_id))


def _env_lookup(env_rows: Optional[Sequence[Mapping[str, Any]]]) -> Dict[str, Mapping[str, Any]]:
    by_key: Dict[str, Mapping[str, Any]] = {}
    for row in env_rows or []:
        key = str(row.get("match_key") or "").strip()
        if key and key not in by_key:
            by_key[key] = row
    return by_key


def _item_from_ref(ref: Mapping[str, str], role: str, by_key: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    key = str(ref.get("match_key") or "").strip()
    row = by_key.get(key) or {}
    env_id = row.get("env_id")
    try:
        env_id_int = int(env_id) if env_id is not None else None
    except (TypeError, ValueError):
        env_id_int = None
    return {
        "env_id": env_id_int,
        "env_name": str(row.get("env_name") or key),
        "match_key": key,
        "role": role,
        "polarity": str(ref.get("polarity") or ""),
    }


def resolve_effect_combo(e_id: int, env_rows: Optional[Sequence[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    combo = combo_of(e_id)
    by_key = _env_lookup(env_rows)
    items: List[Dict[str, Any]] = []
    for role in (ROLE_PRIMARY, ROLE_SIDE, ROLE_OBSERVE):
        for ref in combo.get(role) or []:
            items.append(_item_from_ref(ref, role, by_key))
    for key in combo.get("forbid") or []:
        items.append(_item_from_ref({"match_key": key, "polarity": ""}, ROLE_FORBID, by_key))
    return {
        "empty": bool(combo.get("empty")),
        "note": str(combo.get("note") or ""),
        "items": items,
    }


def _merge_combos(
    combos: Iterable[Mapping[str, Any]],
    *,
    include_forbid: bool,
    note: str,
) -> Dict[str, Any]:
    rows = list(combos)
    acc: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for combo in rows:
        for item in combo.get("items") or []:
            role = str(item.get("role") or "")
            if role == ROLE_FORBID and not include_forbid:
                continue
            key = (str(item.get("match_key") or ""), role)
            if key not in acc:
                acc[key] = dict(item)
                continue
            old = str(acc[key].get("polarity") or "")
            new = str(item.get("polarity") or "")
            parts = [p for p in (old.split("/") if old else []) + ([new] if new else []) if p]
            acc[key]["polarity"] = "/".join(list(dict.fromkeys(parts)))
    items = sorted(
        acc.values(),
        key=lambda it: (ROLE_RANK.get(str(it.get("role")), 9), str(it.get("env_name") or "")),
    )
    empty = bool(rows) and all(bool(c.get("empty")) and not [
        i for i in (c.get("items") or []) if i.get("role") != ROLE_FORBID
    ] for c in rows)
    if not rows:
        empty = True
    return {"empty": empty, "note": note, "items": items}


def resolve_ontology_combos(
    *,
    domains: Sequence[Mapping[str, Any]],
    objects: Sequence[Mapping[str, Any]],
    effects: Sequence[Mapping[str, Any]],
    env_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    effect_combos = {int(e["e_id"]): resolve_effect_combo(int(e["e_id"]), env_rows) for e in effects}
    by_object: Dict[int, List[int]] = {}
    for e in effects:
        by_object.setdefault(int(e["o_id"]), []).append(int(e["e_id"]))
    object_combos: Dict[int, Dict[str, Any]] = {}
    for obj in objects:
        o_id = int(obj["o_id"])
        object_combos[o_id] = _merge_combos(
            [effect_combos[eid] for eid in by_object.get(o_id, []) if eid in effect_combos],
            include_forbid=False,
            note="下属效果叶的环境并集。空签叶不贡献主签名。",
        )
    by_domain: Dict[int, List[int]] = {}
    for obj in objects:
        by_domain.setdefault(int(obj["d_id"]), []).append(int(obj["o_id"]))
    domain_combos: Dict[int, Dict[str, Any]] = {}
    for domain in domains:
        d_id = int(domain["d_id"])
        domain_combos[d_id] = _merge_combos(
            [object_combos[oid] for oid in by_domain.get(d_id, []) if oid in object_combos],
            include_forbid=False,
            note="下属对象的环境并集，用于族类收窄，不单独生成 env_impact。",
        )
    return domain_combos, object_combos, effect_combos
