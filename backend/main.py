import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional, Dict, Any
from database import AsyncSessionLocal
import models
import schemas
from effect_env_combos import resolve_ontology_combos, role_for_env_effect, resolve_effect_combo
import services
import intent_jobs
from miot_param_schema import enrich_param_schema_nl_descriptions
from intent_compose import (
    annotate_device_env_match,
    apply_candidate_meta_to_layer,
    combo_intent_score,
    compact_combo_hint,
    compose_l5_candidates,
    env_attr_as_maps,
    hinted_env_match_keys,
    payload_as_dict,
    payload_exposure,
    payload_specializes_uid,
    payload_is_l5_visible,
    reachable_device_ids as collect_reachable_device_ids,
    recipe_as_dict,
    wanted_env_from_effect_ids,
)
import home_forms as home_library
import home_api


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with AsyncSessionLocal() as db:
        await home_library.init_home_library(db)
        await db.commit()
    yield


app = FastAPI(title="IoT-ScheduleGenerator API", version="1.0.0", lifespan=lifespan)
app.include_router(home_api.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def _as_env_combo(raw: Optional[dict]) -> schemas.EnvComboView:
    data = raw or {"empty": True, "note": "", "items": []}
    return schemas.EnvComboView(
        empty=bool(data.get("empty")),
        note=str(data.get("note") or ""),
        items=[
            schemas.EnvComboItem(
                env_id=item.get("env_id"),
                env_name=str(item.get("env_name") or ""),
                match_key=str(item.get("match_key") or ""),
                role=str(item.get("role") or ""),
                polarity=str(item.get("polarity") or ""),
            )
            for item in (data.get("items") or [])
        ],
    )

async def _combo_maps(db: AsyncSession):
    domains = (await db.execute(select(models.SysDomain))).scalars().all()
    objects = (await db.execute(select(models.SysObject))).scalars().all()
    effects = (await db.execute(select(models.SysEffect))).scalars().all()
    envs = (await db.execute(select(models.SysEnvAttribute))).scalars().all()
    env_rows = [
        {"env_id": row.env_id, "env_name": row.env_name, "match_key": row.match_key or ""}
        for row in envs
    ]
    domain_combos, object_combos, effect_combos = resolve_ontology_combos(
        domains=[{"d_id": row.d_id} for row in domains],
        objects=[{"o_id": row.o_id, "d_id": row.d_id} for row in objects],
        effects=[{"e_id": row.e_id, "o_id": row.o_id} for row in effects],
        env_rows=env_rows,
    )
    return domain_combos, object_combos, effect_combos

async def _ontology_name_maps(db: AsyncSession):
    objects = (await db.execute(select(models.SysObject))).scalars().all()
    effects = (await db.execute(select(models.SysEffect))).scalars().all()
    return (
        {int(row.o_id): str(row.o_name) for row in objects},
        {int(row.e_id): str(row.e_name) for row in effects},
    )


# ==========================================
# 一级领域 API (Domain)
# ==========================================

@app.get("/api/domains/", response_model=List[schemas.DomainResponse], summary="获取所有一级领域")
async def get_domains(db: AsyncSession = Depends(get_db)):
    domain_combos, _, _ = await _combo_maps(db)
    result = await db.execute(select(models.SysDomain))
    return [
        schemas.DomainResponse(
            d_id=row.d_id,
            d_name=row.d_name,
            d_desc=row.d_desc,
            env_combo=_as_env_combo(domain_combos.get(int(row.d_id))),
        )
        for row in result.scalars().all()
    ]

@app.get("/api/objects/", response_model=List[schemas.ObjectResponse], summary="获取所有二级对象")
async def get_objects(db: AsyncSession = Depends(get_db)):
    _, object_combos, _ = await _combo_maps(db)
    result = await db.execute(select(models.SysObject))
    return [
        schemas.ObjectResponse(
            o_id=row.o_id,
            d_id=row.d_id,
            o_name=row.o_name,
            o_desc=row.o_desc,
            env_combo=_as_env_combo(object_combos.get(int(row.o_id))),
        )
        for row in result.scalars().all()
    ]

@app.get("/api/effects/", response_model=List[schemas.EffectResponse], summary="获取所有三级效果")
async def get_effects(db: AsyncSession = Depends(get_db)):
    _, _, effect_combos = await _combo_maps(db)
    result = await db.execute(select(models.SysEffect))
    return [
        schemas.EffectResponse(
            e_id=row.e_id,
            o_id=row.o_id,
            e_name=row.e_name,
            e_desc=row.e_desc,
            env_combo=_as_env_combo(effect_combos.get(int(row.e_id))),
        )
        for row in result.scalars().all()
    ]

def _env_attribute_response(
    row: models.SysEnvAttribute,
    object_names: Optional[Dict[int, str]] = None,
    effect_names: Optional[Dict[int, str]] = None,
) -> schemas.EnvAttributeResponse:
    o_ids = [int(x) for x in (row.related_o_ids or [])]
    e_ids = [int(x) for x in (row.related_e_ids or [])]
    object_names = object_names or {}
    effect_names = effect_names or {}
    match_key = row.match_key or ""
    return schemas.EnvAttributeResponse(
        env_id=row.env_id,
        env_name=row.env_name,
        env_desc=row.env_desc,
        match_key=row.match_key,
        env_kind=str(getattr(row, "env_kind", None) or models.ENV_KIND_AMBIENT),
        aliases=list(row.aliases or []),
        units=list(row.units or []),
        related_o_ids=o_ids,
        related_e_ids=e_ids,
        related_objects=[
            schemas.EnvRelatedNode(id=oid, name=object_names.get(oid) or f"对象#{oid}")
            for oid in o_ids
        ],
        related_effects=[
            schemas.EnvRelatedNode(
                id=eid,
                name=effect_names.get(eid) or f"效果#{eid}",
                role=role_for_env_effect(match_key, eid),
            )
            for eid in e_ids
        ],
        is_active=bool(row.is_active if row.is_active is not None else True),
    )

@app.get("/api/env-attributes/", response_model=List[schemas.EnvAttributeResponse], summary="获取所有环境属性")
async def get_env_attributes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.SysEnvAttribute).order_by(models.SysEnvAttribute.env_id))
    object_names, effect_names = await _ontology_name_maps(db)
    return [_env_attribute_response(row, object_names, effect_names) for row in result.scalars().all()]

