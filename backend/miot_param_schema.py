"""
从 Miot Spec v2 JSON 确定性提取 siid/piid 参数语义，并为 api_set 中的 XX 占位生成 param_schema。
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _is_placeholder(value: Any) -> bool:
    return value == "XX" or value == "xx"


def _label_from_option(opt: dict) -> str:
    return str(opt.get("desc_zh_cn") or opt.get("description") or opt.get("value", ""))


_UNIT_LABELS: Dict[str, str] = {
    "celsius": "摄氏度(℃)",
    "percentage": "百分比(%)",
    "seconds": "秒",
    "minutes": "分钟",
    "hours": "小时",
    "lux": "照度(lux)",
    "ppm": "ppm",
    "rgb": "RGB 颜色",
}

_FORMAT_LABELS: Dict[str, str] = {
    "bool": "布尔值（开/关）",
    "uint8": "无符号 8 位整数",
    "uint16": "无符号 16 位整数",
    "uint32": "无符号 32 位整数",
    "int8": "有符号 8 位整数",
    "int16": "有符号 16 位整数",
    "int32": "有符号 32 位整数",
    "float": "浮点数",
    "string": "字符串",
}

# Miot 常见服务/设备英文名 -> 中文（规格里常缺 desc_zh_cn）
_MIOT_NAME_LABELS: Dict[str, str] = {
    "air-conditioner": "空调",
    "air_conditioner": "空调",
    "washer": "洗衣机",
    "fan": "风扇",
    "light": "灯",
    "humidifier": "加湿器",
    "dehumidifier": "除湿机",
    "heater": "取暖器",
    "curtain": "窗帘",
    "vacuum": "扫地机",
    "robot-cleaner": "扫地机器人",
    "water-heater": "热水器",
    "fridge": "冰箱",
    "television": "电视",
    "speaker": "音箱",
}


def _normalize_value_range(value_range: Any) -> Optional[dict]:
    """Miot Spec 中 value-range 可能是 dict 或 [min, max, step] 数组。"""
    if isinstance(value_range, dict):
        return {
            "min": value_range.get("min"),
            "max": value_range.get("max"),
            "step": value_range.get("step", 1),
        }
    if isinstance(value_range, (list, tuple)) and len(value_range) >= 2:
        return {
            "min": value_range[0],
            "max": value_range[1],
            "step": value_range[2] if len(value_range) > 2 else 1,
        }
    return None


def _format_type_label(fmt: Optional[str], unit: Optional[str] = None) -> str:
    fmt_key = str(fmt or "").lower()
    type_label = _FORMAT_LABELS.get(fmt_key, fmt_key or "未知类型")
    if unit:
        unit_label = _UNIT_LABELS.get(str(unit).lower(), str(unit))
        return f"{type_label}，单位 {unit_label}"
    return type_label


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _humanize_miot_name(name: Optional[str]) -> str:
    """将 Miot 英文 kebab/snake 名转为中文标签（若可映射）。"""
    if not name:
        return ""
    raw = str(name).strip()
    if _contains_cjk(raw):
        return raw
    key = raw.lower().replace("_", "-")
    if key in _MIOT_NAME_LABELS:
        return _MIOT_NAME_LABELS[key]
    return ""


def _format_range_label(value_range: Optional[dict]) -> Optional[str]:
    if not isinstance(value_range, dict):
        return None
    min_v = value_range.get("min")
    max_v = value_range.get("max")
    step = value_range.get("step")
    if min_v is None and max_v is None:
        return None
    if min_v is not None and max_v is not None:
        text = f"取值范围 {min_v}～{max_v}"
    elif min_v is not None:
        text = f"最小值 {min_v}"
    else:
        text = f"最大值 {max_v}"
    if step not in (None, 0, 1, 1.0):
        text += f"，步长 {step}"
    return text


def _build_param_meaning(slot: dict) -> str:
    """根据属性/服务/设备描述生成参数语义说明。"""
    property_desc = slot.get("property_desc") or slot.get("property_name") or "该参数"
    service_label = _humanize_miot_name(slot.get("service_desc"))
    if not service_label:
        service_label = _humanize_miot_name(slot.get("device_desc"))
    if service_label:
        return f"用于调节{service_label}的{property_desc}"
    return f"用于设置设备的{property_desc}"


def build_nl_param_description(slot: dict) -> str:
    """
    为非枚举类参数生成自然语言描述，包含类型、范围（如有）与参数含义。
    """
    label = slot.get("property_desc") or slot.get("property_name") or slot.get("path") or "参数"
    parts: List[str] = [f"「{label}」"]

    value_type = slot.get("value_type")
    fmt = slot.get("format")
    if value_type == "unknown" and not fmt:
        type_text = "未知类型（文档中未找到对应属性定义）"
    else:
        type_text = _format_type_label(fmt, slot.get("unit"))
    if type_text:
        parts.append(f"类型为{type_text}")

    range_text = _format_range_label(slot.get("value_range"))
    if range_text:
        parts.append(range_text)

    if value_type == "unknown" and not slot.get("property_desc") and not slot.get("property_name"):
        siid, piid = slot.get("siid"), slot.get("piid")
        if siid is not None and piid is not None:
            parts.append(f"对应设备属性 siid={siid}、piid={piid}，请参照设备规格填写")
        else:
            parts.append("请参照设备规格文档填写具体数值")
    else:
        parts.append(_build_param_meaning(slot))
    return "，".join(parts) + "。"


def build_miot_param_index(api_doc: dict) -> Dict[Tuple[int, int], dict]:
    """
    解析 Miot Spec，建立 (siid, piid) -> 属性元数据 索引。
    """
    index: Dict[Tuple[int, int], dict] = {}
    if not isinstance(api_doc, dict):
        return index

    device_desc = (
        api_doc.get("desc_zh_cn")
        or _humanize_miot_name(api_doc.get("name"))
        or api_doc.get("description")
        or ""
    )

    services = api_doc.get("services") or {}
    if not isinstance(services, dict):
        return index

    for _svc_key, svc in services.items():
        if not isinstance(svc, dict):
            continue
        try:
            siid = int(svc.get("iid"))
        except (TypeError, ValueError):
            continue
        service_desc = (
            svc.get("desc_zh_cn")
            or _humanize_miot_name(svc.get("name"))
            or svc.get("description")
            or svc.get("name")
            or ""
        )

        properties = svc.get("properties") or {}
        if not isinstance(properties, dict):
            continue

        for _prop_key, prop in properties.items():
            if not isinstance(prop, dict):
                continue
            try:
                piid = int(prop.get("iid"))
            except (TypeError, ValueError):
                continue

            fmt = str(prop.get("format") or "")
            unit = prop.get("unit")
            property_name = prop.get("name") or prop.get("prop") or ""
            property_desc = prop.get("desc_zh_cn") or prop.get("description") or property_name

            entry: dict = {
                "siid": siid,
                "piid": piid,
                "property_name": property_name,
                "property_desc": property_desc,
                "service_desc": service_desc,
                "device_desc": device_desc,
                "format": fmt,
                "unit": unit,
            }

            value_list = prop.get("value-list") or prop.get("value_list")
            if isinstance(value_list, list) and value_list:
                options = []
                for opt in value_list:
                    if not isinstance(opt, dict):
                        continue
                    options.append(
                        {
                            "value": opt.get("value"),
                            "label_zh": opt.get("desc_zh_cn") or opt.get("description") or str(opt.get("value")),
                            "label_en": opt.get("description"),
                        }
                    )
                entry["value_type"] = "enum"
                entry["options"] = options
            elif fmt == "bool":
                entry["value_type"] = "bool"
                entry["options"] = [
                    {"value": True, "label_zh": "开", "label_en": "true"},
                    {"value": False, "label_zh": "关", "label_en": "false"},
                ]
            else:
                normalized_range = _normalize_value_range(prop.get("value-range") or prop.get("value_range"))
                if normalized_range is not None:
                    entry["value_type"] = "range"
                    entry["value_range"] = normalized_range
                else:
                    entry["value_type"] = "unknown"

            index[(siid, piid)] = entry

    return index


def _slot_from_index(path: str, siid: int, piid: int, meta: dict) -> dict:
    slot = {
        "path": path,
        "siid": siid,
        "piid": piid,
        "property_name": meta.get("property_name"),
        "property_desc": meta.get("property_desc"),
        "service_desc": meta.get("service_desc"),
        "device_desc": meta.get("device_desc"),
        "format": meta.get("format"),
        "unit": meta.get("unit"),
        "value_type": meta.get("value_type", "unknown"),
        "placeholder": "XX",
    }
    if meta.get("options"):
        slot["options"] = meta["options"]
    if meta.get("value_range"):
        slot["value_range"] = meta["value_range"]
    value_type = slot.get("value_type")
    if value_type != "enum":
        slot["nl_description"] = build_nl_param_description(slot)
    return slot


def build_param_schema(api_set: Any, api_doc: dict) -> Optional[dict]:
    """
    根据 api_set 中的 XX 占位与文档索引，生成 param_schema。
    按生态分派到 command_pipelines（MIoT / Google Home）。
    """
    from command_pipelines import get_pipeline

    return get_pipeline(api_doc=api_doc, api_set=api_set).build_param_schema(api_set, api_doc)


# 兼容旧导入：Google 实现已迁至 command_pipelines.google_home
def _is_google_home_api_doc(api_doc: Any) -> bool:
    from command_pipelines.google_home import is_google_home_api_doc

    return is_google_home_api_doc(api_doc)


def _api_set_looks_google(api_set: Any) -> bool:
    from command_pipelines.google_home import api_set_looks_google

    return api_set_looks_google(api_set)


def build_google_param_index(api_doc: dict) -> Dict[str, Dict[str, dict]]:
    from command_pipelines.google_home import build_google_param_index as _impl

    return _impl(api_doc)


def _build_google_param_schema(api_set: list, api_doc: dict) -> Optional[dict]:
    from command_pipelines.google_home import build_google_param_schema

    return build_google_param_schema(api_set, api_doc)


def enrich_commands_with_param_schema(commands: list, api_doc: dict) -> list:
    """为指令列表批量附加 param_schema（按文档生态分派）。"""
    from command_pipelines import get_pipeline

    return get_pipeline(api_doc=api_doc).enrich_commands(commands, api_doc)

def merge_effective_param_slots(
    param_schema: Optional[dict],
    param_details: Optional[dict] = None,
    preference_desc: Optional[str] = None,
) -> List[dict]:
    """
    合并客观 param_schema 与主观 param_details，生成填参视图。
    """
    if not param_schema or not isinstance(param_schema, dict):
        return []

    overrides = {}
    if isinstance(param_details, dict):
        overrides = param_details.get("slot_overrides") or {}

    result = []
    for slot in param_schema.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        path = slot.get("path")
        merged = dict(slot)
        ov = overrides.get(path) if path else None
        if isinstance(ov, dict):
            if ov.get("default_value") is not None:
                merged["default_value"] = ov["default_value"]
            if ov.get("preferred_options"):
                merged["preferred_options"] = ov["preferred_options"]
            if ov.get("user_note"):
                merged["user_note"] = ov["user_note"]

        hint_parts = []
        if merged.get("user_note"):
            hint_parts.append(str(merged["user_note"]))
        elif preference_desc:
            hint_parts.append(str(preference_desc))

        label = merged.get("property_desc") or merged.get("property_name") or path
        merged["label"] = label

        value_type = merged.get("value_type")
        if not merged.get("nl_description") and value_type != "enum":
            merged["nl_description"] = build_nl_param_description(merged)

        if hint_parts:
            merged["hint"] = "；".join(hint_parts)
        elif value_type == "enum":
            merged["hint"] = f"请选择{label}"
        else:
            merged["hint"] = merged.get("nl_description") or f"请填写{label}"

        merged["user_value"] = merged.get("default_value")
        result.append(merged)
    return result


def build_param_placeholders_from_schema(
    api_set: Any,
    param_schema: Optional[dict] = None,
    param_details: Optional[dict] = None,
    preference_desc: Optional[str] = None,
) -> List[dict]:
    """意图输出用：优先使用 param_schema，否则回退扫描 XX。"""
    slots = merge_effective_param_slots(param_schema, param_details, preference_desc)
    if slots:
        return [
            {
                "path": s.get("path"),
                "hint": s.get("hint") or s.get("nl_description") or "请填写具体参数值",
                "nl_description": s.get("nl_description"),
                "user_value": s.get("user_value"),
                "label": s.get("label"),
                "value_type": s.get("value_type"),
                "options": s.get("options"),
                "value_range": s.get("value_range"),
                "siid": s.get("siid"),
                "piid": s.get("piid"),
                "unit": s.get("unit"),
                "required": False if s.get("required") is False else True,
            }
            for s in slots
        ]

    placeholders = []

    def walk(node, path: str):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif _is_placeholder(node):
            placeholders.append(
                {
                    "path": path,
                    "hint": preference_desc or "请填写具体参数值",
                    "user_value": None,
                }
            )

    if isinstance(api_set, list):
        for i, item in enumerate(api_set):
            walk(item, f"api_set[{i}]")
    return placeholders


def enrich_param_schema_nl_descriptions(param_schema: Optional[dict]) -> Optional[dict]:
    """为已有 param_schema 中缺失 nl_description 的非枚举槽位补全自然语言描述。"""
    if not param_schema or not isinstance(param_schema, dict):
        return param_schema
    enriched = deepcopy(param_schema)
    for slot in enriched.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        if slot.get("value_type") != "enum" and not slot.get("nl_description"):
            slot["nl_description"] = build_nl_param_description(slot)
    return enriched


def param_schema_summary(param_schema: Optional[dict]) -> str:
    """供 L5 LLM 使用的短摘要。"""
    if not param_schema:
        return ""
    parts = []
    for slot in param_schema.get("slots") or []:
        label = slot.get("property_desc") or slot.get("property_name") or slot.get("path")
        if slot.get("value_type") == "enum" and slot.get("options"):
            opts = "、".join(
                f"{o.get('label_zh')}({o.get('value')})"
                for o in slot["options"][:8]
                if isinstance(o, dict)
            )
            if len(slot["options"]) > 8:
                opts += "…"
            parts.append(f"{label}: {opts}")
        elif slot.get("nl_description"):
            parts.append(str(slot["nl_description"]))
        else:
            desc = build_nl_param_description(slot)
            parts.append(desc if desc else str(label))
    return "；".join(parts)


def _parse_dot_path(path: str) -> List[Any]:
    """将 api_set[0].value 解析为 ['api_set', 0, 'value']。"""
    tokens: List[Any] = []
    i = 0
    while i < len(path):
        if path[i] == "[":
            end = path.index("]", i)
            tokens.append(int(path[i + 1 : end]))
            i = end + 1
        elif path[i] == ".":
            i += 1
        else:
            j = i
            while j < len(path) and path[j] not in ".[":
                j += 1
            tokens.append(path[i:j])
            i = j
    return tokens


def _set_value_by_path(root: Any, path: str, value: Any) -> None:
    tokens = _parse_dot_path(path)
    if not tokens:
        return
    cur = root
    for token in tokens[:-1]:
        cur = cur[token]
    cur[tokens[-1]] = value


def coerce_param_value(value: Any, value_type: Optional[str] = None, fmt: Optional[str] = None) -> Any:
    """按 Miot 类型将用户输入转为合适 Python 值。"""
    if value is None or value == "":
        return value
    if isinstance(value, bool):
        return value
    if value_type == "bool" or str(fmt or "").lower() == "bool":
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        text = str(value).strip().lower()
        if text in ("true", "1", "开", "on", "yes"):
            return True
        if text in ("false", "0", "关", "off", "no"):
            return False
        return value
    fmt_key = str(fmt or "").lower()
    if value_type == "range" or fmt_key in ("uint8", "uint16", "uint32", "int8", "int16", "int32"):
        try:
            num = float(str(value).strip())
            return int(num) if num.is_integer() else int(num)
        except (TypeError, ValueError):
            return value
    if fmt_key == "float":
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return value
    if value_type == "enum":
        try:
            if str(value).strip().lstrip("-").isdigit():
                return int(str(value).strip())
        except (TypeError, ValueError):
            pass
    return value


def inject_params_into_api_set(api_set: Any, fills: List[dict]) -> Tuple[Any, List[dict]]:
    """
    将用户填写的参数注入 api_set 副本。
    fills 每项需含 path、value，可选 value_type/format/label。
    返回 (注入后的 api_set, 实际应用的参数列表)。
    """
    wrapped = {"api_set": deepcopy(api_set)}
    applied: List[dict] = []
    for fill in fills or []:
        if not isinstance(fill, dict):
            continue
        path = fill.get("path")
        if not path:
            continue
        raw_val = fill.get("value")
        if raw_val is None or raw_val == "":
            continue
        coerced = coerce_param_value(raw_val, fill.get("value_type"), fill.get("format"))
        _set_value_by_path(wrapped, path, coerced)
        applied.append(
            {
                "path": path,
                "label": fill.get("label") or path,
                "value": coerced,
                "raw_value": raw_val,
                "value_type": fill.get("value_type"),
                "unit": fill.get("unit"),
            }
        )
    return wrapped["api_set"], applied
