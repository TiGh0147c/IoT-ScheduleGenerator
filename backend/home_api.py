"""环境表单 / 家居库 HTTP。"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from database import AsyncSessionLocal
import home_forms as home_library
from intent_compose import is_pref_eligible_payload, payload_as_dict

router = APIRouter(prefix="/api/home", tags=["home-library"])


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def _get_form(db: AsyncSession, form_id: str) -> models.HomeForm:
    row = (
        await db.execute(select(models.HomeForm).where(models.HomeForm.form_id == form_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该环境表单")
    return row


async def _type_by_id(db: AsyncSession) -> dict:
    rows = (await db.execute(select(models.HomeRoomType))).scalars().all()
    return {int(t.type_id): t for t in rows}


def _dump_command_pref(row: models.HomeCommandPref, payload: Optional[models.CommandPayload] = None) -> dict:
    if payload is None:
        return {
            "placement_id": row.placement_id,
            "payload_uid": row.payload_uid,
            "weight": int(row.weight or 0),
            "preference_desc": row.preference_desc,
            "param_details": row.param_details,
            "e_id": None,
            "capability_kind": None,
            "capability_desc": None,
        }
    return home_library.dump_command_pref_item(
        placement_id=row.placement_id,
        payload=payload_as_dict(payload),
        pref=row,
    )


async def _name_maps_for_payloads(
    db: AsyncSession,
    payloads: List[models.CommandPayload],
    extra_e_ids: Optional[Iterable[int]] = None,
) -> tuple:
    e_ids = set()
    env_ids = set()
    for item in extra_e_ids or []:
        try:
            e_ids.add(int(item))
        except (TypeError, ValueError):
            pass
    for payload in payloads:
        if payload.e_id is not None:
            try:
                e_ids.add(int(payload.e_id))
            except (TypeError, ValueError):
                pass
        for item in payload.supports_e_ids or []:
            try:
                e_ids.add(int(item))
            except (TypeError, ValueError):
                pass
        for item in payload.env_impact or []:
            try:
                env_ids.add(int(item))
            except (TypeError, ValueError):
                pass
    effect_name_map = {}
    if e_ids:
        for row in (
            await db.execute(select(models.SysEffect).where(models.SysEffect.e_id.in_(list(e_ids))))
        ).scalars().all():
            effect_name_map[int(row.e_id)] = row.e_name
    env_name_map = {}
    if env_ids:
        for row in (
            await db.execute(
                select(models.SysEnvAttribute).where(models.SysEnvAttribute.env_id.in_(list(env_ids)))
            )
        ).scalars().all():
            env_name_map[int(row.env_id)] = row.env_name
    return effect_name_map, env_name_map


async def _placement_or_404(db: AsyncSession, form_id: str, placement_id: str) -> models.HomeDevicePlacement:
    placement = (
        await db.execute(
            select(models.HomeDevicePlacement).where(
                models.HomeDevicePlacement.form_id == form_id,
                models.HomeDevicePlacement.placement_id == placement_id,
            )
        )
    ).scalars().first()
    if not placement:
        raise HTTPException(status_code=404, detail="未找到该设备实例")
    return placement


async def _build_placement_editor(db: AsyncSession, placement: models.HomeDevicePlacement) -> dict:
    payloads = (
        await db.execute(
            select(models.CommandPayload).where(
                models.CommandPayload.c_instance_id == placement.catalog_c_instance_id
            )
        )
    ).scalars().all()
    recipes = (
        await db.execute(
            select(models.CommandRecipe).where(
                models.CommandRecipe.c_instance_id == placement.catalog_c_instance_id
            )
        )
    ).scalars().all()
    prefs = {
        r.payload_uid: r
        for r in (
            await db.execute(
                select(models.HomeCommandPref).where(
                    models.HomeCommandPref.placement_id == placement.placement_id
                )
            )
        ).scalars().all()
    }
    extra_e_ids = []
    for rec in recipes:
        extra_e_ids.extend(rec.covers_effects or [])
    effect_name_map, env_name_map = await _name_maps_for_payloads(db, payloads, extra_e_ids)
    return home_library.build_command_weight_editor(
        placement_id=placement.placement_id,
        payloads=payloads,
        recipes=recipes,
        pref_by_uid=prefs,
        effect_name_map=effect_name_map,
        env_name_map=env_name_map,
    )


async def _upsert_command_pref_row(
    db: AsyncSession,
    *,
    placement: models.HomeDevicePlacement,
    uid: str,
    weight: int,
    preference_desc: Optional[str] = None,
    param_details: Any = None,
    set_param_details: bool = False,
) -> models.HomeCommandPref:
    payload = await db.get(models.CommandPayload, uid)
    if not payload or payload.c_instance_id != placement.catalog_c_instance_id:
        raise HTTPException(status_code=404, detail=f"该实例下没有指令 {uid}")
    if not is_pref_eligible_payload(payload_as_dict(payload)):
        raise HTTPException(status_code=400, detail="该指令不可设权重")
    row = (
        await db.execute(
            select(models.HomeCommandPref).where(
                models.HomeCommandPref.placement_id == placement.placement_id,
                models.HomeCommandPref.payload_uid == uid,
            )
        )
    ).scalars().first()
    if row:
        row.weight = int(weight)
        if preference_desc is not None:
            row.preference_desc = preference_desc
        if set_param_details:
            row.param_details = param_details
        return row
    row = models.HomeCommandPref(
        placement_id=placement.placement_id,
        payload_uid=uid,
        weight=int(weight),
        preference_desc=preference_desc,
        param_details=param_details if set_param_details else None,
    )
    db.add(row)
    return row


@router.get("/room-types/", response_model=List[schemas.HomeRoomTypeResponse])
async def list_room_types(db: AsyncSession = Depends(get_db)):
    await home_library.seed_room_types(db)
    await db.commit()
    rows = (
        await db.execute(
            select(models.HomeRoomType).order_by(models.HomeRoomType.is_preset.desc(), models.HomeRoomType.type_id)
        )
    ).scalars().all()
    return [home_library.dump_room_type(r) for r in rows]


@router.post("/room-types/", response_model=schemas.HomeRoomTypeResponse)
async def create_room_type(body: schemas.HomeRoomTypeCreate, db: AsyncSession = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="房间种类名不能为空")
    exists = (
        await db.execute(select(models.HomeRoomType).where(models.HomeRoomType.name == name))
    ).scalars().first()
    if exists:
        raise HTTPException(status_code=409, detail="已有同名房间种类")
    row = models.HomeRoomType(name=name, is_preset=False, is_active=True)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return home_library.dump_room_type(row)


@router.put("/room-types/{type_id}", response_model=schemas.HomeRoomTypeResponse)
async def update_room_type(type_id: int, body: schemas.HomeRoomTypeUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(models.HomeRoomType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="未找到该房间种类")
    if body.name is not None:
        if row.is_preset:
            raise HTTPException(status_code=400, detail="预设房间种类不可改名")
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="房间种类名不能为空")
        clash = (
            await db.execute(
                select(models.HomeRoomType).where(
                    models.HomeRoomType.name == name,
                    models.HomeRoomType.type_id != type_id,
                )
            )
        ).scalars().first()
        if clash:
            raise HTTPException(status_code=409, detail="已有同名房间种类")
        row.name = name
    if body.is_active is not None:
        row.is_active = bool(body.is_active)
    await db.commit()
    await db.refresh(row)
    return home_library.dump_room_type(row)


@router.delete("/room-types/{type_id}")
async def delete_room_type(type_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(models.HomeRoomType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="未找到该房间种类")
    if row.is_preset:
        raise HTTPException(status_code=400, detail="预设房间种类不可删除，可停用")
    used = (
        await db.execute(select(models.HomeRoom.room_id).where(models.HomeRoom.type_id == type_id).limit(1))
    ).first()
    if used:
        raise HTTPException(status_code=409, detail="该种类已被房间实例引用，无法删除")
    await db.delete(row)
    await db.commit()
    return {"message": "已删除房间种类"}


@router.get("/forms/", response_model=List[schemas.HomeFormResponse])
async def list_forms(db: AsyncSession = Depends(get_db)):
    await home_library.init_home_library(db)
    await db.commit()
    rows = (await db.execute(select(models.HomeForm).order_by(models.HomeForm.name, models.HomeForm.form_id))).scalars().all()
    return [home_library.dump_form(r) for r in rows]


@router.post("/forms/", response_model=schemas.HomeFormResponse)
async def create_form(body: schemas.HomeFormCreate, db: AsyncSession = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="表单名称不能为空")
    row = models.HomeForm(form_id=home_library.new_form_id(), name=name, note=(body.note or "").strip() or None)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return home_library.dump_form(row)


@router.get("/forms/{form_id}", response_model=schemas.HomeFormBundleResponse)
async def get_form_bundle(form_id: str, db: AsyncSession = Depends(get_db)):
    ctx = await home_library.load_form_context(db, form_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="未找到该环境表单")
    placements = home_library.dump_ctx_placements(ctx)
    payload_by_uid = {}
    uids = [c.payload_uid for c in ctx["command_prefs"]]
    if uids:
        for row in (
            await db.execute(select(models.CommandPayload).where(models.CommandPayload.uid.in_(uids)))
        ).scalars().all():
            payload_by_uid[row.uid] = row
    return {
        "form": home_library.dump_form(ctx["form"]),
        "rooms": [home_library.dump_room(r, ctx["type_by_id"]) for r in ctx["rooms"]],
        "placements": placements,
        "command_prefs": [_dump_command_pref(c, payload_by_uid.get(c.payload_uid)) for c in ctx["command_prefs"]],
    }


@router.put("/forms/{form_id}", response_model=schemas.HomeFormResponse)
async def update_form(form_id: str, body: schemas.HomeFormUpdate, db: AsyncSession = Depends(get_db)):
    row = await _get_form(db, form_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="表单名称不能为空")
        row.name = name
    if body.note is not None:
        row.note = body.note.strip() or None
    await db.commit()
    await db.refresh(row)
    return home_library.dump_form(row)


@router.delete("/forms/{form_id}")
async def delete_form(form_id: str, db: AsyncSession = Depends(get_db)):
    row = await _get_form(db, form_id)
    total = (await db.execute(select(func.count()).select_from(models.HomeForm))).scalar_one()
    if int(total or 0) <= 1:
        raise HTTPException(status_code=400, detail="至少保留一份环境表单")
    await db.delete(row)
    await db.commit()
    return {"message": "已删除环境表单"}


@router.post("/forms/{form_id}/rooms/", response_model=schemas.HomeRoomResponse)
async def create_room(form_id: str, body: schemas.HomeRoomCreate, db: AsyncSession = Depends(get_db)):
    await _get_form(db, form_id)
    type_row = await db.get(models.HomeRoomType, body.type_id)
    if not type_row or not type_row.is_active:
        raise HTTPException(status_code=400, detail="请选择有效的房间种类")
    max_order = (
        await db.execute(select(func.max(models.HomeRoom.sort_order)).where(models.HomeRoom.form_id == form_id))
    ).scalar_one()
    label = (body.label or "").strip() or type_row.name
    row = models.HomeRoom(
        form_id=form_id,
        type_id=type_row.type_id,
        label=label,
        sort_order=int(max_order or 0) + 1,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return home_library.dump_room(row, {int(type_row.type_id): type_row})


@router.put("/forms/{form_id}/rooms/{room_id}", response_model=schemas.HomeRoomResponse)
async def update_room(form_id: str, room_id: int, body: schemas.HomeRoomUpdate, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(models.HomeRoom).where(models.HomeRoom.form_id == form_id, models.HomeRoom.room_id == room_id)
        )
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该房间")
    if body.label is not None:
        label = body.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="房间名称不能为空")
        row.label = label
    if body.sort_order is not None:
        row.sort_order = int(body.sort_order)
    await db.commit()
    await db.refresh(row)
    types = await _type_by_id(db)
    return home_library.dump_room(row, types)


@router.delete("/forms/{form_id}/rooms/{room_id}")
async def delete_room(form_id: str, room_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(models.HomeRoom).where(models.HomeRoom.form_id == form_id, models.HomeRoom.room_id == room_id)
        )
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该房间")
    await db.delete(row)
    await db.commit()
    return {"message": "已删除房间（其上设备的房间标记已清空）"}


async def _create_one_placement(
    db: AsyncSession,
    *,
    form_id: str,
    catalog_c_instance_id: str,
    alias: Optional[str],
    room_id: Optional[int],
    weight: int,
    preference_desc: Optional[str],
) -> models.HomeDevicePlacement:
    catalog = await db.get(models.ConcreteDevice, catalog_c_instance_id)
    if not catalog:
        raise HTTPException(status_code=404, detail=f"能力库中没有设备 {catalog_c_instance_id}")
    if room_id is not None:
        room = (
            await db.execute(
                select(models.HomeRoom).where(
                    models.HomeRoom.form_id == form_id, models.HomeRoom.room_id == room_id
                )
            )
        ).scalars().first()
        if not room:
            raise HTTPException(status_code=400, detail="房间不属于当前表单")
    display_alias = (alias or "").strip() or catalog.c_brand or catalog_c_instance_id
    placement = models.HomeDevicePlacement(
        placement_id=home_library.new_placement_id(),
        form_id=form_id,
        catalog_c_instance_id=catalog_c_instance_id,
        room_id=room_id,
        alias=display_alias,
        weight=int(weight),
        preference_desc=preference_desc,
    )
    db.add(placement)
    await db.flush()
    for pref in await home_library.default_command_prefs_for_catalog(db, catalog_c_instance_id):
        db.add(
            models.HomeCommandPref(
                placement_id=placement.placement_id,
                payload_uid=pref["payload_uid"],
                weight=pref["weight"],
                preference_desc=pref["preference_desc"],
                param_details=pref["param_details"],
            )
        )
    return placement


@router.post("/forms/{form_id}/placement", response_model=schemas.HomePlacementResponse)
async def create_placement(
    form_id: str,
    body: schemas.HomePlacementCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_form(db, form_id)
    row = await _create_one_placement(
        db,
        form_id=form_id,
        catalog_c_instance_id=body.catalog_c_instance_id.strip(),
        alias=body.alias,
        room_id=body.room_id,
        weight=body.weight,
        preference_desc=body.preference_desc,
    )
    await db.commit()
    ctx = await home_library.load_form_context(db, form_id)
    placed = next((p for p in ctx["placements"] if p.placement_id == row.placement_id), row)
    return home_library.dump_ctx_placement(ctx, placed)


@router.post("/forms/{form_id}/placements/", response_model=List[schemas.HomePlacementResponse])
async def create_placements(
    form_id: str,
    body: schemas.HomePlacementBatchCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_form(db, form_id)
    created = []
    for cid in body.catalog_c_instance_ids:
        cid = str(cid or "").strip()
        if not cid:
            continue
        created.append(
            await _create_one_placement(
                db,
                form_id=form_id,
                catalog_c_instance_id=cid,
                alias=None,
                room_id=body.room_id,
                weight=body.weight,
                preference_desc=body.preference_desc,
            )
        )
    if not created:
        raise HTTPException(status_code=400, detail="请至少选择一台能力库设备")
    await db.commit()
    ctx = await home_library.load_form_context(db, form_id)
    out = []
    created_ids = {p.placement_id for p in created}
    for p in ctx["placements"]:
        if p.placement_id not in created_ids:
            continue
        out.append(home_library.dump_ctx_placement(ctx, p))
    return out


@router.put("/forms/{form_id}/placements/{placement_id}", response_model=schemas.HomePlacementResponse)
async def update_placement(
    form_id: str,
    placement_id: str,
    body: schemas.HomePlacementUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(models.HomeDevicePlacement).where(
                models.HomeDevicePlacement.form_id == form_id,
                models.HomeDevicePlacement.placement_id == placement_id,
            )
        )
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该设备实例")
    if body.alias is not None:
        alias = body.alias.strip()
        if not alias:
            raise HTTPException(status_code=400, detail="别名不能为空")
        row.alias = alias
    if body.clear_room:
        row.room_id = None
    elif body.room_id is not None:
        room = (
            await db.execute(
                select(models.HomeRoom).where(
                    models.HomeRoom.form_id == form_id, models.HomeRoom.room_id == body.room_id
                )
            )
        ).scalars().first()
        if not room:
            raise HTTPException(status_code=400, detail="房间不属于当前表单")
        row.room_id = body.room_id
    if body.weight is not None:
        row.weight = int(body.weight)
    if body.preference_desc is not None:
        row.preference_desc = body.preference_desc or None
    await db.commit()
    ctx = await home_library.load_form_context(db, form_id)
    p = next((x for x in ctx["placements"] if x.placement_id == placement_id), row)
    return home_library.dump_ctx_placement(ctx, p)


@router.delete("/forms/{form_id}/placements/{placement_id}")
async def delete_placement(form_id: str, placement_id: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(models.HomeDevicePlacement).where(
                models.HomeDevicePlacement.form_id == form_id,
                models.HomeDevicePlacement.placement_id == placement_id,
            )
        )
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该设备实例")
    await db.delete(row)
    await db.commit()
    return {"message": "已从环境表单移除该设备实例"}


@router.put("/forms/{form_id}/placements-batch")
async def patch_placements_batch(
    form_id: str,
    body: schemas.HomePlacementBatchPatch,
    db: AsyncSession = Depends(get_db),
):
    await _get_form(db, form_id)
    if body.weight is None and body.command_weight is None:
        raise HTTPException(status_code=400, detail="请指定设备权重或指令权重")
    rows = (
        await db.execute(
            select(models.HomeDevicePlacement).where(
                models.HomeDevicePlacement.form_id == form_id,
                models.HomeDevicePlacement.placement_id.in_(body.placement_ids),
            )
        )
    ).scalars().all()
    found = {r.placement_id: r for r in rows}
    missing = [pid for pid in body.placement_ids if pid not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"未找到设备实例：{', '.join(missing)}")
    updated_commands = 0
    for row in rows:
        if body.weight is not None:
            row.weight = int(body.weight)
        if body.command_weight is None:
            continue
        prefs = await home_library.default_command_prefs_for_catalog(db, row.catalog_c_instance_id)
        existing = {
            p.payload_uid: p
            for p in (
                await db.execute(
                    select(models.HomeCommandPref).where(models.HomeCommandPref.placement_id == row.placement_id)
                )
            ).scalars().all()
        }
        for item in prefs:
            uid = item["payload_uid"]
            current = existing.get(uid)
            if current:
                current.weight = int(body.command_weight)
            else:
                db.add(
                    models.HomeCommandPref(
                        placement_id=row.placement_id,
                        payload_uid=uid,
                        weight=int(body.command_weight),
                        preference_desc=None,
                        param_details=None,
                    )
                )
            updated_commands += 1
    await db.commit()
    return {
        "updated_placements": len(rows),
        "updated_commands": updated_commands,
    }


@router.get(
    "/forms/{form_id}/placements/{placement_id}/commands",
    response_model=schemas.HomeCommandEditorResponse,
)
async def list_placement_commands(form_id: str, placement_id: str, db: AsyncSession = Depends(get_db)):
    placement = await _placement_or_404(db, form_id, placement_id)
    return await _build_placement_editor(db, placement)


@router.put(
    "/forms/{form_id}/placements/{placement_id}/commands",
    response_model=schemas.HomeCommandEditorResponse,
)
async def upsert_placement_commands_batch(
    form_id: str,
    placement_id: str,
    body: schemas.HomeCommandPrefBatchUpsert,
    db: AsyncSession = Depends(get_db),
):
    placement = await _placement_or_404(db, form_id, placement_id)
    for item in body.items:
        await _upsert_command_pref_row(
            db,
            placement=placement,
            uid=item.payload_uid,
            weight=item.weight,
            preference_desc=item.preference_desc,
            param_details=item.param_details,
            set_param_details=item.param_details is not None,
        )
    await db.commit()
    return await _build_placement_editor(db, placement)


@router.put(
    "/forms/{form_id}/placements/{placement_id}/commands/{uid:path}",
    response_model=schemas.HomeCommandPrefResponse,
)
async def upsert_placement_command(
    form_id: str,
    placement_id: str,
    uid: str,
    body: schemas.HomeCommandPrefUpsert,
    db: AsyncSession = Depends(get_db),
):
    placement = await _placement_or_404(db, form_id, placement_id)
    row = await _upsert_command_pref_row(
        db,
        placement=placement,
        uid=uid,
        weight=body.weight,
        preference_desc=body.preference_desc,
        param_details=body.param_details,
        set_param_details=body.param_details is not None,
    )
    payload = await db.get(models.CommandPayload, uid)
    await db.commit()
    await db.refresh(row)
    return _dump_command_pref(row, payload)