def _normalize_concrete_env_set(raw) -> list:
    """将 JSONB 转为 int 列表供响应模型使用。"""
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out

def _normalize_device_source(raw, *, default: int = models.DEVICE_SOURCE_MIOT) -> int:
    """规范化具体设备生态来源：1=miot，2=google home，3=openharmony。"""
    try:
        value = int(raw if raw is not None else default)
    except (TypeError, ValueError):
        value = default
    if value not in models.DEVICE_SOURCE_LABELS:
        raise HTTPException(
            status_code=400,
            detail="source 仅支持 1(miot)、2(google home) 或 3(openharmony)",
        )
    return value

def _optional_a_ref(value) -> Optional[str]:
    name = str(value or "").strip()
    return name or None

def _concrete_device_response(row: models.ConcreteDevice) -> schemas.ConcreteDeviceResponse:
    source = _normalize_device_source(getattr(row, "source", None))
    return schemas.ConcreteDeviceResponse(
        c_instance_id=row.c_instance_id,
        c_brand=row.c_brand,
        a_ref=_optional_a_ref(getattr(row, "a_ref", None)),
        env_set=_normalize_concrete_env_set(row.env_set),
        source=source,
        source_label=models.DEVICE_SOURCE_LABELS.get(source, ""),
        c_desc=(str(getattr(row, "c_desc", None) or "").strip() or None),
    )

@app.get("/api/concrete-devices/", response_model=List[schemas.ConcreteDeviceResponse], summary="获取所有具体设备")
async def get_concrete_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ConcreteDevice))
    rows = result.scalars().all()
    return [_concrete_device_response(r) for r in rows]

@app.get(
    "/api/concrete-devices/{c_instance_id:path}",
    response_model=schemas.ConcreteDeviceResponse,
    summary="按实例 ID 获取具体设备",
)
async def get_concrete_device(c_instance_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(models.ConcreteDevice, c_instance_id)
    if not row:
        raise HTTPException(status_code=404, detail="具体设备不存在")
    return _concrete_device_response(row)

def _normalize_command_env_impact(raw) -> list:
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out

def _command_payload_to_response(row: models.CommandPayload) -> schemas.CommandPayloadResponse:
    kind = models.normalize_capability_kind(getattr(row, "capability_kind", None), row.e_id)
    supports = models.normalize_supports_e_ids(getattr(row, "supports_e_ids", None))
    if not models.kind_keeps_supports(kind):
        supports = []
    return schemas.CommandPayloadResponse(
        uid=row.uid,
        c_instance_id=row.c_instance_id,
        e_id=row.e_id,
        api_set=row.api_set,
        env_impact=_normalize_command_env_impact(row.env_impact),
        param_schema=enrich_param_schema_nl_descriptions(row.param_schema),
        capability_kind=kind,
        capability_desc=getattr(row, "capability_desc", None),
        interpretation=getattr(row, "interpretation", None),
        aligned_template_id=getattr(row, "aligned_template_id", None),
        supports_e_ids=supports,
    )

def _command_payload_to_brief(row: models.CommandPayload) -> schemas.CommandPayloadBrief:
    has_slots = bool(
        row.param_schema
        and isinstance(row.param_schema, dict)
        and row.param_schema.get("slots")
    )
    kind = models.normalize_capability_kind(getattr(row, "capability_kind", None), row.e_id)
    supports = models.normalize_supports_e_ids(getattr(row, "supports_e_ids", None))
    if not models.kind_keeps_supports(kind):
        supports = []
    data = payload_as_dict(row)
    interp = getattr(row, "interpretation", None)
    subtype = None
    if isinstance(interp, dict):
        subtype = interp.get("strategy_subtype")
    return schemas.CommandPayloadBrief(
        uid=row.uid,
        c_instance_id=row.c_instance_id,
        e_id=row.e_id,
        env_impact=_normalize_command_env_impact(row.env_impact),
        has_param_slots=has_slots,
        capability_kind=kind,
        capability_desc=getattr(row, "capability_desc", None),
        supports_e_ids=supports,
        l5_visible=payload_is_l5_visible(data),
        exposure=payload_exposure(data) or None,
        specializes_uid=payload_specializes_uid(data) or None,
        strategy_subtype=str(subtype) if subtype else None,
    )

@app.get(
    "/api/command-payloads/all/",
    response_model=List[schemas.CommandPayloadResponse],
    summary="获取全部功能指令载荷（分类树等用途）",
)
async def list_all_command_payloads(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.CommandPayload))
    rows = result.scalars().all()
    return [_command_payload_to_response(r) for r in rows]

