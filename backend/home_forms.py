"""环境表单 / 房间种类 / 设备实例化：意图实现的家居库。"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from intent_compose import (
    _is_uid_subsequence,
    _recipe_has_strategy_step,
    _recipe_is_lazy,
    _step_uids,
    drop_subset_recipes,
    is_pref_eligible_payload,
    merge_step_payloads,
    payload_as_dict,
    recipe_as_dict,
    recipe_covers_effects,
)

DEFAULT_FORM_ID = "form-default"
DEFAULT_FORM_NAME = "默认环境"
PRESET_ROOM_TYPE_NAMES = models.PRESET_ROOM_TYPE_NAMES


def new_form_id() -> str:
    return f"form-{uuid.uuid4().hex[:12]}"


def new_placement_id() -> str:
    return f"plc-{uuid.uuid4().hex[:12]}"


def placement_display_name(
    *,
    alias: str = "",
    catalog_brand: str = "",
    catalog_id: str = "",
    room_label: str = "",
) -> str:
    base = str(alias or "").strip() or str(catalog_brand or "").strip() or str(catalog_id or "").strip()
    room = str(room_label or "").strip()
    if room:
        return f"{base}（{room}）"
    return base or catalog_id


async def seed_room_types(db: AsyncSession) -> int:
    existing = {
        str(row.name)
        for row in (await db.execute(select(models.HomeRoomType))).scalars().all()
    }
    created = 0
    for name in PRESET_ROOM_TYPE_NAMES:
        if name in existing:
            continue
        db.add(models.HomeRoomType(name=name, is_preset=True, is_active=True))
        created += 1
    if created:
        await db.flush()
    return created


async def ensure_default_form(db: AsyncSession) -> models.HomeForm:
    form = (
        await db.execute(select(models.HomeForm).where(models.HomeForm.form_id == DEFAULT_FORM_ID))
    ).scalars().first()
    if form:
        return form
    form = models.HomeForm(form_id=DEFAULT_FORM_ID, name=DEFAULT_FORM_NAME, note="由历史检索偏好迁移或系统预置")
    db.add(form)
    await db.flush()
    return form


async def migrate_legacy_preferences(db: AsyncSession) -> Dict[str, int]:
    """把 weight>0 的旧设备/指令偏好迁进默认环境表单。已有实例则跳过。"""
    await seed_room_types(db)
    existing_any = (await db.execute(select(models.HomeDevicePlacement).limit(1))).scalars().first()
    form = await ensure_default_form(db)
    if existing_any:
        return {"forms": 1, "placements": 0, "command_prefs": 0, "skipped": 1}

    device_prefs = (
        await db.execute(
            select(models.UserDevicePreference).where(models.UserDevicePreference.weight > 0)
        )
    ).scalars().all()
    if not device_prefs:
        return {"forms": 1, "placements": 0, "command_prefs": 0, "skipped": 0}

    catalog_ids = [p.c_instance_id for p in device_prefs]
    devices = (
        await db.execute(
            select(models.ConcreteDevice).where(models.ConcreteDevice.c_instance_id.in_(catalog_ids))
        )
    ).scalars().all()
    brand_by_id = {d.c_instance_id: d.c_brand for d in devices}
    payloads = (
        await db.execute(
            select(models.CommandPayload).where(models.CommandPayload.c_instance_id.in_(catalog_ids))
        )
    ).scalars().all()
    payloads_by_device: Dict[str, List[models.CommandPayload]] = {}
    for row in payloads:
        payloads_by_device.setdefault(row.c_instance_id, []).append(row)
    old_cmd = {
        p.payload_uid: p
        for p in (await db.execute(select(models.UserCommandPreference))).scalars().all()
    }

    placements = 0
    command_prefs = 0
    for pref in device_prefs:
        cid = pref.c_instance_id
        if cid not in brand_by_id:
            continue
        placement = models.HomeDevicePlacement(
            placement_id=new_placement_id(),
            form_id=form.form_id,
            catalog_c_instance_id=cid,
            room_id=None,
            alias=str(brand_by_id.get(cid) or cid),
            weight=max(1, min(5, int(pref.weight or 1))),
            preference_desc=pref.preference_desc,
        )
        db.add(placement)
        await db.flush()
        placements += 1
        for payload in payloads_by_device.get(cid) or []:
            if not is_pref_eligible_payload(payload_as_dict(payload)):
                continue
            old = old_cmd.get(payload.uid)
            weight = int(old.weight) if old is not None else 1
            weight = max(0, min(5, weight))
            db.add(
                models.HomeCommandPref(
                    placement_id=placement.placement_id,
                    payload_uid=payload.uid,
                    weight=weight,
                    preference_desc=old.preference_desc if old is not None else None,
                    param_details=old.param_details if old is not None else None,
                )
            )
            command_prefs += 1
    await db.flush()
    return {"forms": 1, "placements": placements, "command_prefs": command_prefs, "skipped": 0}


async def init_home_library(db: AsyncSession) -> Dict[str, int]:
    created_types = await seed_room_types(db)
    migrated = await migrate_legacy_preferences(db)
    return {"room_types_created": created_types, **migrated}


def dump_room_type(row: models.HomeRoomType) -> dict:
    return {
        "type_id": row.type_id,
        "name": row.name,
        "is_preset": bool(row.is_preset),
        "is_active": bool(row.is_active),
    }


def dump_form(row: models.HomeForm) -> dict:
    return {
        "form_id": row.form_id,
        "name": row.name,
        "note": row.note or "",
    }


def dump_room(
    row: models.HomeRoom,
    type_by_id: Optional[Dict[int, models.HomeRoomType]] = None,
) -> dict:
    type_row = (type_by_id or {}).get(int(row.type_id)) if type_by_id else None
    return {
        "room_id": row.room_id,
        "form_id": row.form_id,
        "type_id": row.type_id,
        "type_name": type_row.name if type_row else "",
        "label": row.label,
        "sort_order": int(row.sort_order or 0),
    }


def dump_placement(
    row: models.HomeDevicePlacement,
    *,
    catalog: Optional[models.ConcreteDevice] = None,
    room: Optional[models.HomeRoom] = None,
    room_type: Optional[models.HomeRoomType] = None,
) -> dict:
    room_label = room.label if room else ""
    brand = catalog.c_brand if catalog else ""
    catalog_id = row.catalog_c_instance_id
    return {
        "placement_id": row.placement_id,
        "form_id": row.form_id,
        "catalog_c_instance_id": catalog_id,
        "c_brand": brand,
        "a_ref": catalog.a_ref if catalog else None,
        "env_set": list(catalog.env_set or []) if catalog else [],
        "source": int(getattr(catalog, "source", 1) or 1) if catalog else 1,
        "c_desc": getattr(catalog, "c_desc", None) if catalog else None,
        "room_id": row.room_id,
        "room_label": room_label,
        "room_type_name": room_type.name if room_type else "",
        "alias": row.alias or "",
        "weight": int(row.weight or 1),
        "preference_desc": row.preference_desc,
        "display_name": placement_display_name(
            alias=row.alias or "",
            catalog_brand=brand,
            catalog_id=catalog_id,
            room_label=room_label,
        ),
    }


def dump_ctx_placement(ctx: Dict[str, Any], row: models.HomeDevicePlacement) -> dict:
    room_by_id = ctx.get("room_by_id") or {}
    type_by_id = ctx.get("type_by_id") or {}
    device_by_id = ctx.get("device_by_id") or {}
    room = room_by_id.get(row.room_id) if row.room_id else None
    room_type = None
    if room:
        room_type = type_by_id.get(int(room.type_id))
    return dump_placement(
        row,
        catalog=device_by_id.get(row.catalog_c_instance_id),
        room=room,
        room_type=room_type,
    )


def dump_ctx_placements(ctx: Dict[str, Any]) -> List[dict]:
    return [dump_ctx_placement(ctx, p) for p in ctx.get("placements") or []]


def command_prefs_by_placement(ctx: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for pref in ctx.get("command_prefs") or []:
        out.setdefault(pref.placement_id, {})[pref.payload_uid] = pref
    return out


def fill_command_pref_map(existing: Dict[str, Any], payloads: Iterable) -> Dict[str, Any]:
    """表单里已有实例时，未单独设权的合格指令按 weight=1 参与。"""
    out = dict(existing or {})
    for payload in payloads:
        data = payload_as_dict(payload)
        uid = str(data.get("uid") or "")
        if not uid or uid in out:
            continue
        if is_pref_eligible_payload(data):
            out[uid] = {"weight": 1}
    return out


async def load_form_context(db: AsyncSession, form_id: str) -> Dict[str, Any]:
    form = (
        await db.execute(select(models.HomeForm).where(models.HomeForm.form_id == form_id))
    ).scalars().first()
    if not form:
        return {}
    types = (await db.execute(select(models.HomeRoomType))).scalars().all()
    type_by_id = {int(t.type_id): t for t in types}
    rooms = (
        await db.execute(
            select(models.HomeRoom).where(models.HomeRoom.form_id == form_id).order_by(
                models.HomeRoom.sort_order, models.HomeRoom.room_id
            )
        )
    ).scalars().all()
    room_by_id = {int(r.room_id): r for r in rooms}
    placements = (
        await db.execute(
            select(models.HomeDevicePlacement).where(models.HomeDevicePlacement.form_id == form_id)
        )
    ).scalars().all()
    catalog_ids = [p.catalog_c_instance_id for p in placements]
    devices = []
    if catalog_ids:
        devices = (
            await db.execute(
                select(models.ConcreteDevice).where(
                    models.ConcreteDevice.c_instance_id.in_(catalog_ids)
                )
            )
        ).scalars().all()
    device_by_id = {d.c_instance_id: d for d in devices}
    cmd_prefs = []
    if placements:
        cmd_prefs = (
            await db.execute(
                select(models.HomeCommandPref).where(
                    models.HomeCommandPref.placement_id.in_([p.placement_id for p in placements])
                )
            )
        ).scalars().all()
    return {
        "form": form,
        "types": types,
        "type_by_id": type_by_id,
        "rooms": rooms,
        "room_by_id": room_by_id,
        "placements": placements,
        "device_by_id": device_by_id,
        "command_prefs": cmd_prefs,
    }


async def default_command_prefs_for_catalog(
    db: AsyncSession,
    catalog_c_instance_id: str,
) -> List[dict]:
    payloads = (
        await db.execute(
            select(models.CommandPayload).where(
                models.CommandPayload.c_instance_id == catalog_c_instance_id
            )
        )
    ).scalars().all()
    rows = []
    for payload in payloads:
        if not is_pref_eligible_payload(payload_as_dict(payload)):
            continue
        rows.append(
            {
                "payload_uid": payload.uid,
                "weight": 1,
                "preference_desc": None,
                "param_details": None,
            }
        )
    return rows


def stamp_l5_placement(candidates: List[dict], placement: dict) -> List[dict]:
    """把按型号展开的 L5 候选改写到某一家居实例上，避免同型号多例 UID 撞车。"""
    pid = str(placement.get("placement_id") or "")
    catalog_id = str(placement.get("catalog_c_instance_id") or "")
    brand = str(placement.get("display_name") or placement.get("alias") or placement.get("c_brand") or "")
    out: List[dict] = []
    for cand in candidates or []:
        item = dict(cand)
        orig_uid = str(item.get("uid") or "")
        item["source_uid"] = orig_uid
        item["primary_payload_uid"] = item.get("primary_payload_uid") or orig_uid
        item["uid"] = f"{pid}::{orig_uid}" if pid else orig_uid
        item["catalog_c_instance_id"] = catalog_id or item.get("c_instance_id")
        item["placement_id"] = pid
        item["c_instance_id"] = pid
        if brand:
            item["c_brand"] = brand
        item["room_label"] = placement.get("room_label") or ""
        out.append(item)
    return out


def annotate_device_room_match(intent_text: str, devices: List[dict]) -> None:
    """口语里的房间名/别名只给已填房间或别名命中的实例加权。"""
    text = str(intent_text or "")
    for device in devices or []:
        score = 0
        hints: List[str] = []
        for token, bonus in (
            (str(device.get("room_label") or "").strip(), 3),
            (str(device.get("room_type_name") or "").strip(), 2),
            (str(device.get("alias") or "").strip(), 1),
        ):
            if len(token) < 2 or token not in text:
                continue
            score += bonus
            if token not in hints:
                hints.append(token)
        device["room_match_score"] = score
        device["room_match_hint"] = "、".join(hints)


_STEP_ROLE_LABELS = {
    "effect": "效果步骤",
    "parameter": "参数槽",
    "auxiliary": "辅助步骤",
    "strategy": "策略步骤",
    "action": "动作步骤",
}


def _pref_weight_value(pref: Any, default: int = 1) -> int:
    if pref is None:
        return default
    if isinstance(pref, dict):
        raw = pref.get("weight")
    else:
        raw = getattr(pref, "weight", None)
    try:
        return max(0, min(5, int(raw if raw is not None else default)))
    except (TypeError, ValueError):
        return default


def _pref_desc_value(pref: Any) -> Optional[str]:
    if pref is None:
        return None
    if isinstance(pref, dict):
        text = pref.get("preference_desc")
    else:
        text = getattr(pref, "preference_desc", None)
    return str(text) if text else None


def _pref_details_value(pref: Any) -> Optional[Any]:
    if pref is None:
        return None
    if isinstance(pref, dict):
        return pref.get("param_details")
    return getattr(pref, "param_details", None)


def _int_ids(raw: Any) -> List[int]:
    out: List[int] = []
    seen = set()
    for item in raw or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _names_for_ids(ids: Iterable[int], name_map: Optional[Dict[int, str]]) -> List[str]:
    mapping = name_map or {}
    names = []
    for item in ids:
        label = str(mapping.get(int(item)) or "").strip()
        names.append(label or f"#{item}")
    return names


def _param_slot_labels(payload: dict) -> List[str]:
    schema = payload.get("param_schema") if isinstance(payload.get("param_schema"), dict) else {}
    labels = []
    for slot in schema.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        label = str(
            slot.get("property_desc")
            or slot.get("label")
            or slot.get("property_name")
            or slot.get("param_name")
            or slot.get("path")
            or ""
        ).strip()
        if label:
            labels.append(label)
    return labels


def _kind_label(kind: str) -> str:
    return models.CAPABILITY_KIND_LABELS.get(kind, "") or kind or ""


def dump_command_pref_item(
    *,
    placement_id: str,
    payload: dict,
    pref: Any = None,
    effect_name_map: Optional[Dict[int, str]] = None,
    env_name_map: Optional[Dict[int, str]] = None,
    covered_by_recipes: Optional[List[str]] = None,
) -> dict:
    kind = str(payload.get("capability_kind") or "")
    e_id = payload.get("e_id")
    try:
        e_id_int = int(e_id) if e_id is not None else None
    except (TypeError, ValueError):
        e_id_int = None
    env_ids = _int_ids(payload.get("env_impact"))
    support_ids = _int_ids(payload.get("supports_e_ids"))
    interp = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    return {
        "placement_id": placement_id,
        "payload_uid": str(payload.get("uid") or ""),
        "weight": _pref_weight_value(pref, 1),
        "preference_desc": _pref_desc_value(pref),
        "param_details": _pref_details_value(pref),
        "e_id": e_id_int,
        "e_name": (effect_name_map or {}).get(e_id_int, "") if e_id_int is not None else "",
        "capability_kind": kind,
        "kind_label": _kind_label(kind),
        "capability_desc": payload.get("capability_desc"),
        "env_impact": env_ids,
        "env_names": _names_for_ids(env_ids, env_name_map),
        "supports_e_ids": support_ids,
        "supports_effect_names": _names_for_ids(support_ids, effect_name_map),
        "covered_by_recipes": list(covered_by_recipes or []),
        "l5_visible": interp.get("l5_visible") is not False,
        "exposure": str(interp.get("exposure") or payload.get("exposure") or "") or None,
        "specializes_uid": str(interp.get("specializes_uid") or payload.get("specializes_uid") or "") or None,
        "param_labels": _param_slot_labels(payload),
    }


def build_command_weight_editor(
    *,
    placement_id: str,
    payloads: Iterable[Any],
    recipes: Iterable[Any],
    pref_by_uid: Optional[Dict[str, Any]] = None,
    effect_name_map: Optional[Dict[int, str]] = None,
    env_name_map: Optional[Dict[int, str]] = None,
) -> dict:
    """按 L5 出场结构组织指令权：配方卡片优先，未被覆盖的效果/策略原子随后。"""
    prefs = pref_by_uid or {}
    payload_list = [payload_as_dict(p) for p in payloads]
    payload_by_uid = {str(p.get("uid") or ""): p for p in payload_list if p.get("uid")}
    rec_list = [recipe_as_dict(r) for r in recipes]
    usable = []
    for rec in rec_list:
        if _recipe_is_lazy(rec):
            continue
        if not merge_step_payloads(rec.get("steps") or [], payload_by_uid):
            continue
        usable.append(rec)
    kept_ids = {str(r.get("recipe_uid") or "") for r in drop_subset_recipes(usable)}
    recipes_by_step: Dict[str, List[str]] = {}
    for rec in usable:
        name = str(rec.get("recipe_name") or rec.get("recipe_uid") or "")
        for uid in _step_uids(rec):
            recipes_by_step.setdefault(uid, []).append(name)

    recipe_cards = []
    covered_uids = set()
    for rec in usable:
        steps_out = []
        weight_uids = []
        weights = []
        for step in rec.get("steps") or []:
            uid = str(step.get("uid") or "")
            payload = payload_by_uid.get(uid) or {}
            kind = str(payload.get("capability_kind") or "")
            role = str(step.get("role") or "")
            e_id = payload.get("e_id")
            try:
                e_id_int = int(e_id) if e_id is not None else None
            except (TypeError, ValueError):
                e_id_int = None
            editable = bool(uid) and is_pref_eligible_payload(payload)
            weight = _pref_weight_value(prefs.get(uid), 1) if editable else None
            if editable:
                weight_uids.append(uid)
                weights.append(int(weight or 0))
            shared = [n for n in recipes_by_step.get(uid, []) if n != str(rec.get("recipe_name") or "")]
            steps_out.append(
                {
                    "uid": uid,
                    "role": role,
                    "role_label": _STEP_ROLE_LABELS.get(role, role or "步骤"),
                    "capability_kind": kind,
                    "kind_label": _kind_label(kind),
                    "capability_desc": payload.get("capability_desc"),
                    "e_id": e_id_int,
                    "e_name": (effect_name_map or {}).get(e_id_int, "") if e_id_int is not None else "",
                    "weight_editable": editable,
                    "weight": weight,
                    "shared_recipe_names": shared,
                    "param_labels": _param_slot_labels(payload),
                }
            )
        covered_uids.update(_step_uids(rec))
        rec_uid = str(rec.get("recipe_uid") or "")
        extra = rec.get("extra") if isinstance(rec.get("extra"), dict) else {}
        covers = sorted(recipe_covers_effects(rec, payload_by_uid, set()))
        recipe_cards.append(
            {
                "recipe_uid": rec_uid,
                "recipe_name": str(rec.get("recipe_name") or rec_uid),
                "recipe_desc": extra.get("recipe_desc") or extra.get("desc"),
                "daily_use": extra.get("daily_use"),
                "pattern": extra.get("pattern"),
                "is_strategy": _recipe_has_strategy_step(rec, payload_by_uid),
                "is_lazy": False,
                "shadowed": rec_uid not in kept_ids,
                "shadowed_by": [
                    str(other.get("recipe_name") or other.get("recipe_uid") or "")
                    for other in usable
                    if other is not rec and _is_uid_subsequence(_step_uids(rec), _step_uids(other))
                ],
                "covers_effects": covers,
                "cover_effect_names": _names_for_ids(covers, effect_name_map),
                "steps": steps_out,
                "effective_weight": max(weights) if weights else 0,
                "weight_payload_uids": weight_uids,
            }
        )

    commands = []
    uncovered = []
    for payload in payload_list:
        if not is_pref_eligible_payload(payload):
            continue
        uid = str(payload.get("uid") or "")
        owners = list(recipes_by_step.get(uid) or [])
        commands.append(
            dump_command_pref_item(
                placement_id=placement_id,
                payload=payload,
                pref=prefs.get(uid),
                effect_name_map=effect_name_map,
                env_name_map=env_name_map,
                covered_by_recipes=owners,
            )
        )
        if uid not in covered_uids:
            uncovered.append(uid)

    return {
        "placement_id": placement_id,
        "commands": commands,
        "recipes": recipe_cards,
        "uncovered_payload_uids": uncovered,
    }
