"""意图寻址 L4/L5 适配：配方展开、参数挂槽、口语枚举绑定、环境加权。"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from miot_param_schema import build_param_placeholders_from_schema, enrich_param_schema_nl_descriptions

_API_INDEX_RE = re.compile(r"^api_set\[(\d+)\](.*)$")
_MEASURE_RE = re.compile(
    r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)\s*(摄氏度|℃|°c|°C|度|转|rpm|％|%)?",
    re.I,
)
_CLAUSE_SPLIT_RE = re.compile(r"[，。；！？\n]")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_NUMBER_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?$")
_GENERIC_TOKENS = {
    "设置",
    "模式",
    "目标",
    "温度",
    "开启",
    "打开",
    "执行",
    "设备",
    "开始",
    "进行",
    "占位",
    "具体",
    "参数",
}

_OPTIONAL_STEP_ROLES = {"parameter"}
_LAZY_EXPOSURES = {"lazy"}

# 口语种子。不要用单独的「度」，否则会误伤「湿度」。
_ENV_INTENT_KEYS = (
    (("凉快", "降温", "制冷", "制热", "暖和", "温度", "℃", "冷气", "暖气", "几度", "多少度"), "air_temperature"),
    (("湿度", "除湿", "潮湿", "回潮"), "air_humidity"),
)
_OBSERVE_INTENT_HINTS = ("看看", "查看", "多少", "读取", "查询", "数据获取", "现在几度", "几度了", "测一下")
_SKIP_ENV_ROLES = {"parameter", "auxiliary"}
_SKIP_ENV_KINDS = {"parameter", "auxiliary"}


def payload_as_dict(payload: Any) -> dict:
    if isinstance(payload, dict):
        interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
        return {
            "uid": payload.get("uid"),
            "c_instance_id": payload.get("c_instance_id"),
            "e_id": payload.get("e_id"),
            "api_set": payload.get("api_set"),
            "param_schema": payload.get("param_schema"),
            "capability_kind": payload.get("capability_kind") or "",
            "capability_desc": payload.get("capability_desc"),
            "supports_e_ids": list(payload.get("supports_e_ids") or []),
            "env_impact": list(payload.get("env_impact") or []),
            "interpretation": interp,
        }
    interp = getattr(payload, "interpretation", None)
    if not isinstance(interp, dict):
        interp = {}
    return {
        "uid": getattr(payload, "uid", None),
        "c_instance_id": getattr(payload, "c_instance_id", None),
        "e_id": getattr(payload, "e_id", None),
        "api_set": getattr(payload, "api_set", None),
        "param_schema": getattr(payload, "param_schema", None),
        "capability_kind": getattr(payload, "capability_kind", None) or "",
        "capability_desc": getattr(payload, "capability_desc", None),
        "supports_e_ids": list(getattr(payload, "supports_e_ids", None) or []),
        "env_impact": list(getattr(payload, "env_impact", None) or []),
        "interpretation": interp,
    }


def recipe_as_dict(recipe: Any) -> dict:
    if isinstance(recipe, dict):
        extra = recipe.get("extra") if isinstance(recipe.get("extra"), dict) else {}
        return {
            "recipe_uid": recipe.get("recipe_uid"),
            "c_instance_id": recipe.get("c_instance_id"),
            "recipe_name": recipe.get("recipe_name"),
            "covers_effects": list(recipe.get("covers_effects") or []),
            "steps": list(recipe.get("steps") or []),
            "extra": extra,
        }
    extra = getattr(recipe, "extra", None)
    if not isinstance(extra, dict):
        extra = {}
    return {
        "recipe_uid": getattr(recipe, "recipe_uid", None),
        "c_instance_id": getattr(recipe, "c_instance_id", None),
        "recipe_name": getattr(recipe, "recipe_name", None),
        "covers_effects": list(getattr(recipe, "covers_effects", None) or []),
        "steps": list(getattr(recipe, "steps", None) or []),
        "extra": extra,
    }


def _as_int_set(raw) -> Set[int]:
    out: Set[int] = set()
    for x in raw or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _pref_weight(pref: Any) -> int:
    if pref is None:
        return 0
    if isinstance(pref, dict):
        raw = pref.get("weight")
    else:
        raw = getattr(pref, "weight", 0)
    try:
        return int(raw if raw is not None else 0)
    except (TypeError, ValueError):
        return 0


def _pref_desc(pref: Any) -> str:
    if pref is None:
        return ""
    if isinstance(pref, dict):
        return str(pref.get("preference_desc") or "")
    return str(getattr(pref, "preference_desc", None) or "")


def _pref_details(pref: Any) -> Optional[dict]:
    if pref is None:
        return None
    if isinstance(pref, dict):
        details = pref.get("param_details")
    else:
        details = getattr(pref, "param_details", None)
    return details if isinstance(details, dict) else None


def payload_exposure(payload: dict) -> str:
    interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    return str(interp.get("exposure") or payload.get("exposure") or "").strip()


def payload_specializes_uid(payload: dict) -> str:
    interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    return str(interp.get("specializes_uid") or payload.get("specializes_uid") or "").strip()


def payload_is_l5_visible(payload: dict) -> bool:
    interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    if interp.get("l5_visible") is False:
        return False
    if payload_exposure(payload) in _LAZY_EXPOSURES:
        return False
    return True


def is_pref_eligible_payload(payload: Any) -> bool:
    """效果原子或场景策略且 L5 可见：懒人程序 / 参数 / 辅助不参与指令偏好默认池。"""
    data = payload_as_dict(payload)
    kind = str(data.get("capability_kind") or "").strip()
    if kind in {"parameter", "auxiliary"}:
        return False
    if kind == "strategy":
        return payload_is_l5_visible(data)
    if data.get("e_id") is None:
        return False
    return payload_is_l5_visible(data)


def strategy_named_in_intent(payload: dict, intent_text: str) -> bool:
    """点名门：用户话里点到自动/睡眠/喜好或 possible_intents，不单靠「模式」。"""
    text = str(intent_text or "").replace(" ", "")
    if not text:
        return False
    interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    phrases = []
    for raw in interp.get("possible_intents") or []:
        phrase = str(raw or "").replace(" ", "")
        if phrase:
            phrases.append(phrase)
    uid = str(payload.get("uid") or "")
    action = uid.split("：", 1)[-1] if "：" in uid else uid
    action = action.replace(" ", "")
    if action:
        phrases.append(action)
    for phrase in phrases:
        if phrase and phrase in text:
            return True
    blob = " ".join(
        [
            uid,
            action,
            str(payload.get("capability_desc") or ""),
            " ".join(phrases),
            str(interp.get("strategy_subtype") or ""),
        ]
    )
    for token in ("自动", "睡眠", "助眠", "喜好", "夜间", "diy"):
        if token in text and token in blob:
            return True
    return False


def _recipe_has_strategy_step(recipe: dict, payload_by_uid: Dict[str, dict]) -> bool:
    for step in recipe.get("steps") or []:
        if str(step.get("role") or "") == "strategy":
            return True
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if payload and str(payload.get("capability_kind") or "") == "strategy":
            return True
    return False


def strategy_recipe_named(recipe: dict, payload_by_uid: Dict[str, dict], intent_text: str) -> bool:
    name = str(recipe.get("recipe_name") or "").replace(" ", "")
    text = str(intent_text or "").replace(" ", "")
    if name and text and name in text:
        return True
    for step in recipe.get("steps") or []:
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if not payload:
            continue
        if str(payload.get("capability_kind") or "") != "strategy" and str(step.get("role") or "") != "strategy":
            continue
        if strategy_named_in_intent(payload, intent_text):
            return True
    return False


def remap_api_set_path(path: str, offset: int) -> str:
    text = str(path or "")
    matched = _API_INDEX_RE.match(text)
    if not matched or offset == 0:
        return text
    return f"api_set[{int(matched.group(1)) + offset}]{matched.group(2)}"


def _api_len(api_set: Any) -> int:
    return len(api_set) if isinstance(api_set, list) else 0


def merge_step_payloads(steps: List[dict], payload_by_uid: Dict[str, dict]) -> Optional[dict]:
    """按配方步骤顺序拼接 api_set，并重映射 param_schema 路径。"""
    merged_api: List[Any] = []
    merged_slots: List[dict] = []
    offset = 0
    step_meta: List[dict] = []
    for step in steps:
        uid = str(step.get("uid") or "")
        payload = payload_by_uid.get(uid)
        if not payload:
            return None
        api_set = payload.get("api_set")
        chunk = copy.deepcopy(api_set) if isinstance(api_set, list) else []
        role = str(step.get("role") or "")
        required = role not in _OPTIONAL_STEP_ROLES
        schema = payload.get("param_schema") if isinstance(payload.get("param_schema"), dict) else {}
        for slot in schema.get("slots") or []:
            if not isinstance(slot, dict):
                continue
            new_slot = copy.deepcopy(slot)
            new_slot["path"] = remap_api_set_path(str(slot.get("path") or ""), offset)
            new_slot["required"] = bool(slot.get("required", required))
            if not required:
                new_slot["required"] = False
            merged_slots.append(new_slot)
        step_meta.append(
            {
                "uid": uid,
                "role": role,
                "offset": offset,
                "count": len(chunk),
            }
        )
        merged_api.extend(chunk)
        offset += len(chunk)
    schema = {"slots": merged_slots} if merged_slots else None
    if schema:
        schema = enrich_param_schema_nl_descriptions(schema)
    return {"api_set": merged_api, "param_schema": schema, "step_meta": step_meta}


def _step_uids(recipe: dict) -> List[str]:
    return [str(s.get("uid") or "") for s in (recipe.get("steps") or []) if s.get("uid")]


def _is_uid_subsequence(left: List[str], right: List[str]) -> bool:
    if not left or left == right:
        return False
    iterator = iter(right)
    return all(uid in iterator for uid in left)


def drop_subset_recipes(recipes: List[dict]) -> List[dict]:
    """同设备下，步骤被另一条配方完全覆盖的短配方丢掉，避免「制冷」与「制冷到目标温度」并列。"""
    kept: List[dict] = []
    for rec in recipes:
        uids = _step_uids(rec)
        cid = str(rec.get("c_instance_id") or "")
        if any(
            str(other.get("c_instance_id") or "") == cid
            and other is not rec
            and _is_uid_subsequence(uids, _step_uids(other))
            for other in recipes
        ):
            continue
        kept.append(rec)
    return kept


def _recipe_is_lazy(recipe: dict) -> bool:
    extra = recipe.get("extra") if isinstance(recipe.get("extra"), dict) else {}
    return str(extra.get("exposure") or "") in _LAZY_EXPOSURES


def recipe_covers_effects(
    recipe: dict,
    payload_by_uid: Dict[str, dict],
    selected_e_ids: Set[int],
) -> Set[int]:
    covers = _as_int_set(recipe.get("covers_effects"))
    if covers:
        return covers
    found: Set[int] = set()
    for step in recipe.get("steps") or []:
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if not payload:
            continue
        kind = str(payload.get("capability_kind") or "")
        if kind in {"parameter", "strategy", "auxiliary"}:
            continue
        if str(step.get("role") or "") in {"parameter", "strategy", "auxiliary"}:
            continue
        if payload.get("e_id") is not None:
            try:
                found.add(int(payload["e_id"]))
            except (TypeError, ValueError):
                pass
    return found


def recipe_matches_l3(
    recipe: dict,
    payload_by_uid: Dict[str, dict],
    selected_e_ids: Set[int],
    filter_by_l3: bool,
) -> bool:
    if not filter_by_l3:
        return True
    if not selected_e_ids:
        return False
    covers = recipe_covers_effects(recipe, payload_by_uid, selected_e_ids)
    if covers & selected_e_ids:
        return True
    return False


def _recipe_has_effect_step(recipe: dict, payload_by_uid: Dict[str, dict], selected_e_ids: Set[int]) -> bool:
    for step in recipe.get("steps") or []:
        if str(step.get("role") or "") == "parameter":
            continue
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if not payload:
            continue
        kind = str(payload.get("capability_kind") or "")
        if kind in {"parameter", "strategy"}:
            continue
        e_id = payload.get("e_id")
        if e_id is None:
            continue
        try:
            eid = int(e_id)
        except (TypeError, ValueError):
            continue
        if not selected_e_ids or eid in selected_e_ids:
            return True
    return False


def _children_by_parent(payloads: Iterable[dict]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for payload in payloads:
        interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
        parent = str(interp.get("specializes_uid") or payload.get("specializes_uid") or "").strip()
        uid = str(payload.get("uid") or "")
        if parent and uid:
            mapping.setdefault(parent, []).append(uid)
    return mapping


def effective_command_weight(
    uid: str,
    pref_by_uid: Dict[str, Any],
    children_by_parent: Dict[str, List[str]],
) -> int:
    weight = _pref_weight(pref_by_uid.get(uid))
    for child in children_by_parent.get(uid) or []:
        weight = max(weight, _pref_weight(pref_by_uid.get(child)))
    return weight


def _primary_effect(payload_by_uid: Dict[str, dict], steps: List[dict], selected_e_ids: Set[int]) -> Tuple[Optional[int], str]:
    for step in steps:
        if str(step.get("role") or "") == "parameter":
            continue
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if not payload or payload.get("e_id") is None:
            continue
        try:
            e_id = int(payload["e_id"])
        except (TypeError, ValueError):
            continue
        if selected_e_ids and e_id not in selected_e_ids:
            continue
        return e_id, str(payload.get("uid") or "")
    for step in steps:
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if not payload or payload.get("e_id") is None:
            continue
        try:
            return int(payload["e_id"]), str(payload.get("uid") or "")
        except (TypeError, ValueError):
            continue
    return None, ""


def _optional_labels(param_schema: Optional[dict]) -> List[str]:
    labels = []
    for slot in (param_schema or {}).get("slots") or []:
        if not isinstance(slot, dict) or slot.get("required") is not False:
            continue
        labels.append(str(slot.get("label") or slot.get("property_desc") or slot.get("path") or "参数"))
    return labels


def _slot_blob(ph: dict) -> str:
    return (
        str(ph.get("label") or "")
        + str(ph.get("property_desc") or "")
        + str(ph.get("nl_description") or "")
        + str(ph.get("unit") or "")
    ).lower()


def _is_temp_slot(ph: dict) -> bool:
    blob = _slot_blob(ph)
    return any(k in blob for k in ("温", "℃", "celsius", "temperature"))


def _is_rpm_slot(ph: dict) -> bool:
    blob = _slot_blob(ph)
    return any(k in blob for k in ("转", "转速", "rpm"))


def _is_percent_slot(ph: dict) -> bool:
    blob = _slot_blob(ph)
    return any(k in blob for k in ("%", "％", "percent", "亮度", "百分比"))


def _slot_open(ph: dict) -> bool:
    return isinstance(ph, dict) and ph.get("user_value") in (None, "")


def _same_number(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return str(left).strip() == str(right).strip()


def _number_in_text(value: Any, text: str) -> bool:
    raw = str(value).strip()
    if not raw or not text:
        return False
    return re.search(rf"(?<!\d){re.escape(raw)}(?!\d)", text) is not None


def _value_in_range(value: Any, ph: dict) -> bool:
    bounds = ph.get("value_range") if isinstance(ph.get("value_range"), dict) else None
    if not bounds:
        return True
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    try:
        if bounds.get("min") is not None and number < float(bounds["min"]) - 1e-9:
            return False
        if bounds.get("max") is not None and number > float(bounds["max"]) + 1e-9:
            return False
    except (TypeError, ValueError):
        return False
    return True


def _enum_text_labels(ph: dict) -> List[Tuple[str, Any]]:
    found: List[Tuple[str, Any]] = []
    for opt in ph.get("options") or []:
        if not isinstance(opt, dict):
            continue
        for key in ("label_zh", "label_en"):
            label = str(opt.get(key) or "").strip()
            if len(label) < 2 or _NUMBER_TOKEN_RE.match(label):
                continue
            if re.fullmatch(r"[A-Za-z]{1,2}", label):
                continue
            found.append((label, opt.get("value")))
    return found


def _enum_value_for_number(ph: dict, value: Any) -> Any:
    """离散档位用选项名称上的数字对齐，不用选项内部编号。"""
    for opt in ph.get("options") or []:
        if not isinstance(opt, dict):
            continue
        for key in ("label_zh", "label_en"):
            label = str(opt.get(key) or "").strip()
            if _NUMBER_TOKEN_RE.match(label) and _same_number(label, value):
                return opt.get("value")
    return None


def _measure_kind(unit: str, window: str) -> str:
    token = str(unit or "").lower()
    if token in {"度", "℃", "°c", "°c", "摄氏度"} or "摄氏" in token:
        return "temp"
    if token in {"转", "rpm"}:
        return "rpm"
    if token in {"%", "％"}:
        return "percent"
    if any(k in window for k in ("温", "℃", "热", "冷", "凉", "降", "暖")):
        return "temp"
    if any(k in window for k in ("转", "转速")):
        return "rpm"
    if any(k in window for k in ("亮度", "百分之")):
        return "percent"
    if any(k in window for k in ("调到", "调成", "调至", "设为", "设成", "设到", "开到")):
        return "soft"
    return "number"


def _clauses(text: str) -> List[str]:
    parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(text) if p and p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _extract_measures(text: str) -> List[dict]:
    clauses = _clauses(text)
    if not clauses:
        return []
    spans: List[Tuple[int, int, str]] = []
    cursor = 0
    for clause in clauses:
        idx = text.find(clause, cursor)
        if idx < 0:
            idx = cursor
        spans.append((idx, idx + len(clause), clause))
        cursor = idx + len(clause)
    mentions = []
    for match in _MEASURE_RE.finditer(text):
        host = 0
        for i, (start, end, _clause) in enumerate(spans):
            if start <= match.start() < end:
                host = i
                break
        window_parts = []
        if host > 0:
            window_parts.append(spans[host - 1][2])
        window_parts.append(spans[host][2])
        window = "，".join(window_parts)
        mentions.append(
            {
                "value": match.group(1),
                "kind": _measure_kind(match.group(2) or "", window),
                "window": window,
            }
        )
    return mentions


def _distinctive_tokens(step: dict) -> Set[str]:
    blob = " ".join(
        str(step.get(key) or "")
        for key in ("c_brand", "e_name", "nl_step", "step_intent")
    )
    tokens: Set[str] = set()
    for run in _CJK_RUN_RE.findall(blob):
        if len(run) <= 8:
            tokens.add(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                tokens.add(run[i : i + 2])
    return {t for t in tokens if t not in _GENERIC_TOKENS and len(t) >= 2}


def _slot_accepts_measure(ph: dict, mention: dict) -> bool:
    if not _slot_open(ph):
        return False
    kind = mention.get("kind") or "number"
    if kind == "number":
        return False
    is_enum = str(ph.get("value_type") or "") == "enum" or bool(ph.get("options"))
    if kind in {"temp", "soft"} and not _is_temp_slot(ph):
        return False
    if kind == "rpm" and not _is_rpm_slot(ph):
        return False
    if kind == "percent" and not _is_percent_slot(ph):
        return False
    if is_enum and str(ph.get("value_type") or "") == "enum":
        return _enum_value_for_number(ph, mention.get("value")) is not None
    if is_enum and ph.get("options") and str(ph.get("value_type") or "") != "range":
        return _enum_value_for_number(ph, mention.get("value")) is not None
    return _value_in_range(mention.get("value"), ph)


def _write_measure(ph: dict, mention: dict) -> None:
    if str(ph.get("value_type") or "") == "enum" or (
        ph.get("options") and str(ph.get("value_type") or "") != "range"
    ):
        enum_value = _enum_value_for_number(ph, mention.get("value"))
        if enum_value is not None:
            ph["user_value"] = enum_value
        return
    ph["user_value"] = mention.get("value")


def _apply_measure_to_slots(placeholders: List[dict], mention: dict) -> None:
    accepting = [ph for ph in placeholders if _slot_accepts_measure(ph, mention)]
    if len(accepting) != 1:
        return
    _write_measure(accepting[0], mention)


def _bind_text_enums(text: str, placeholders: List[dict]) -> None:
    """用选项的文字名称对齐枚举。数字编号不参与，避免「22度」撞上 value=22。"""
    if not text or not placeholders:
        return
    compact = text.replace(" ", "")
    hits: List[Tuple[int, dict, Any]] = []
    for ph in placeholders:
        if not _slot_open(ph):
            continue
        for label, value in _enum_text_labels(ph):
            if label in text or label in compact:
                hits.append((len(label), ph, value))
    hits.sort(key=lambda item: item[0], reverse=True)
    bound = set()
    for _n, ph, value in hits:
        path = ph.get("path")
        if path in bound or not _slot_open(ph):
            continue
        ph["user_value"] = value
        bound.add(path)


def bind_placeholders_from_intent(intent_text: str, placeholders: List[dict]) -> List[dict]:
    """单组占位：程序名按文字对齐，数值只填唯一能接住的槽。不改 api_set。"""
    text = str(intent_text or "").strip()
    if not text or not placeholders:
        return placeholders
    _bind_text_enums(text, placeholders)
    mentions = _extract_measures(text)
    by_kind: Dict[str, List[dict]] = {}
    for mention in mentions:
        by_kind.setdefault(str(mention.get("kind") or "number"), []).append(mention)
    for group in by_kind.values():
        if len(group) != 1:
            continue
        _apply_measure_to_slots(placeholders, group[0])
    return placeholders


def bind_schema_slots_from_intent(param_schema: Optional[dict], intent_text: str) -> Optional[dict]:
    if not param_schema or not isinstance(param_schema, dict):
        return param_schema
    placeholders = build_param_placeholders_from_schema(None, param_schema=param_schema)
    bind_placeholders_from_intent(intent_text, placeholders)
    by_path = {p.get("path"): p.get("user_value") for p in placeholders if p.get("user_value") not in (None, "")}
    if not by_path:
        return param_schema
    schema = copy.deepcopy(param_schema)
    for slot in schema.get("slots") or []:
        if isinstance(slot, dict) and slot.get("path") in by_path:
            slot["user_value"] = by_path[slot["path"]]
    return schema


def _score_mention_step(mention: dict, step: dict) -> int:
    window = str(mention.get("window") or "")
    score = 0
    if _number_in_text(mention.get("value"), str(step.get("step_intent") or "")):
        score += 8
    score += 3 * sum(1 for token in _distinctive_tokens(step) if token in window)
    return score


def _placeholder_lists(step: dict) -> List[List[dict]]:
    primary = step.get("param_placeholders")
    if not isinstance(primary, list):
        return []
    lists: List[List[dict]] = [primary]
    seen = {id(primary)}
    own_id = str(step.get("c_instance_id") or "")

    def take(owner: dict) -> None:
        if own_id and str(owner.get("c_instance_id") or "") not in {"", own_id}:
            return
        items = owner.get("param_placeholders") or []
        if isinstance(items, list) and id(items) not in seen:
            seen.add(id(items))
            lists.append(items)

    for opt in step.get("options") or []:
        if not isinstance(opt, dict):
            continue
        take(opt)
        for variant in opt.get("command_variants") or []:
            if isinstance(variant, dict):
                take(variant)
    return lists


def bind_plan_placeholders(steps: List[dict], intent_text: str) -> None:
    """把原文里的数值分到对应步骤的槽上。一个数字只落一处，并对取值范围做校验。"""
    text = str(intent_text or "").strip()
    plans = [step for step in (steps or []) if isinstance(step, dict)]
    if not text or not plans:
        return
    mentions = _extract_measures(text)
    claimed: Set[int] = set()
    for index, mention in enumerate(mentions):
        pool = []
        for step in plans:
            lists = _placeholder_lists(step)
            primary = lists[0] if lists else []
            if not any(_slot_accepts_measure(ph, mention) for ph in primary):
                continue
            pool.append((step, lists, _score_mention_step(mention, step)))
        if not pool:
            continue
        localized = [item for item in pool if _number_in_text(mention.get("value"), item[0].get("step_intent"))]
        choices = localized or pool
        if mention.get("kind") == "soft":
            choices = [item for item in choices if item[2] > 0]
        choices.sort(key=lambda item: item[2], reverse=True)
        if not choices:
            continue
        if len(choices) > 1 and choices[0][2] == choices[1][2]:
            continue
        _step, lists, _score = choices[0]
        for items in lists:
            _apply_measure_to_slots(items, mention)
        claimed.add(index)

    for step in plans:
        lists = _placeholder_lists(step)
        scope_parts = [str(step.get("step_intent") or "")]
        for index in claimed:
            window = str(mentions[index].get("window") or "")
            if window and _score_mention_step(mentions[index], step) > 0:
                scope_parts.append(window)
        scope = "\n".join(part for part in scope_parts if part) or text
        # 多步草案里，文字枚举只在该步说明或已分到该步的片段里找，避免全文串槽
        if len(plans) == 1:
            scope = text
        for items in lists:
            _bind_text_enums(scope, items)
    _bind_unique_text_enums(text, plans)


def _bind_unique_text_enums(text: str, steps: List[dict]) -> None:
    """全文里的程序名只在唯一持有该名称的步骤上预填。"""
    if len(steps) <= 1 or not text:
        return
    compact = text.replace(" ", "")
    grouped: Dict[str, List[Tuple[dict, Any]]] = {}
    owners: Dict[str, Set[int]] = {}
    for step in steps:
        primary = step.get("param_placeholders")
        if not isinstance(primary, list):
            continue
        for ph in primary:
            if not _slot_open(ph):
                continue
            for label, value in _enum_text_labels(ph):
                if label not in text and label not in compact:
                    continue
                grouped.setdefault(label, []).append((ph, value))
                owners.setdefault(label, set()).add(id(step))
    for label, rows in sorted(grouped.items(), key=lambda item: len(item[0]), reverse=True):
        if len(owners.get(label) or ()) != 1:
            continue
        ph, value = rows[0]
        if _slot_open(ph):
            ph["user_value"] = value


def drop_unfilled_optional_api_ops(api_set: Any, placeholders: List[dict], applied: List[dict]) -> Any:
    """未填写的可选参数对应 api 操作从最终指令中去掉，避免把 XX 发给设备。"""
    if not isinstance(api_set, list):
        return api_set
    applied_paths = {a.get("path") for a in applied or [] if isinstance(a, dict)}
    drop_indexes = set()
    for ph in placeholders or []:
        if not isinstance(ph, dict) or ph.get("required") is not False:
            continue
        path = ph.get("path")
        if path in applied_paths:
            continue
        matched = _API_INDEX_RE.match(str(path or ""))
        if matched:
            drop_indexes.add(int(matched.group(1)))
    if not drop_indexes:
        return api_set
    return [row for i, row in enumerate(api_set) if i not in drop_indexes]


def env_attr_as_maps(env_attrs: Optional[Iterable[Any]] = None) -> List[dict]:
    rows: List[dict] = []
    for row in env_attrs or []:
        if isinstance(row, dict):
            aliases = row.get("aliases") or []
            rows.append(
                {
                    "env_id": row.get("env_id"),
                    "match_key": str(row.get("match_key") or ""),
                    "env_name": str(row.get("env_name") or ""),
                    "aliases": list(aliases) if isinstance(aliases, list) else [],
                }
            )
            continue
        aliases = getattr(row, "aliases", None) or []
        rows.append(
            {
                "env_id": getattr(row, "env_id", None),
                "match_key": str(getattr(row, "match_key", None) or ""),
                "env_name": str(getattr(row, "env_name", None) or ""),
                "aliases": list(aliases) if isinstance(aliases, list) else [],
            }
        )
    return rows


def looks_like_observe_intent(intent_text: str) -> bool:
    text = str(intent_text or "")
    return any(token in text for token in _OBSERVE_INTENT_HINTS)


def hinted_env_match_keys(intent_text: str, env_attrs: Optional[Iterable[Any]] = None) -> Set[str]:
    text = str(intent_text or "")
    keys: Set[str] = set()
    for words, key in _ENV_INTENT_KEYS:
        if any(w in text for w in words):
            keys.add(key)
    for row in env_attr_as_maps(env_attrs):
        mk = str(row.get("match_key") or "").strip()
        if not mk:
            continue
        needles = [str(row.get("env_name") or ""), mk]
        needles.extend(str(alias or "") for alias in (row.get("aliases") or []))
        for needle in needles:
            token = needle.strip()
            if len(token) < 2:
                continue
            if token in text:
                keys.add(mk)
                break
    return keys


def compact_combo_hint(combo: Optional[dict]) -> str:
    items = (combo or {}).get("items") or []
    by_role: Dict[str, List[str]] = {"primary": [], "side": [], "observe": [], "forbid": []}
    for item in items:
        role = str(item.get("role") or "")
        name = str(item.get("env_name") or item.get("match_key") or "").strip()
        if role not in by_role or not name or name in by_role[role]:
            continue
        by_role[role].append(name)
    parts: List[str] = []
    if by_role["primary"]:
        parts.append("主签名：" + "、".join(by_role["primary"]))
    if by_role["side"]:
        parts.append("连带：" + "、".join(by_role["side"]))
    if by_role["observe"]:
        parts.append("观察：" + "、".join(by_role["observe"]))
    if by_role["forbid"]:
        parts.append("禁标：" + "、".join(by_role["forbid"][:4]))
    if (combo or {}).get("empty"):
        parts.append("空签")
    return "；".join(parts)


def combo_intent_score(combo: Optional[dict], wanted_keys: Set[str], intent_text: str) -> Tuple[int, str]:
    """按对应组给 L3 效果预打分：主签名命中加分，禁标命中降权，纯观察默认后置。"""
    combo = combo or {}
    items = combo.get("items") or []
    score = 0
    hints: List[str] = []
    has_primary = False
    has_observe = False
    observe_intent = looks_like_observe_intent(intent_text)
    for item in items:
        role = str(item.get("role") or "")
        mk = str(item.get("match_key") or "")
        name = str(item.get("env_name") or mk)
        if role == "primary":
            has_primary = True
            if mk and mk in wanted_keys:
                score += 4
                hints.append(f"主:{name}")
        elif role == "side":
            if mk and mk in wanted_keys:
                score += 1
                hints.append(f"连带:{name}")
        elif role == "observe":
            has_observe = True
            if mk and mk in wanted_keys and observe_intent:
                score += 3
                hints.append(f"观察:{name}")
        elif role == "forbid":
            if mk and mk in wanted_keys:
                score -= 3
                hints.append(f"禁:{name}")
    if combo.get("empty"):
        score -= 1
    if has_observe and not has_primary and not observe_intent:
        score -= 2
    return score, "；".join(hints) or compact_combo_hint(combo)


def wanted_env_from_effect_ids(
    e_ids: Iterable[Any],
    env_attrs: Optional[Iterable[Any]] = None,
) -> Tuple[Set[int], Set[str], List[str]]:
    """从已选 L3 效果的主签名（无主签名则观察）收集 wanted env。"""
    from effect_env_combos import resolve_effect_combo

    env_maps = env_attr_as_maps(env_attrs)
    wanted_ids: Set[int] = set()
    wanted_keys: Set[str] = set()
    labels: List[str] = []
    for raw in e_ids or []:
        try:
            eid = int(raw)
        except (TypeError, ValueError):
            continue
        combo = resolve_effect_combo(eid, env_maps)
        items = list(combo.get("items") or [])
        primaries = [it for it in items if str(it.get("role") or "") == "primary"]
        chosen = primaries or [it for it in items if str(it.get("role") or "") == "observe"]
        for item in chosen:
            mk = str(item.get("match_key") or "").strip()
            if mk:
                wanted_keys.add(mk)
            try:
                env_id = int(item.get("env_id")) if item.get("env_id") is not None else None
            except (TypeError, ValueError):
                env_id = None
            if env_id is not None:
                wanted_ids.add(env_id)
            name = str(item.get("env_name") or mk).strip()
            if name and name not in labels:
                labels.append(name)
    return wanted_ids, wanted_keys, labels


def annotate_device_env_match(
    intent_text: str,
    devices: List[dict],
    env_attrs: List[Any],
    wanted_keys: Optional[Set[str]] = None,
    wanted_env_ids: Optional[Set[int]] = None,
) -> None:
    """按 L3 主签名（缺省则口语关键词）给设备 env_set 打分；不让模型选择 env_id。"""
    env_maps = env_attr_as_maps(env_attrs)
    wanted = set(wanted_keys) if wanted_keys is not None else hinted_env_match_keys(intent_text, env_maps)
    wanted_ids = set()
    for raw in wanted_env_ids or []:
        try:
            wanted_ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    id_to_meta = {}
    for row in env_maps:
        try:
            eid = int(row.get("env_id"))
        except (TypeError, ValueError):
            continue
        id_to_meta[eid] = {
            "match_key": str(row.get("match_key") or ""),
            "env_name": str(row.get("env_name") or ""),
        }
    for device in devices or []:
        score = 0
        hints: List[str] = []
        for raw in device.get("env_set") or []:
            try:
                eid = int(raw)
            except (TypeError, ValueError):
                continue
            meta = id_to_meta.get(eid) or {}
            mk = meta.get("match_key")
            hit = False
            if eid in wanted_ids:
                score += 2
                hit = True
            elif mk and mk in wanted:
                score += 1
                hit = True
            if hit:
                name = meta.get("env_name") or mk
                if name and name not in hints:
                    hints.append(name)
        device["env_match_score"] = score
        device["env_match_hint"] = "、".join(hints)


def apply_candidate_meta_to_layer(layer_result: Any, cand_by_id: Dict[Any, dict]) -> None:
    """把预排序字段写回已选节点，供层卡片展示。"""
    nodes = getattr(layer_result, "selected_nodes", None)
    if nodes is None and isinstance(layer_result, dict):
        nodes = layer_result.get("selected_nodes") or []
    for node in nodes or []:
        raw_id = node.get("id") if isinstance(node, dict) else getattr(node, "id", None)
        meta = cand_by_id.get(raw_id)
        if meta is None:
            meta = cand_by_id.get(str(raw_id))
        if meta is None:
            try:
                meta = cand_by_id.get(int(raw_id))
            except (TypeError, ValueError):
                meta = None
        if not meta:
            continue
        hint = str(
            meta.get("env_combo_hint")
            or meta.get("env_match_hint")
            or meta.get("env_hint")
            or ""
        )
        try:
            score = int(meta.get("env_match_score") if meta.get("env_match_score") is not None else meta.get("combo_score") or 0)
        except (TypeError, ValueError):
            score = 0
        kind = str(meta.get("candidate_kind") or "")
        if isinstance(node, dict):
            node["env_hint"] = hint
            node["env_match_score"] = score
            node["candidate_kind"] = kind
            continue
        node.env_hint = hint
        node.env_match_score = score
        node.candidate_kind = kind


def reachable_device_ids(
    payloads: List[dict],
    recipes: List[dict],
    selected_e_ids: Set[int],
) -> Set[str]:
    selected = set(selected_e_ids)
    reachable: Set[str] = set()
    payload_by_uid = {str(p.get("uid") or ""): p for p in payloads}
    for payload in payloads:
        cid = str(payload.get("c_instance_id") or "")
        if not cid:
            continue
        e_id = payload.get("e_id")
        try:
            if e_id is not None and int(e_id) in selected:
                reachable.add(cid)
                continue
        except (TypeError, ValueError):
            pass
        if str(payload.get("capability_kind") or "") == "parameter":
            if _as_int_set(payload.get("supports_e_ids")) & selected:
                reachable.add(cid)
    for recipe in recipes:
        rec = recipe_as_dict(recipe) if not isinstance(recipe, dict) else recipe
        if _recipe_is_lazy(rec):
            continue
        if recipe_covers_effects(rec, payload_by_uid, selected) & selected:
            cid = str(rec.get("c_instance_id") or "")
            if cid:
                reachable.add(cid)
    return reachable


def _supporting_params(
    payloads: List[dict],
    device_id: str,
    e_id: Optional[int],
) -> List[dict]:
    if e_id is None:
        return []
    out = []
    for payload in payloads:
        if str(payload.get("c_instance_id") or "") != device_id:
            continue
        if str(payload.get("capability_kind") or "") != "parameter":
            continue
        if not payload_is_l5_visible(payload):
            continue
        if e_id not in _as_int_set(payload.get("supports_e_ids")):
            continue
        out.append(payload)
    return out


def _unique_uid(base: str, used: Set[str], c_instance_id: str) -> str:
    uid = str(base or "").strip()
    if not uid:
        uid = f"{c_instance_id}::recipe"
    if uid in used:
        uid = f"{c_instance_id}::{uid}"
    used.add(uid)
    return uid


def _candidate_env_ids(cand: dict, payload_by_uid: Dict[str, dict]) -> Set[int]:
    ids: Set[int] = set()
    collected = False
    for step in cand.get("recipe_steps") or []:
        role = str(step.get("role") or "")
        payload = payload_by_uid.get(str(step.get("uid") or ""))
        if not payload:
            continue
        kind = str(payload.get("capability_kind") or "")
        if role in _SKIP_ENV_ROLES or kind in _SKIP_ENV_KINDS:
            continue
        ids |= _as_int_set(payload.get("env_impact"))
        collected = True
    if not collected:
        payload = payload_by_uid.get(str(cand.get("primary_payload_uid") or ""))
        if payload:
            ids |= _as_int_set(payload.get("env_impact"))
    return ids


def attach_l5_env_rank(
    candidates: List[dict],
    payload_by_uid: Dict[str, dict],
    wanted_env_ids: Optional[Iterable[Any]] = None,
    env_name_by_id: Optional[Dict[int, str]] = None,
) -> None:
    wanted = _as_int_set(wanted_env_ids)
    names = env_name_by_id or {}
    for cand in candidates or []:
        ids = _candidate_env_ids(cand, payload_by_uid)
        cand["env_impact"] = sorted(ids)
        overlap = ids & wanted if wanted else set()
        cand["env_match_score"] = len(overlap)
        show_ids = sorted(overlap or ids)
        label_parts = [str(names.get(eid) or eid) for eid in show_ids]
        kind = str(cand.get("candidate_kind") or "atom")
        kind_label = {"recipe": "配方", "atom": "原子", "composed": "组合"}.get(kind, kind)
        hint_parts = [kind_label]
        if label_parts:
            hint_parts.append("影响：" + "、".join(label_parts))
        cand["env_hint"] = "；".join(hint_parts)
    if wanted:
        candidates.sort(
            key=lambda c: (
                -int(c.get("env_match_score") or 0),
                0 if c.get("candidate_kind") == "recipe" else 1,
                -int(c.get("weight") or 0),
                str(c.get("uid") or ""),
            )
        )


def compose_l5_candidates(
    *,
    payloads: List[Any],
    recipes: List[Any],
    pref_by_uid: Dict[str, Any],
    device_pref_by_id: Dict[str, Any],
    selected_e_ids: Iterable[int],
    filter_by_l3: bool = True,
    effect_name_map: Optional[Dict[int, str]] = None,
    device_brand_map: Optional[Dict[str, str]] = None,
    intent_text: str = "",
    wanted_env_ids: Optional[Iterable[Any]] = None,
    env_name_by_id: Optional[Dict[int, str]] = None,
) -> List[dict]:
    """
    L5 候选：优先配方（一步含可选参数槽），否则效果原子并挂 supports_e_ids 参数。
    懒人程序不进主候选；偏好看效果步 weight，可继承 specializes 子指令。
    """
    payload_list = [payload_as_dict(p) for p in payloads]
    payload_by_uid = {str(p.get("uid") or ""): p for p in payload_list if p.get("uid")}
    selected = _as_int_set(selected_e_ids)
    effect_name_map = effect_name_map or {}
    device_brand_map = device_brand_map or {}
    children_by_parent = _children_by_parent(payload_list)

    rec_list = [recipe_as_dict(r) for r in recipes]
    usable = []
    for rec in rec_list:
        if _recipe_is_lazy(rec):
            continue
        if not merge_step_payloads(rec.get("steps") or [], payload_by_uid):
            continue
        is_strategy_rec = _recipe_has_strategy_step(rec, payload_by_uid)
        if is_strategy_rec:
            if filter_by_l3 and not strategy_recipe_named(rec, payload_by_uid, intent_text):
                continue
        else:
            if filter_by_l3 and not recipe_matches_l3(rec, payload_by_uid, selected, True):
                continue
            if filter_by_l3 and not _recipe_has_effect_step(rec, payload_by_uid, selected):
                continue
        usable.append(rec)
    usable = drop_subset_recipes(usable)

    candidates: List[dict] = []
    used_uids: Set[str] = set()
    covered_payload_uids: Set[str] = set()

    for rec in usable:
        steps = list(rec.get("steps") or [])
        merged = merge_step_payloads(steps, payload_by_uid)
        if not merged:
            continue
        weights = []
        descs = []
        details = {}
        for step in steps:
            if str(step.get("role") or "") in _OPTIONAL_STEP_ROLES:
                continue
            uid = str(step.get("uid") or "")
            weights.append(effective_command_weight(uid, pref_by_uid, children_by_parent))
            desc = _pref_desc(pref_by_uid.get(uid))
            if desc:
                descs.append(desc)
            extra_details = _pref_details(pref_by_uid.get(uid))
            if extra_details:
                details.update(extra_details)
        weight = max(weights) if weights else 0
        if weight <= 0:
            continue
        e_id, primary_uid = _primary_effect(payload_by_uid, steps, selected)
        cid = str(rec.get("c_instance_id") or "")
        extra = rec.get("extra") if isinstance(rec.get("extra"), dict) else {}
        schema = bind_schema_slots_from_intent(merged.get("param_schema"), intent_text)
        uid = _unique_uid(str(rec.get("recipe_uid") or rec.get("recipe_name") or primary_uid), used_uids, cid)
        device_pref = device_pref_by_id.get(cid)
        is_strategy_rec = _recipe_has_strategy_step(rec, payload_by_uid)
        candidates.append(
            {
                "uid": uid,
                "display_name": str(rec.get("recipe_name") or uid),
                "c_instance_id": cid,
                "c_brand": device_brand_map.get(cid, ""),
                "e_id": e_id,
                "e_name": effect_name_map.get(e_id, "") if e_id is not None else "",
                "api_set": merged.get("api_set"),
                "param_schema": schema,
                "param_details": details or None,
                "weight": weight,
                "preference_desc": "；".join(descs) if descs else None,
                "device_weight": _pref_weight(device_pref),
                "capability_kind": "strategy" if is_strategy_rec else "effect",
                "candidate_kind": "recipe",
                "recipe_uid": rec.get("recipe_uid"),
                "recipe_pattern": extra.get("pattern") or "",
                "covers_effects": sorted(recipe_covers_effects(rec, payload_by_uid, selected)),
                "primary_payload_uid": primary_uid,
                "optional_param_labels": _optional_labels(schema),
                "recipe_steps": merged.get("step_meta") or [],
            }
        )
        covered_payload_uids.update(_step_uids(rec))

    for payload in payload_list:
        uid = str(payload.get("uid") or "")
        if not uid or uid in covered_payload_uids:
            continue
        if not payload_is_l5_visible(payload):
            continue
        kind = str(payload.get("capability_kind") or "")
        if kind in {"parameter", "auxiliary"}:
            continue
        e_id = payload.get("e_id")
        try:
            e_id_int = int(e_id) if e_id is not None else None
        except (TypeError, ValueError):
            e_id_int = None
        if kind == "strategy":
            if filter_by_l3 and not strategy_named_in_intent(payload, intent_text):
                continue
        elif filter_by_l3 and (e_id_int is None or e_id_int not in selected):
            continue
        weight = effective_command_weight(uid, pref_by_uid, children_by_parent)
        if weight <= 0:
            continue
        cid = str(payload.get("c_instance_id") or "")
        param_atoms = _supporting_params(payload_list, cid, e_id_int)
        steps = [{"uid": uid, "role": "strategy" if kind == "strategy" else "effect"}]
        for param in param_atoms:
            puid = str(param.get("uid") or "")
            if puid and puid not in covered_payload_uids:
                steps.append({"uid": puid, "role": "parameter"})
        merged = merge_step_payloads(steps, payload_by_uid)
        if not merged:
            continue
        schema = bind_schema_slots_from_intent(merged.get("param_schema"), intent_text)
        details = _pref_details(pref_by_uid.get(uid))
        l5_uid = _unique_uid(uid, used_uids, cid)
        device_pref = device_pref_by_id.get(cid)
        candidates.append(
            {
                "uid": l5_uid,
                "display_name": uid,
                "c_instance_id": cid,
                "c_brand": device_brand_map.get(cid, ""),
                "e_id": e_id_int,
                "e_name": effect_name_map.get(e_id_int, "") if e_id_int is not None else "",
                "api_set": merged.get("api_set"),
                "param_schema": schema,
                "param_details": details,
                "weight": weight,
                "preference_desc": _pref_desc(pref_by_uid.get(uid)) or None,
                "device_weight": _pref_weight(device_pref),
                "capability_kind": kind or "effect",
                "candidate_kind": "atom" if len(steps) == 1 else "composed",
                "recipe_uid": None,
                "recipe_pattern": "",
                "covers_effects": [e_id_int] if e_id_int is not None else [],
                "primary_payload_uid": uid,
                "optional_param_labels": _optional_labels(schema),
                "recipe_steps": merged.get("step_meta") or [],
            }
        )
    attach_l5_env_rank(
        candidates,
        payload_by_uid,
        wanted_env_ids=wanted_env_ids,
        env_name_by_id=env_name_by_id,
    )
    return candidates