@app.get(
    "/api/command-payloads/tree-keys/",
    response_model=List[schemas.CommandPayloadTreeKey],
    summary="分类树：仅返回 c_instance_id 与 e_id（轻量，不含 api_set）",
)
async def list_command_payload_tree_keys(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            models.CommandPayload.uid,
            models.CommandPayload.c_instance_id,
            models.CommandPayload.e_id,
            models.CommandPayload.env_impact,
        ).where(
            models.CommandPayload.e_id.isnot(None),
            models.CommandPayload.capability_kind == models.CAPABILITY_KIND_EFFECT,
        )
    )
    return [
        schemas.CommandPayloadTreeKey(
            uid=row[0],
            c_instance_id=row[1],
            e_id=row[2],
            env_impact=row[3] or [],
        )
        for row in result.all()
    ]


# 以下 /uid/... 路由须注册在 /{c_instance_id:path} 之前，避免「uid/xxx」被误当作具体设备路径

@app.get(
    "/api/command-payloads/uid/{uid:path}",
    response_model=schemas.CommandPayloadResponse,
    summary="按 uid 获取单条功能指令",
)
async def get_command_payload_by_uid(uid: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(models.CommandPayload, uid)
    if not row:
        raise HTTPException(status_code=404, detail="功能指令不存在")
    return _command_payload_to_response(row)

@app.get(
    "/api/command-payloads/brief/{c_instance_id:path}",
    response_model=List[schemas.CommandPayloadBrief],
    summary="按具体设备实例列出功能指令（轻量，不含 api_set）",
)
async def get_device_command_briefs(c_instance_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.CommandPayload).where(models.CommandPayload.c_instance_id == c_instance_id)
    )
    rows = result.scalars().all()
    return [_command_payload_to_brief(r) for r in rows]

@app.get(
    "/api/command-recipes/{c_instance_id:path}",
    response_model=List[schemas.CommandRecipeResponse],
    summary="按具体设备列出能力配方",
)
async def list_device_command_recipes(c_instance_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.CommandRecipe).where(models.CommandRecipe.c_instance_id == c_instance_id)
    )
    rows = result.scalars().all()
    return [
        schemas.CommandRecipeResponse(
            recipe_uid=r.recipe_uid,
            c_instance_id=r.c_instance_id,
            recipe_name=r.recipe_name,
            covers_effects=list(r.covers_effects or []),
            needs_auxiliary=list(r.needs_auxiliary or []),
            steps=list(r.steps or []),
            extra=r.extra,
        )
        for r in rows
    ]

@app.get(
    "/api/command-payloads/{c_instance_id:path}",
    response_model=List[schemas.CommandPayloadResponse],
    summary="按具体设备实例列出功能指令",
)
async def get_device_commands(c_instance_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.CommandPayload).where(models.CommandPayload.c_instance_id == c_instance_id)
    )
    rows = result.scalars().all()
    return [_command_payload_to_response(r) for r in rows]


# ==========================================
# 核心自动化流：原子指令集(Command Payload)批量生成
# ==========================================

def _layer_result(layer: str, data: dict, **extra) -> schemas.IntentLayerResult:
    nodes = []
    for n in data.get("selected_nodes") or []:
        if not isinstance(n, dict):
            continue
        try:
            score = int(n.get("env_match_score") or 0)
        except (TypeError, ValueError):
            score = 0
        nodes.append(
            schemas.IntentSelectedNode(
                id=n.get("id"),
                name=n.get("name") or "",
                reason=n.get("reason") or "",
                env_hint=str(n.get("env_hint") or ""),
                env_match_score=score,
                candidate_kind=str(n.get("candidate_kind") or ""),
            )
        )
    return schemas.IntentLayerResult(
        layer=layer,
        selected_nodes=nodes,
        relations=[schemas.IntentRelation(**r) for r in data.get("relations") or []],
        nl_guidance=data.get("nl_guidance") or "",
        invalid_ids=data.get("invalid_ids") or [],
        candidate_count=int(data.get("candidate_count") or 0),
        stopped=bool(extra.get("stopped", False)),
        stop_reason=extra.get("stop_reason"),
        error=extra.get("error"),
        wanted_env=list(data.get("wanted_env") or extra.get("wanted_env") or []),
    )

def _intent_progress(phase: str, layers: Dict[str, schemas.IntentLayerResult], message: str = "") -> None:
    try:
        intent_jobs.report_layers(phase, layers, message)
    except Exception:
        pass

def _take_layer_trace(data: dict, traces: List[dict]) -> dict:
    """剥离服务层附带的 _trace，写入 traces 列表。"""
    tr = data.pop("_trace", None)
    if tr:
        traces.append(tr)
    data.pop("fallback_applied", None)
    return data

def _pack_api_set_from_plan(final_plan) -> List[dict]:
    if not final_plan:
        return []
    steps = (
        final_plan.ordered_steps
        if hasattr(final_plan, "ordered_steps")
        else (final_plan.get("ordered_steps") or [])
    )
    packed = []
    for step in steps:
        item = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        packed.append(
            {
                "step": item.get("step"),
                "payload_uid": item.get("payload_uid"),
                "c_instance_id": item.get("c_instance_id"),
                "c_brand": item.get("c_brand"),
                "e_id": item.get("e_id"),
                "e_name": item.get("e_name"),
                "nl_step": item.get("nl_step"),
                "api_set": item.get("api_set"),
                "param_placeholders": item.get("param_placeholders") or [],
            }
        )
    return packed

async def _run_layer_with_timeout(coro, timeout_ms: int):
    timeout_s = max(5.0, timeout_ms / 1000.0)
    return await asyncio.wait_for(coro, timeout=timeout_s)

@app.post(
    "/api/intent/resolve/",
    response_model=schemas.IntentResolveResponse,
    summary="一键五层意图实现",
)
async def resolve_intent(body: schemas.IntentResolveRequest, db: AsyncSession = Depends(get_db)):
    from datetime import datetime

    intent_text = body.intent_text.strip()
    if not intent_text:
        raise HTTPException(status_code=400, detail="intent_text 不能为空")

    opts = body.options
    trace_id = str(uuid.uuid4())
    started_at = datetime.now()
    layers: Dict[str, schemas.IntentLayerResult] = {}
    layers_trace: List[dict] = []
    final_plan = None
    stopped_at = None
    message = None
    response: Optional[schemas.IntentResolveResponse] = None

    try:
        _intent_progress("l1", layers, "正在执行 L1 领域层推理…")
        # ---- L1 Domain ----
        domains = (await db.execute(select(models.SysDomain))).scalars().all()
        domain_cands = [
            {"d_id": d.d_id, "d_name": d.d_name, "d_desc": d.d_desc} for d in domains
        ]
        try:
            l1 = await _run_layer_with_timeout(
                services.intent_select_domains(intent_text, domain_cands),
                opts.timeout_per_layer_ms,
            )
            l1 = _take_layer_trace(l1, layers_trace)
            layers["l1"] = _layer_result("l1", l1)
            _intent_progress("l1", layers)
        except asyncio.TimeoutError:
            layers["l1"] = _layer_result("l1", {"candidate_count": len(domain_cands)}, error="L1 超时")
            stopped_at, message = "l1", "L1 领域层推理超时"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response
        except Exception as e:
            layers["l1"] = _layer_result("l1", {"candidate_count": len(domain_cands)}, error=str(e))
            stopped_at, message = "l1", f"L1 失败: {e}"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        if not layers["l1"].selected_nodes:
            layers["l1"].stopped = True
            layers["l1"].stop_reason = "无法匹配相关作用领域"
            stopped_at, message = "l1", "无法匹配相关作用领域"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        selected_d_ids = {int(n.id) for n in layers["l1"].selected_nodes}

        # ---- L2 Object ----
        _intent_progress("l2", layers, "正在执行 L2 对象层推理…")
        objects = (await db.execute(select(models.SysObject))).scalars().all()
        if opts.filter_objects_by_l1:
            objects = [o for o in objects if o.d_id in selected_d_ids]
        object_cands = [
            {"o_id": o.o_id, "d_id": o.d_id, "o_name": o.o_name, "o_desc": o.o_desc} for o in objects
        ]
        prev_l1 = {
            "selected_nodes": [n.model_dump() for n in layers["l1"].selected_nodes],
            "relations": [r.model_dump() for r in layers["l1"].relations],
            "nl_guidance": layers["l1"].nl_guidance,
        }
        try:
            l2 = await _run_layer_with_timeout(
                services.intent_select_objects(intent_text, object_cands, prev_l1),
                opts.timeout_per_layer_ms,
            )
            l2 = _take_layer_trace(l2, layers_trace)
            layers["l2"] = _layer_result("l2", l2)
            _intent_progress("l2", layers)
        except asyncio.TimeoutError:
            layers["l2"] = _layer_result("l2", {"candidate_count": len(object_cands)}, error="L2 超时")
            stopped_at, message = "l2", "L2 超时"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response
        except Exception as e:
            layers["l2"] = _layer_result("l2", {"candidate_count": len(object_cands)}, error=str(e))
            stopped_at, message = "l2", f"L2 失败: {e}"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response

        if not layers["l2"].selected_nodes:
            layers["l2"].stopped = True
            layers["l2"].stop_reason = "无法匹配相关作用对象"
            stopped_at, message = "l2", "无法匹配相关作用对象"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        selected_o_ids = {int(n.id) for n in layers["l2"].selected_nodes}

        # ---- L3 Effect ----
        _intent_progress("l3", layers, "正在执行 L3 效果层推理…")
        effects = (await db.execute(select(models.SysEffect))).scalars().all()
        if opts.filter_effects_by_l2:
            effects = [e for e in effects if e.o_id in selected_o_ids]
        env_attr_rows = (await db.execute(select(models.SysEnvAttribute))).scalars().all()
        env_maps = env_attr_as_maps(env_attr_rows)
        hinted_keys = hinted_env_match_keys(intent_text, env_maps)
        effect_cands = []
        for e in effects:
            combo = resolve_effect_combo(int(e.e_id), env_maps)
            score, _hit = combo_intent_score(combo, hinted_keys, intent_text)
            effect_cands.append(
                {
                    "e_id": e.e_id,
                    "o_id": e.o_id,
                    "e_name": e.e_name,
                    "e_desc": e.e_desc,
                    "env_combo_hint": compact_combo_hint(combo),
                    "combo_score": score,
                }
            )
        effect_cands.sort(key=lambda row: (-int(row.get("combo_score") or 0), int(row.get("e_id") or 0)))
        prev_l2 = {
            "selected_nodes": [n.model_dump() for n in layers["l2"].selected_nodes],
            "relations": [r.model_dump() for r in layers["l2"].relations],
            "nl_guidance": layers["l2"].nl_guidance,
        }
        try:
            l3 = await _run_layer_with_timeout(
                services.intent_select_effects(intent_text, effect_cands, prev_l2),
                opts.timeout_per_layer_ms,
            )
            l3 = _take_layer_trace(l3, layers_trace)
            layers["l3"] = _layer_result("l3", l3)
            apply_candidate_meta_to_layer(layers["l3"], {int(c["e_id"]): c for c in effect_cands})
            _intent_progress("l3", layers)
        except asyncio.TimeoutError:
            layers["l3"] = _layer_result("l3", {"candidate_count": len(effect_cands)}, error="L3 超时")
            stopped_at, message = "l3", "L3 超时"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response
        except Exception as e:
            layers["l3"] = _layer_result("l3", {"candidate_count": len(effect_cands)}, error=str(e))
            stopped_at, message = "l3", f"L3 失败: {e}"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response

        if not layers["l3"].selected_nodes:
            layers["l3"].stopped = True
            layers["l3"].stop_reason = "无法匹配相关具体效果"
            stopped_at, message = "l3", "无法匹配相关具体效果"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        selected_e_ids = {int(n.id) for n in layers["l3"].selected_nodes}
        wanted_env_ids, wanted_keys, wanted_labels = wanted_env_from_effect_ids(selected_e_ids, env_maps)
        if not wanted_keys:
            wanted_keys = hinted_env_match_keys(intent_text, env_maps)
        layers["l3"].wanted_env = wanted_labels
        _intent_progress("l3", layers)

        # ---- L4 Device candidates（当前环境表单实例）----
        _intent_progress("l4", layers, "正在执行 L4 设备层推理…")
        form_id = str(getattr(opts, "home_form_id", None) or "").strip()
        form_ctx = await home_library.load_form_context(db, form_id) if form_id else {}
        placement_dicts = home_library.dump_ctx_placements(form_ctx) if form_ctx else []
        if not form_id or not form_ctx or not placement_dicts:
            layers["l4"] = _layer_result(
                "l4",
                {"candidate_count": 0},
                stopped=True,
                stop_reason="请先选择环境表单并实例化设备",
            )
            stopped_at, message = "l4", "请先选择环境表单并实例化设备"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        catalog_ids = list({p["catalog_c_instance_id"] for p in placement_dicts if p.get("catalog_c_instance_id")})
        pref_payloads = (
            await db.execute(
                select(models.CommandPayload).where(models.CommandPayload.c_instance_id.in_(catalog_ids))
            )
        ).scalars().all() if catalog_ids else []
        pref_recipes = (
            await db.execute(
                select(models.CommandRecipe).where(models.CommandRecipe.c_instance_id.in_(catalog_ids))
            )
        ).scalars().all() if catalog_ids else []
        payload_dicts = [payload_as_dict(p) for p in pref_payloads]
        recipe_dicts = [recipe_as_dict(r) for r in pref_recipes]
        reachable_catalog_ids = collect_reachable_device_ids(
            payload_dicts, recipe_dicts, selected_e_ids
        )

        allowed_sources_raw = getattr(opts, "allowed_sources", None) or list(
            models.DEVICE_SOURCE_LABELS.keys()
        )
        allowed_sources = {
            int(x)
            for x in allowed_sources_raw
            if int(x) in models.DEVICE_SOURCE_LABELS
        }
        if not allowed_sources:
            layers["l4"] = _layer_result(
                "l4",
                {"candidate_count": 0},
                stopped=True,
                stop_reason="请至少选择一个参与实现的智能家居生态来源（miot / google home / openharmony）",
            )
            stopped_at, message = "l4", "请至少选择一个参与实现的智能家居生态来源"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        device_cands = []
        for pl in placement_dicts:
            catalog_id = str(pl.get("catalog_c_instance_id") or "")
            if catalog_id not in reachable_catalog_ids:
                continue
            source = int(pl.get("source") or models.DEVICE_SOURCE_MIOT)
            if source not in allowed_sources:
                continue
            device_cands.append(
                {
                    "c_instance_id": pl["placement_id"],
                    "placement_id": pl["placement_id"],
                    "catalog_c_instance_id": catalog_id,
                    "c_brand": pl.get("display_name") or pl.get("alias") or pl.get("c_brand") or catalog_id,
                    "a_ref": pl.get("a_ref"),
                    "c_desc": pl.get("c_desc"),
                    "env_set": pl.get("env_set") or [],
                    "source": source,
                    "weight": int(pl.get("weight") or 1),
                    "preference_desc": pl.get("preference_desc"),
                    "room_id": pl.get("room_id"),
                    "room_label": pl.get("room_label") or "",
                    "room_type_name": pl.get("room_type_name") or "",
                    "alias": pl.get("alias") or "",
                }
            )
        annotate_device_env_match(
            intent_text,
            device_cands,
            env_maps,
            wanted_keys=wanted_keys,
            wanted_env_ids=wanted_env_ids,
        )
        home_library.annotate_device_room_match(intent_text, device_cands)
        for d in device_cands:
            parts = [x for x in (d.get("env_match_hint"), d.get("room_match_hint")) if x]
            if parts:
                d["env_match_hint"] = "、".join(parts)
        device_cands.sort(
            key=lambda d: (
                -int(d.get("room_match_score") or 0),
                -int(d.get("env_match_score") or 0),
                -int(d.get("weight") or 0),
                str(d.get("c_instance_id") or ""),
            )
        )

        if not device_cands:
            layers["l4"] = _layer_result(
                "l4",
                {"candidate_count": 0},
                stopped=True,
                stop_reason="所选生态来源下，当前环境表单中没有能覆盖 L3 效果的设备实例",
            )
            stopped_at, message = "l4", "所选生态来源下，当前环境表单中没有能覆盖 L3 效果的设备实例"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        prev_l3 = {
            "selected_nodes": [n.model_dump() for n in layers["l3"].selected_nodes],
            "relations": [r.model_dump() for r in layers["l3"].relations],
            "nl_guidance": layers["l3"].nl_guidance,
        }
        try:
            l4 = await _run_layer_with_timeout(
                services.intent_select_devices(
                    intent_text,
                    device_cands,
                    prev_l3,
                    resolve_mode=getattr(opts, "resolve_mode", "auto") or "auto",
                ),
                opts.timeout_per_layer_ms,
            )
            l4 = _take_layer_trace(l4, layers_trace)
            layers["l4"] = _layer_result("l4", l4)
            apply_candidate_meta_to_layer(
                layers["l4"],
                {str(c.get("c_instance_id") or ""): c for c in device_cands},
            )
            layers["l4"].wanted_env = wanted_labels
            _intent_progress("l4", layers)
        except asyncio.TimeoutError:
            layers["l4"] = _layer_result("l4", {"candidate_count": len(device_cands)}, error="L4 超时")
            stopped_at, message = "l4", "L4 超时"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response
        except Exception as e:
            layers["l4"] = _layer_result("l4", {"candidate_count": len(device_cands)}, error=str(e))
            stopped_at, message = "l4", f"L4 失败: {e}"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response

        if not layers["l4"].selected_nodes:
            layers["l4"].stopped = True
            layers["l4"].stop_reason = "无法匹配相关具体设备"
            stopped_at, message = "l4", "无法匹配相关具体设备"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        selected_device_ids = {str(n.id) for n in layers["l4"].selected_nodes}
        placement_by_id = {p["placement_id"]: p for p in placement_dicts}
        selected_placements = [placement_by_id[pid] for pid in selected_device_ids if pid in placement_by_id]
        selected_catalog_ids = list({p["catalog_c_instance_id"] for p in selected_placements})

        # ---- L5 Command candidates（按表单实例展开，配方优先）----
        _intent_progress("l5", layers, "正在执行 L5 指令层推理…")
        l5_payloads = (
            await db.execute(
                select(models.CommandPayload).where(
                    models.CommandPayload.c_instance_id.in_(selected_catalog_ids)
                )
            )
        ).scalars().all() if selected_catalog_ids else []
        l5_recipes = (
            await db.execute(
                select(models.CommandRecipe).where(
                    models.CommandRecipe.c_instance_id.in_(selected_catalog_ids)
                )
            )
        ).scalars().all() if selected_catalog_ids else []
        payloads_by_catalog: Dict[str, list] = {}
        for p in l5_payloads:
            payloads_by_catalog.setdefault(p.c_instance_id, []).append(p)
        recipes_by_catalog: Dict[str, list] = {}
        for r in l5_recipes:
            recipes_by_catalog.setdefault(r.c_instance_id, []).append(r)
        prefs_by_placement = home_library.command_prefs_by_placement(form_ctx)

        effect_name_map = {
            e.e_id: e.e_name
            for e in (await db.execute(select(models.SysEffect))).scalars().all()
        }

        env_name_by_id = {}
        for row in env_maps:
            try:
                env_name_by_id[int(row.get("env_id"))] = str(row.get("env_name") or row.get("match_key") or "")
            except (TypeError, ValueError):
                continue

        command_cands = []
        for pl in selected_placements:
            catalog_id = str(pl.get("catalog_c_instance_id") or "")
            catalog_payloads = payloads_by_catalog.get(catalog_id) or []
            catalog_recipes = recipes_by_catalog.get(catalog_id) or []
            pref_by_uid = home_library.fill_command_pref_map(
                prefs_by_placement.get(pl["placement_id"]) or {},
                catalog_payloads,
            )
            display_name = pl.get("display_name") or pl.get("alias") or pl.get("c_brand") or catalog_id
            composed = compose_l5_candidates(
                payloads=[payload_as_dict(p) for p in catalog_payloads],
                recipes=[recipe_as_dict(r) for r in catalog_recipes],
                pref_by_uid=pref_by_uid,
                device_pref_by_id={catalog_id: pl},
                selected_e_ids=selected_e_ids,
                filter_by_l3=bool(opts.filter_commands_by_l3),
                effect_name_map=effect_name_map,
                device_brand_map={catalog_id: display_name},
                intent_text=intent_text,
                wanted_env_ids=wanted_env_ids,
                env_name_by_id=env_name_by_id,
            )
            command_cands.extend(home_library.stamp_l5_placement(composed, pl))

        if not command_cands:
            layers["l5"] = _layer_result(
                "l5",
                {"candidate_count": 0},
                stopped=True,
                stop_reason="当前环境表单的已选设备下没有满足权重与效果约束的指令候选（请为泛化效果指令设置 weight>0）",
            )
            stopped_at, message = "l5", "当前环境表单的已选设备下没有满足权重与效果约束的指令候选"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id,
                intent_text=intent_text,
                layers=layers,
                stopped_at=stopped_at,
                message=message,
            )
            return response

        prev_l4 = {
            "selected_nodes": [n.model_dump() for n in layers["l4"].selected_nodes],
            "relations": [r.model_dump() for r in layers["l4"].relations],
            "nl_guidance": layers["l4"].nl_guidance,
        }
        try:
            l5 = await _run_layer_with_timeout(
                services.intent_select_commands(
                    intent_text,
                    command_cands,
                    prev_l4,
                    resolve_mode=getattr(opts, "resolve_mode", "auto") or "auto",
                    max_options_per_step=getattr(opts, "max_options_per_step", 5) or 5,
                ),
                opts.timeout_per_layer_ms,
            )
            plan_data = l5.pop("final_plan", None)
            l5 = _take_layer_trace(l5, layers_trace)
            layers["l5"] = _layer_result("l5", l5)
            apply_candidate_meta_to_layer(
                layers["l5"],
                {str(c.get("uid") or ""): c for c in command_cands},
            )
            layers["l5"].wanted_env = wanted_labels
            _intent_progress("l5", layers)
            if plan_data:
                final_plan = schemas.IntentFinalPlan(**plan_data)
        except asyncio.TimeoutError:
            layers["l5"] = _layer_result("l5", {"candidate_count": len(command_cands)}, error="L5 超时")
            stopped_at, message = "l5", "L5 超时"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response
        except Exception as e:
            layers["l5"] = _layer_result("l5", {"candidate_count": len(command_cands)}, error=str(e))
            stopped_at, message = "l5", f"L5 失败: {e}"
            response = schemas.IntentResolveResponse(
                trace_id=trace_id, intent_text=intent_text, layers=layers, stopped_at=stopped_at, message=message
            )
            return response

        if not layers["l5"].selected_nodes and not (final_plan and final_plan.ordered_steps):
            layers["l5"].stopped = True
            layers["l5"].stop_reason = "无法匹配相关指令"
            stopped_at = "l5"
            message = "无法匹配相关指令"
        else:
            message = "意图实现完成"

        response = schemas.IntentResolveResponse(
            trace_id=trace_id,
            intent_text=intent_text,
            layers=layers,
            final_plan=final_plan,
            stopped_at=stopped_at,
            message=message,
        )
        return response
    finally:
        try:
            packed_apis = _pack_api_set_from_plan(final_plan)
            layers_summary = {
                k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in layers.items()
            }
            final_plan_dump = (
                final_plan.model_dump() if final_plan is not None and hasattr(final_plan, "model_dump") else final_plan
            )
            log_path = services.write_intent_trace_log(
                trace_id=trace_id,
                intent_text=intent_text,
                started_at=started_at,
                layers_trace=layers_trace,
                final_plan=final_plan_dump,
                packed_api_set=packed_apis,
                stopped_at=stopped_at,
                message=message,
                layers_summary=layers_summary,
            )
            if response is not None:
                response.trace_log_file = log_path
        except Exception as log_err:
            print(f"[intent-trace] 写入日志失败: {log_err}")

@app.post("/api/intent/jobs/", summary="启动意图实现后台作业并立即返回进度快照")
async def api_create_intent_job(body: schemas.IntentResolveRequest):
    try:
        job = await intent_jobs.start_intent_job(body.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return job.snapshot()

@app.get("/api/intent/jobs/{job_id}", summary="轮询意图实现作业进度")
async def api_get_intent_job(job_id: str):
    job = intent_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="未找到该作业，可能已因服务重启丢失，请重新解析")
    return job.snapshot()

@app.post(
    "/api/intent/pack/",
    response_model=schemas.IntentPackResponse,
    summary="参数注入并打包生成 API 指令集",
)
async def pack_intent_commands(body: schemas.IntentPackRequest):
    """
    用户填写预填参数后，将参数注入 api_set 并打包为可执行 API 指令集。
    成功时写入 API_Command_Logs/APIcommand-年-月-日-hh-mm-ss.log。
    """
    intent_text = body.intent_text.strip()
    if not intent_text:
        raise HTTPException(status_code=400, detail="intent_text 不能为空")
    if not body.final_plan or not body.final_plan.ordered_steps:
        raise HTTPException(status_code=400, detail="缺少有序指令方案 final_plan")

    final_plan_dump = body.final_plan.model_dump()
    result = services.pack_intent_api_commands(
        trace_id=body.trace_id,
        intent_text=intent_text,
        final_plan=final_plan_dump,
        user_param_values=body.user_param_values or {},
    )

    if not result.get("success"):
        return schemas.IntentPackResponse(
            success=False,
            message="参数校验未通过，请补全所有必填参数",
            plan_summary=result.get("plan_summary") or "",
            resolve_mode=result.get("resolve_mode") or "auto",
            resolve_mode_label=result.get("resolve_mode_label") or "自动模式",
            validation_errors=result.get("validation_errors") or [],
        )

    log_path = None
    try:
        log_path = services.write_api_command_log(
            trace_id=body.trace_id,
            intent_text=intent_text,
            final_plan=final_plan_dump,
            user_param_values=body.user_param_values or {},
            packed_api_set=result.get("packed_api_set") or [],
            packed_steps=result.get("packed_steps") or [],
        )
    except Exception as log_err:
        print(f"[api-command-log] 写入日志失败: {log_err}")

    return schemas.IntentPackResponse(
        success=True,
        message="API 指令集已生成",
        plan_summary=result.get("plan_summary") or "",
        resolve_mode=result.get("resolve_mode") or "auto",
        resolve_mode_label=result.get("resolve_mode_label") or "自动模式",
        packed_steps=result.get("packed_steps") or [],
        packed_api_set=result.get("packed_api_set") or [],
        log_file=log_path,
    )
