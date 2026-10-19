import os
import json
import re
from typing import Optional, Any, Dict, List, Set, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from miot_param_schema import (
    build_param_placeholders_from_schema,
    param_schema_summary,
    inject_params_into_api_set,
)
from dotenv import load_dotenv
from intent_compose import bind_plan_placeholders, drop_unfilled_optional_api_ops

load_dotenv(override=True)

INTENT_TRACE_DIR = "Intent_Trace_Logs"
API_COMMAND_LOG_DIR = "API_Command_Logs"

def _resolve_mode_meta(resolve_mode: Optional[str] = None) -> dict:
    """
    统一解析意图寻址模式元信息。
    内部取值：auto / interactive
    文件名前缀：auto / complex
    展示名：自动模式 / 复杂模式
    """
    raw = str(resolve_mode or "auto").strip().lower()
    interactive = raw in {"interactive", "complex", "复杂", "复杂模式"}
    if interactive:
        return {
            "resolve_mode": "interactive",
            "file_tag": "complex",
            "label_zh": "复杂模式",
            "label_en": "complex",
        }
    return {
        "resolve_mode": "auto",
        "file_tag": "auto",
        "label_zh": "自动模式",
        "label_en": "auto",
    }


def _extract_resolve_mode(*sources) -> str:
    """从 final_plan / layer_input 等来源提取 resolve_mode。"""
    for src in sources:
        if isinstance(src, dict) and src.get("resolve_mode"):
            return str(src.get("resolve_mode"))
        if isinstance(src, list):
            for item in reversed(src):
                if not isinstance(item, dict):
                    continue
                if item.get("resolve_mode"):
                    return str(item.get("resolve_mode"))
                inp = item.get("input")
                if isinstance(inp, dict) and inp.get("resolve_mode"):
                    return str(inp.get("resolve_mode"))
                out = item.get("output")
                if isinstance(out, dict) and out.get("resolve_mode"):
                    return str(out.get("resolve_mode"))
    return "auto"


# 初始化 DeepSeek 模型
# 移除了 with_structured_output，返回的是一个灵活的嵌套 JSON，
# 改用 response_format 强制要求输出 JSON 字符串。
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
    temperature=0.1,
    model_kwargs={"response_format": {"type": "json_object"}}
)


# ==========================================
# 意图寻址：五层递进 LLM 推理
# ==========================================

def _parse_llm_json(content: str) -> dict:
    """尽量从模型输出中解析 JSON 对象。"""
    text = (content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def _normalize_id(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _filter_layer_selection(raw: dict, valid_id_set: set, name_by_id: dict, prefer_int: bool = False) -> dict:
    """校验 selected_nodes / relations 的 ID 必须落在候选集内。"""

    def coerce_id(raw_id):
        nid = _normalize_id(raw_id)
        if not nid:
            return None, None
        if prefer_int and nid.isdigit():
            try:
                return nid, int(nid)
            except ValueError:
                return nid, raw_id
        return nid, nid if not prefer_int else raw_id

    selected = []
    invalid_ids = []
    seen = set()
    for item in raw.get("selected_nodes") or []:
        if not isinstance(item, dict):
            continue
        nid, typed = coerce_id(item.get("id"))
        if not nid:
            continue
        if nid not in valid_id_set:
            invalid_ids.append(item.get("id"))
            continue
        if nid in seen:
            continue
        seen.add(nid)
        selected.append(
            {
                "id": typed,
                "name": str(item.get("name") or name_by_id.get(nid, "")),
                "reason": str(item.get("reason") or ""),
            }
        )

    relations = []
    for rel in raw.get("relations") or []:
        if not isinstance(rel, dict):
            continue
        from_nid, from_typed = coerce_id(rel.get("from_id"))
        to_nid, to_typed = coerce_id(rel.get("to_id"))
        if not from_nid or not to_nid:
            continue
        if from_nid not in valid_id_set or to_nid not in valid_id_set:
            if from_nid and from_nid not in valid_id_set:
                invalid_ids.append(rel.get("from_id"))
            if to_nid and to_nid not in valid_id_set:
                invalid_ids.append(rel.get("to_id"))
            continue
        relations.append(
            {
                "type": str(rel.get("type") or "cooperate"),
                "from_id": from_typed,
                "to_id": to_typed,
                "note": str(rel.get("note") or ""),
            }
        )

    return {
        "selected_nodes": selected,
        "relations": relations,
        "nl_guidance": str(raw.get("nl_guidance") or ""),
        "invalid_ids": invalid_ids,
    }


_LAYER_JSON_RULES = """
【强制输出格式】
只能输出一个合法 JSON 对象，不要 markdown，不要额外解释。结构：
{
  "selected_nodes": [{"id": <候选中的主键>, "name": "<名称>", "reason": "<简述>"}],
  "relations": [{"type": "cooperate|mutex|sequence|alternative", "from_id": ..., "to_id": ..., "note": "..."}],
  "nl_guidance": "供下一层推理使用的自然语言指导方针"
}
规则：
1. selected_nodes 的 id 必须来自候选列表，禁止编造。
2. 【最重要】只要候选列表非空且与意图可能相关，就必须至少选出 1 个节点；禁止因“不够确定/没有特殊偏好/多个差不多”而输出空列表。
3. 若多个候选权重相同、或没有 preference_desc 等特殊偏好描述，请根据意图语义自由择优；难以区分时任选其一即可，并在 reason 中说明“权重相同，自由择一”。
4. 仅当候选与意图完全无关时，才允许空 selected_nodes，并在 nl_guidance 说明原因。
5. 多节点时尽量给出 relations（协同/互斥/顺序/替代）。
"""

_LAYER_JSON_RULES_INTERACTIVE_DEVICES = """
【强制输出格式】
只能输出一个合法 JSON 对象，不要 markdown，不要额外解释。结构：
{
  "selected_nodes": [{"id": <候选中的主键>, "name": "<名称>", "reason": "<简述>"}],
  "relations": [{"type": "cooperate|mutex|sequence|alternative", "from_id": ..., "to_id": ..., "note": "..."}],
  "nl_guidance": "供下一层推理使用的自然语言指导方针"
}
规则：
1. selected_nodes 的 id 必须来自候选列表，禁止编造。
2. 【最重要】必须把所有能实现用户意图的相关具体设备全部选出；禁止因“权重相同/没有特殊偏好/多个差不多”而只选 1 个。
3. 同类可替代设备（相同 a_ref 或能力相近）只要与意图相关，全部列入 selected_nodes。
4. 仅当某设备与意图完全无关时才可不选；禁止输出空列表（候选非空且可能相关时）。
5. 多节点时用 relations 标注 alternative（可互相替代）或 cooperate。
"""


def _candidate_int(item: dict, *keys: str) -> int:
    for key in keys:
        raw = item.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def _candidate_sort_key(item: dict) -> tuple:
    """环境匹配优先，其次权重；同分保持稳定顺序。"""
    room_score = _candidate_int(item, "room_match_score")
    env_score = _candidate_int(item, "env_match_score", "combo_score")
    weight = _candidate_int(item, "weight", "device_weight")
    nid = _normalize_id(
        item.get("id")
        or item.get("uid")
        or item.get("c_instance_id")
        or item.get("d_id")
        or item.get("o_id")
        or item.get("e_id")
        or ""
    )
    return (-room_score, -env_score, -weight, nid)


def _ensure_nonempty_selection(
    filtered: dict,
    candidates: list,
    *,
    id_key: str,
    name_key: str,
    prefer_int: bool = False,
) -> dict:
    """
    模型未选出时的保底：环境匹配优先、其次权重；保证后续链路有有效输出。
    """
    if filtered.get("selected_nodes"):
        return filtered
    if not candidates:
        return filtered

    ranked = sorted(candidates, key=_candidate_sort_key)
    chosen = ranked[0]
    top_env = _candidate_int(chosen, "env_match_score", "combo_score")
    top_weight = _candidate_int(chosen, "weight", "device_weight")

    raw_id = chosen.get(id_key)
    nid = _normalize_id(raw_id)
    if prefer_int and nid.isdigit():
        typed_id = int(nid)
    else:
        typed_id = nid if not prefer_int else raw_id

    reason_bits = []
    if top_env:
        reason_bits.append(f"环境匹配 {top_env}")
    reason_bits.append(f"权重 {top_weight}")
    reason = "模型未给出有效选择；系统按" + "、".join(reason_bits) + "保底择一"

    filtered["selected_nodes"] = [
        {
            "id": typed_id,
            "name": str(chosen.get(name_key) or nid),
            "reason": reason,
        }
    ]
    guidance = filtered.get("nl_guidance") or ""
    suffix = "【系统保底】候选非空但模型未选出，已自动择一以保证后续有效输出。"
    filtered["nl_guidance"] = f"{guidance}\n{suffix}".strip() if guidance else suffix
    filtered["fallback_applied"] = True
    return filtered


async def _ainvoke_intent_json(prompt_template: str, variables: dict) -> tuple:
    """
    仅替换已知占位符，避免 PromptTemplate 把 JSON 示例中的 {} 当成变量。
    返回: (parsed_dict, rendered_prompt, raw_response_text)
    """
    text = prompt_template
    for key, value in variables.items():
        text = text.replace("{" + key + "}", str(value))
    result = await llm.ainvoke(text)
    content = result.content if hasattr(result, "content") else str(result)
    return _parse_llm_json(content), text, content


def _sort_selected_nodes_by_candidate_weight(
    filtered: dict,
    candidates: list,
    id_key: str,
) -> dict:
    """将已选节点按候选权重降序排列，保证「第一个选择」是权重最高者。"""
    selected = list(filtered.get("selected_nodes") or [])
    if len(selected) <= 1 or not candidates:
        return filtered
    by_id: Dict[str, dict] = {}
    for item in candidates:
        nid = _normalize_id(item.get(id_key) or item.get("id") or item.get("uid") or "")
        if nid:
            by_id[nid] = item

    def node_rank(node: dict) -> tuple:
        nid = _normalize_id(node.get("id"))
        cand = by_id.get(nid) or {}
        return (
            -_candidate_int(cand, "env_match_score", "combo_score"),
            -_candidate_int(cand, "weight", "device_weight"),
            nid,
        )

    filtered["selected_nodes"] = sorted(selected, key=node_rank)
    return filtered


def _public_layer_output(filtered: dict) -> dict:
    """去掉内部字段后的层输出，供日志与下游使用。"""
    out = {
        "selected_nodes": filtered.get("selected_nodes") or [],
        "relations": filtered.get("relations") or [],
        "nl_guidance": filtered.get("nl_guidance") or "",
        "invalid_ids": filtered.get("invalid_ids") or [],
        "candidate_count": filtered.get("candidate_count") or 0,
        "fallback_applied": bool(filtered.get("fallback_applied")),
    }
    if filtered.get("parallel_devices_expanded"):
        out["parallel_devices_expanded"] = filtered.get("parallel_devices_expanded")
    if filtered.get("weight_rank_decisions"):
        out["weight_rank_decisions"] = filtered.get("weight_rank_decisions")
    return out


def _attach_layer_trace(
    filtered: dict,
    *,
    layer: str,
    layer_input: dict,
    prompt: str,
    raw_response: str,
    raw_parsed: dict,
) -> dict:
    filtered["_trace"] = {
        "layer": layer,
        "input": layer_input,
        "prompt": prompt,
        "raw_llm_response": raw_response,
        "raw_parsed": raw_parsed if isinstance(raw_parsed, dict) else {},
        "output": _public_layer_output(filtered),
    }
    return filtered


def _compact_trace_value(value: Any, *, max_list: int = 30, max_str: int = 4000) -> Any:
    """压缩日志中的大对象，避免候选/提示词把整份日志撑爆。"""
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) <= max_str:
            return value
        return value[:max_str] + f"\n...（已截断，原长度 {len(value)}）"
    if isinstance(value, list):
        if len(value) <= max_list:
            return [_compact_trace_value(v, max_list=max_list, max_str=max_str) for v in value]
        head = [_compact_trace_value(v, max_list=max_list, max_str=max_str) for v in value[:max_list]]
        head.append({"_truncated": True, "omitted": len(value) - max_list, "total": len(value)})
        return head
    if isinstance(value, dict):
        # 候选列表仅保留关键字段
        if "candidates" in value and isinstance(value.get("candidates"), list):
            slim = dict(value)
            cands = value.get("candidates") or []
            slim["candidate_count"] = slim.get("candidate_count") or len(cands)
            slim["candidates_preview"] = [
                {
                    k: item.get(k)
                    for k in (
                        "env_id",
                        "env_name",
                        "match_key",
                        "roles",
                        "grade",
                        "hint_verb",
                        "uid",
                        "d_id",
                        "d_name",
                        "o_id",
                        "o_name",
                        "e_id",
                        "e_name",
                        "c_instance_id",
                        "c_brand",
                        "a_ref",
                        "weight",
                        "device_weight",
                    )
                    if isinstance(item, dict) and item.get(k) is not None
                }
                for item in cands[:max_list]
            ]
            if len(cands) > max_list:
                slim["candidates_preview"].append(
                    {"_truncated": True, "omitted": len(cands) - max_list, "total": len(cands)}
                )
            slim.pop("candidates", None)
            return {k: _compact_trace_value(v, max_list=max_list, max_str=max_str) for k, v in slim.items()}
        return {k: _compact_trace_value(v, max_list=max_list, max_str=max_str) for k, v in value.items()}
    return value


def _summarize_final_plan_for_trace(final_plan: Any) -> Any:
    if not isinstance(final_plan, dict):
        return final_plan
    steps = []
    for step in final_plan.get("ordered_steps") or []:
        if not isinstance(step, dict):
            continue
        options_summary = []
        for opt in step.get("options") or []:
            if not isinstance(opt, dict):
                continue
            variants = opt.get("command_variants") or []
            options_summary.append(
                {
                    "payload_uid": opt.get("payload_uid"),
                    "c_brand": opt.get("c_brand"),
                    "device_weight": opt.get("device_weight"),
                    "command_weight": opt.get("command_weight"),
                    "is_recommended": opt.get("is_recommended"),
                    "goal_analysis": opt.get("goal_analysis"),
                    "variant_count": len(variants),
                    "top_variants": [
                        {
                            "payload_uid": v.get("payload_uid"),
                            "command_weight": v.get("command_weight"),
                            "is_recommended": v.get("is_recommended"),
                            "goal_analysis": v.get("goal_analysis"),
                        }
                        for v in variants[:4]
                        if isinstance(v, dict)
                    ],
                }
            )
        steps.append(
            {
                "step": step.get("step"),
                "step_intent": step.get("step_intent"),
                "selected_uid": step.get("selected_uid") or step.get("payload_uid"),
                "c_brand": step.get("c_brand"),
                "nl_step": step.get("nl_step"),
                "selection_required": step.get("selection_required"),
                "options": options_summary,
            }
        )
    return {
        "plan_summary": final_plan.get("plan_summary"),
        "nl_guidance": final_plan.get("nl_guidance"),
        "resolve_mode": final_plan.get("resolve_mode"),
        "weight_rank_decisions": final_plan.get("weight_rank_decisions") or [],
        "ordered_steps": steps,
        "relations": final_plan.get("relations") or [],
    }


def write_intent_trace_log(
    *,
    trace_id: str,
    intent_text: str,
    started_at,
    layers_trace: list,
    final_plan,
    packed_api_set: list,
    stopped_at: Optional[str],
    message: Optional[str],
    layers_summary: Optional[dict] = None,
) -> str:
    """
    写入意图→指令集生成 Trace 日志（结构化分段）：
    1) 概览  2) 流水线摘要  3) 权重择优  4) 最终方案  5) 打包 API  6) 各层详情附录
    返回相对路径。
    """
    from datetime import datetime

    if not os.path.exists(INTENT_TRACE_DIR):
        os.makedirs(INTENT_TRACE_DIR)

    ts = started_at if hasattr(started_at, "strftime") else datetime.now()
    resolve_mode_raw = _extract_resolve_mode(final_plan, layers_trace)
    mode_meta = _resolve_mode_meta(resolve_mode_raw)
    resolve_mode = mode_meta["resolve_mode"]
    file_tag = mode_meta["file_tag"]
    mode_label = mode_meta["label_zh"]

    filename = f"trace-{file_tag}-{ts.strftime('%Y-%m-%d-%H-%M-%S')}.log"
    save_path = os.path.join(INTENT_TRACE_DIR, filename)
    if os.path.exists(save_path):
        for i in range(1, 1000):
            alt = os.path.join(
                INTENT_TRACE_DIR,
                f"trace-{file_tag}-{ts.strftime('%Y-%m-%d-%H-%M-%S')}-{i}.log",
            )
            if not os.path.exists(alt):
                save_path = alt
                filename = os.path.basename(alt)
                break

    weight_decisions = []
    if isinstance(final_plan, dict):
        weight_decisions = list(final_plan.get("weight_rank_decisions") or [])
    if not weight_decisions:
        for layer_tr in layers_trace or []:
            if not isinstance(layer_tr, dict):
                continue
            out = layer_tr.get("output") or {}
            if isinstance(out, dict) and out.get("weight_rank_decisions"):
                weight_decisions = list(out.get("weight_rank_decisions") or [])
                break

    pipeline_rows = []
    for idx, layer_tr in enumerate(layers_trace or [], start=1):
        if not isinstance(layer_tr, dict):
            continue
        out = layer_tr.get("output") or {}
        selected = out.get("selected_nodes") if isinstance(out, dict) else []
        names = []
        for node in selected or []:
            if isinstance(node, dict):
                names.append(str(node.get("name") or node.get("id") or ""))
        pipeline_rows.append(
            {
                "layer": layer_tr.get("layer") or f"layer_{idx}",
                "selected_count": len(selected or []),
                "selected_names": names[:12],
                "candidate_count": (out.get("candidate_count") if isinstance(out, dict) else 0) or 0,
                "fallback_applied": bool(out.get("fallback_applied")) if isinstance(out, dict) else False,
                "nl_guidance": (out.get("nl_guidance") if isinstance(out, dict) else "") or "",
            }
        )

    lines = []
    lines.append("=" * 80)
    lines.append("IoT-CapBuilder 意图 → 指令集 Trace 日志")
    lines.append("=" * 80)
    lines.append(f"trace_id      : {trace_id}")
    lines.append(f"started_at    : {ts.isoformat(sep=' ', timespec='seconds')}")
    lines.append(f"stopped_at    : {stopped_at or '-'}")
    lines.append(f"resolve_mode  : {resolve_mode}（{mode_label}）")
    lines.append(f"mode_label    : {mode_label}")
    lines.append(f"message       : {message or '-'}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("【0. 调用模式】")
    lines.append(f"本次意图到指令生成调用模式：{mode_label}（resolve_mode={resolve_mode}）")
    lines.append("")

    lines.append("-" * 80)
    lines.append("【1. 用户意图】")
    lines.append(intent_text)
    lines.append("")

    lines.append("-" * 80)
    lines.append("【2. 流水线摘要 L1→L5】")
    lines.append(json.dumps(pipeline_rows, ensure_ascii=False, indent=2))
    lines.append("")

    lines.append("-" * 80)
    lines.append("【3. 权重择优决策（设备权重 > 指令权重）】")
    lines.append(json.dumps(weight_decisions, ensure_ascii=False, indent=2) if weight_decisions else "(无)")
    lines.append("")

    lines.append("-" * 80)
    lines.append("【4. 最终执行方案（结构化摘要）】")
    lines.append(json.dumps(_summarize_final_plan_for_trace(final_plan), ensure_ascii=False, indent=2))
    lines.append("")

    lines.append("-" * 80)
    lines.append("【5. 打包的 API 指令集】")
    lines.append(json.dumps(packed_api_set or [], ensure_ascii=False, indent=2))
    lines.append("")

    lines.append("=" * 80)
    lines.append("【6. 各层详情附录】")
    lines.append("=" * 80)
    for idx, layer_tr in enumerate(layers_trace or [], start=1):
        if not isinstance(layer_tr, dict):
            continue
        layer_name = layer_tr.get("layer") or f"layer_{idx}"
        lines.append("")
        lines.append(f"### 第 {idx} 层 / {layer_name}")
        lines.append("--- 层输入（压缩） ---")
        lines.append(json.dumps(_compact_trace_value(layer_tr.get("input") or {}), ensure_ascii=False, indent=2))
        lines.append("")
        lines.append("--- 调用提示词（截断） ---")
        lines.append(str(_compact_trace_value(str(layer_tr.get("prompt") or ""), max_str=2500)))
        lines.append("")
        lines.append("--- 模型原始输出（截断） ---")
        lines.append(str(_compact_trace_value(str(layer_tr.get("raw_llm_response") or ""), max_str=2500)))
        lines.append("")
        lines.append("--- 解析 JSON（压缩） ---")
        lines.append(json.dumps(_compact_trace_value(layer_tr.get("raw_parsed") or {}), ensure_ascii=False, indent=2))
        lines.append("")
        lines.append("--- 层输出 ---")
        lines.append(json.dumps(_compact_trace_value(layer_tr.get("output") or {}), ensure_ascii=False, indent=2))

    if layers_summary is not None:
        lines.append("")
        lines.append("-" * 80)
        lines.append("【7. 各层响应摘要（API 返回结构）】")
        lines.append(json.dumps(_compact_trace_value(layers_summary), ensure_ascii=False, indent=2))

    lines.append("")
    lines.append("=" * 80)
    lines.append("日志结束")
    lines.append("=" * 80)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return save_path


def _format_user_param_value(value: Any, unit: Optional[str] = None) -> str:
    if value is None:
        return ""
    text = str(value)
    if unit and unit not in text:
        unit_label = {"celsius": "℃", "percentage": "%"}.get(str(unit).lower(), str(unit))
        if unit_label == "℃":
            return f"{text}℃"
        if unit_label == "%":
            return f"{text}%"
        return f"{text}{unit_label}"
    return text


def _build_step_description(nl_step: str, applied_params: list) -> str:
    base = (nl_step or "").strip()
    if not applied_params:
        return base or "执行该步指令"
    param_parts = []
    for p in applied_params:
        label = p.get("label") or p.get("path") or "参数"
        val_text = _format_user_param_value(p.get("value"), p.get("unit"))
        param_parts.append(f"{label}={val_text}")
    param_text = "；".join(param_parts)
    if base and "XX" in base:
        for p in applied_params:
            val_text = _format_user_param_value(p.get("value"), p.get("unit"))
            base = base.replace("XX", val_text, 1)
    if param_parts:
        return f"{base}（参数：{param_text}）" if base else f"设置参数：{param_text}"
    return base


def pack_intent_api_commands(
    *,
    intent_text: str,
    final_plan: dict,
    user_param_values: dict,
    trace_id: Optional[str] = None,
) -> dict:
    """
    将用户填写的参数注入有序指令草案，打包为可执行的 API 指令集。
    返回 packed_steps、packed_api_set、validation_errors。
    """
    steps = final_plan.get("ordered_steps") or []
    validation_errors: list = []

    normalized_steps = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_copy = dict(step)
        selected = step_copy.get("selected_uid") or step_copy.get("payload_uid") or ""
        if selected:
            step_copy["payload_uid"] = selected
            step_copy["selected_uid"] = selected
            if step_copy.get("options"):
                matched_opt = None
                for opt in step_copy["options"]:
                    if not isinstance(opt, dict):
                        continue
                    if _normalize_id(opt.get("payload_uid")) == _normalize_id(selected):
                        matched_opt = opt
                        break
                    for variant in opt.get("command_variants") or []:
                        if isinstance(variant, dict) and _normalize_id(variant.get("payload_uid")) == _normalize_id(selected):
                            matched_opt = opt
                            break
                    if matched_opt:
                        break
                if matched_opt:
                    _apply_step_option_to_step(step_copy, matched_opt)
        normalized_steps.append(step_copy)

    for step in normalized_steps:
        if not isinstance(step, dict):
            continue
        step_no = step.get("step")
        for ph in step.get("param_placeholders") or []:
            if not isinstance(ph, dict):
                continue
            if ph.get("required") is False:
                continue
            path = ph.get("path")
            key = f"{step_no}-{path}"
            val = user_param_values.get(key)
            if val is None or val == "":
                val = ph.get("user_value")
            if val is None or val == "":
                label = ph.get("label") or path
                validation_errors.append(f"步骤 {step_no} 的参数「{label}」尚未填写")

    if validation_errors:
        mode_meta = _resolve_mode_meta(final_plan.get("resolve_mode"))
        return {
            "success": False,
            "validation_errors": validation_errors,
            "packed_steps": [],
            "packed_api_set": [],
            "plan_summary": final_plan.get("plan_summary") or "",
            "nl_guidance": final_plan.get("nl_guidance") or "",
            "resolve_mode": mode_meta["resolve_mode"],
            "resolve_mode_label": mode_meta["label_zh"],
            "trace_id": trace_id,
            "intent_text": intent_text,
        }

    packed_steps: list = []
    packed_api_set: list = []

    for step in normalized_steps:
        if not isinstance(step, dict):
            continue
        step_no = step.get("step")
        fills = []
        for ph in step.get("param_placeholders") or []:
            if not isinstance(ph, dict):
                continue
            path = ph.get("path")
            key = f"{step_no}-{path}"
            val = user_param_values.get(key)
            if val is None or val == "":
                val = ph.get("user_value")
            fills.append(
                {
                    "path": path,
                    "value": val,
                    "label": ph.get("label") or path,
                    "value_type": ph.get("value_type"),
                    "format": ph.get("format"),
                    "unit": ph.get("unit"),
                }
            )

        api_set_raw = step.get("api_set")
        injected_api_set, applied = inject_params_into_api_set(api_set_raw, fills)
        injected_api_set = drop_unfilled_optional_api_ops(
            injected_api_set, step.get("param_placeholders") or [], applied
        )
        step_desc = _build_step_description(step.get("nl_step") or "", applied)
        packed_step = {
            "step": step_no,
            "payload_uid": step.get("payload_uid") or "",
            "c_instance_id": step.get("c_instance_id") or "",
            "c_brand": step.get("c_brand") or "",
            "e_id": step.get("e_id"),
            "e_name": step.get("e_name") or "",
            "nl_step": step.get("nl_step") or "",
            "step_description": step_desc,
            "user_params": applied,
            "api_set": injected_api_set,
        }
        packed_steps.append(packed_step)
        packed_api_set.append(
            {
                "step": step_no,
                "payload_uid": packed_step["payload_uid"],
                "c_instance_id": packed_step["c_instance_id"],
                "c_brand": packed_step["c_brand"],
                "e_id": packed_step["e_id"],
                "e_name": packed_step["e_name"],
                "step_description": step_desc,
                "user_params": applied,
                "api_set": injected_api_set,
            }
        )

    mode_meta = _resolve_mode_meta(final_plan.get("resolve_mode"))
    return {
        "success": True,
        "validation_errors": [],
        "packed_steps": packed_steps,
        "packed_api_set": packed_api_set,
        "plan_summary": final_plan.get("plan_summary") or "",
        "nl_guidance": final_plan.get("nl_guidance") or "",
        "resolve_mode": mode_meta["resolve_mode"],
        "resolve_mode_label": mode_meta["label_zh"],
        "trace_id": trace_id,
        "intent_text": intent_text,
    }


def write_api_command_log(
    *,
    trace_id: Optional[str],
    intent_text: str,
    final_plan: dict,
    user_param_values: dict,
    packed_api_set: list,
    packed_steps: Optional[list] = None,
) -> str:
    """
    写入 API 指令集生成日志：APIcommand-年-月-日-hh-mm-ss.log
    日志中标注本次意图到指令生成所调用的模式（自动/复杂）。
    返回相对路径。
    """
    from datetime import datetime

    if not os.path.exists(API_COMMAND_LOG_DIR):
        os.makedirs(API_COMMAND_LOG_DIR)

    ts = datetime.now()
    mode_meta = _resolve_mode_meta(_extract_resolve_mode(final_plan))
    filename = f"APIcommand-{ts.strftime('%Y-%m-%d-%H-%M-%S')}.log"
    save_path = os.path.join(API_COMMAND_LOG_DIR, filename)
    if os.path.exists(save_path):
        for i in range(1, 1000):
            alt = os.path.join(
                API_COMMAND_LOG_DIR, f"APIcommand-{ts.strftime('%Y-%m-%d-%H-%M-%S')}-{i}.log"
            )
            if not os.path.exists(alt):
                save_path = alt
                filename = os.path.basename(alt)
                break

    steps = final_plan.get("ordered_steps") or []
    plan_summary = final_plan.get("plan_summary") or ""
    nl_guidance = final_plan.get("nl_guidance") or ""

    lines: list = []
    lines.append("=" * 80)
    lines.append("IoT-CapBuilder 意图 API 指令集生成日志")
    lines.append("=" * 80)
    lines.append(f"trace_id      : {trace_id or '-'}")
    lines.append(f"generated_at  : {ts.isoformat(sep=' ', timespec='seconds')}")
    lines.append(f"resolve_mode  : {mode_meta['resolve_mode']}（{mode_meta['label_zh']}）")
    lines.append(f"mode_label    : {mode_meta['label_zh']}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("【0. 调用模式】")
    lines.append(
        f"本次意图到指令生成调用模式：{mode_meta['label_zh']}（resolve_mode={mode_meta['resolve_mode']}）"
    )
    lines.append("")
    lines.append("-" * 80)
    lines.append("【用户原意图】")
    lines.append(intent_text)
    lines.append("")
    lines.append("-" * 80)
    lines.append("【有序指令方案】")
    lines.append(f"方案摘要：{plan_summary or '（无）'}")
    lines.append(f"调用模式：{mode_meta['label_zh']}")
    if nl_guidance:
        lines.append(f"整体说明：{nl_guidance}")
    lines.append("")
    lines.append("--- 各步骤说明 ---")
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_no = step.get("step")
        lines.append(
            f"步骤 {step_no}：{step.get('nl_step') or step.get('payload_uid') or '-'}"
        )
        lines.append(f"  设备：{step.get('c_brand') or step.get('c_instance_id') or '-'}")
        lines.append(f"  指令 UID：{step.get('payload_uid') or '-'}")
    lines.append("")
    lines.append("-" * 80)
    lines.append("【用户填写参数】")
    if user_param_values:
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_no = step.get("step")
            placeholders = step.get("param_placeholders") or []
            if not placeholders:
                continue
            lines.append(f"--- 步骤 {step_no} ---")
            for ph in placeholders:
                if not isinstance(ph, dict):
                    continue
                path = ph.get("path")
                key = f"{step_no}-{path}"
                val = user_param_values.get(key)
                label = ph.get("label") or path
                lines.append(f"  {label} ({path}) = {json.dumps(val, ensure_ascii=False)}")
    else:
        lines.append("（无待填参数）")
    lines.append("")
    if packed_steps:
        lines.append("--- 注入后步骤描述 ---")
        for ps in packed_steps:
            lines.append(f"步骤 {ps.get('step')}：{ps.get('step_description') or '-'}")
        lines.append("")
    lines.append("-" * 80)
    lines.append("【最终 API 指令集】")
    lines.append(json.dumps(packed_api_set or [], ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("=" * 80)
    lines.append("日志结束")
    lines.append("=" * 80)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return save_path


async def intent_select_domains(intent_text: str, domains: list) -> dict:
    """L1：从全部领域中选出与意图相关的领域。"""
    valid = {_normalize_id(d["d_id"]) for d in domains}
    name_by_id = {_normalize_id(d["d_id"]): d.get("d_name", "") for d in domains}
    candidates = json.dumps(domains, ensure_ascii=False)
    prompt = """
你是智能家居意图解析助手。请根据用户自然语言意图，从候选「作用领域」中选出相关节点。
若多个领域都可能相关且难以区分优先级，请自由择优，至少选出 1 个，优先保证有效输出。

【用户意图】
{intent_text}

【候选作用领域】
{candidates}
""" + _LAYER_JSON_RULES
    raw, rendered_prompt, raw_response = await _ainvoke_intent_json(
        prompt, {"intent_text": intent_text, "candidates": candidates}
    )
    filtered = _filter_layer_selection(raw, valid, name_by_id, prefer_int=True)
    filtered = _ensure_nonempty_selection(
        filtered, domains, id_key="d_id", name_key="d_name", prefer_int=True
    )
    filtered["candidate_count"] = len(domains)
    return _attach_layer_trace(
        filtered,
        layer="l1",
        layer_input={"intent_text": intent_text, "candidates": domains},
        prompt=rendered_prompt,
        raw_response=raw_response,
        raw_parsed=raw,
    )


async def intent_select_objects(intent_text: str, objects: list, prev_layer: dict) -> dict:
    """L2：结合 L1 结果，从对象候选中选出相关对象。"""
    valid = {_normalize_id(o["o_id"]) for o in objects}
    name_by_id = {_normalize_id(o["o_id"]): o.get("o_name", "") for o in objects}
    prompt = """
你是智能家居意图解析助手。请结合上一层「作用领域」推理结果，从候选「作用对象」中选出相关节点。
若多个对象都可能相关且难以区分，请自由择优，至少选出 1 个，优先保证有效输出。

【用户意图】
{intent_text}

【上一层领域推理结果】
{prev_layer}

【候选作用对象】
{candidates}
""" + _LAYER_JSON_RULES
    raw, rendered_prompt, raw_response = await _ainvoke_intent_json(
        prompt,
        {
            "intent_text": intent_text,
            "prev_layer": json.dumps(prev_layer, ensure_ascii=False),
            "candidates": json.dumps(objects, ensure_ascii=False),
        },
    )
    filtered = _filter_layer_selection(raw, valid, name_by_id, prefer_int=True)
    filtered = _ensure_nonempty_selection(
        filtered, objects, id_key="o_id", name_key="o_name", prefer_int=True
    )
    filtered["candidate_count"] = len(objects)
    return _attach_layer_trace(
        filtered,
        layer="l2",
        layer_input={
            "intent_text": intent_text,
            "prev_layer": prev_layer,
            "candidates": objects,
        },
        prompt=rendered_prompt,
        raw_response=raw_response,
        raw_parsed=raw,
    )


async def intent_select_effects(intent_text: str, effects: list, prev_layer: dict) -> dict:
    """L3：结合 L2 结果，从效果候选中选出相关效果。"""
    valid = {_normalize_id(e["e_id"]) for e in effects}
    name_by_id = {_normalize_id(e["e_id"]): e.get("e_name", "") for e in effects}
    prompt = """
你是智能家居意图解析助手。请结合上一层「作用对象」推理结果，从候选「具体效果」中选出相关节点。
温度、转速、风向等设定值不是单独的效果，会在指令层用配方参数槽展开；本层只需选出制冷/制热/洗衣/冷藏等效果。
候选已按环境对应组预排序，并附 env_combo_hint（主签名/连带/观察/禁标）与 combo_score：
- 优先选择主签名环境与用户意图相符的效果（例如「凉快一点」对应制冷，而不是只读温度或通风换气）；
- 观察类效果仅当用户明确要查看/读取环境数据时才选；
- combo_score 只作排序参考，禁止编造或选择环境 ID。
若多个效果都可能相关且难以区分，请自由择优，至少选出 1 个，优先保证有效输出。

【用户意图】
{intent_text}

【上一层对象推理结果】
{prev_layer}

【候选具体效果】
{candidates}
""" + _LAYER_JSON_RULES
    raw, rendered_prompt, raw_response = await _ainvoke_intent_json(
        prompt,
        {
            "intent_text": intent_text,
            "prev_layer": json.dumps(prev_layer, ensure_ascii=False),
            "candidates": json.dumps(effects, ensure_ascii=False),
        },
    )
    filtered = _filter_layer_selection(raw, valid, name_by_id, prefer_int=True)
    filtered = _ensure_nonempty_selection(
        filtered, effects, id_key="e_id", name_key="e_name", prefer_int=True
    )
    filtered["candidate_count"] = len(effects)
    return _attach_layer_trace(
        filtered,
        layer="l3",
        layer_input={
            "intent_text": intent_text,
            "prev_layer": prev_layer,
            "candidates": effects,
        },
        prompt=rendered_prompt,
        raw_response=raw_response,
        raw_parsed=raw,
    )


async def intent_select_devices(
    intent_text: str,
    devices: list,
    prev_layer: dict,
    *,
    resolve_mode: str = "auto",
) -> dict:
    """L4：在用户参与池 ∩ L3 可达设备中选出具体设备，可参考偏好权重与描述。"""
    interactive = str(resolve_mode or "auto").lower() == "interactive"
    valid = {_normalize_id(d["c_instance_id"]) for d in devices}
    name_by_id = {_normalize_id(d["c_instance_id"]): d.get("c_brand", "") for d in devices}

    if interactive:
        prompt = """
你是智能家居意图解析助手（复杂选择模式）。请结合上一层「具体效果」推理结果，从当前环境表单已实例化的具体设备中选出相关设备。
候选设备已附带用户偏好 weight(1-5)、preference_desc、c_desc（设备能力摘要）、a_ref（抽象设备类型），以及可选的房间/别名：
- 必须选出所有能实现用户意图的相关具体设备，供后续步骤做横向设备选择；
- 若多个设备同类（相同 a_ref）或能力相近，只要与意图相关就必须全部选出，禁止只择其一；
- c_desc 是抽取生成的能力摘要，用于判断设备能否覆盖意图；preference_desc 是用户偏好说明，二者不要混用；
- env_match_score / env_match_hint 表示设备环境属性与 L3 主签名的匹配，只作排序参考，禁止据此编造或选择环境 ID；
- room_label / room_type_name / alias / room_match_score 用于对齐口语中的房间或设备称呼，只作排序与择优参考；
- 权重与 preference_desc 仅用于排序倾向，不能作为“只保留一个设备”的理由；
- 只要候选非空且与意图可能相关，禁止输出空列表。

【用户意图】
{intent_text}

【上一层效果推理结果】
{prev_layer}

【候选具体设备（含偏好）】
{candidates}
""" + _LAYER_JSON_RULES_INTERACTIVE_DEVICES
    else:
        prompt = """
你是智能家居意图解析助手。请结合上一层「具体效果」推理结果，从当前环境表单已实例化的具体设备中选出相关设备。
候选设备已附带用户偏好 weight(1-5)、preference_desc、c_desc（设备能力摘要），以及可选的房间/别名：
- 权重越高越应优先；
- c_desc 描述设备已抽取的能力，用于判断能否覆盖意图；preference_desc 是用户偏好，不要把二者当成同一字段；
- env_match_score / env_match_hint 表示与 L3 主签名环境的匹配，仅作排序参考，禁止编造或选择环境 ID；
- 若意图提到房间名或设备别名，优先选择 room_label / alias 命中、room_match_score 更高的实例；
- 若多个设备权重相同，或都没有特殊 preference_desc，请按意图语义自由择一/择优，不要放弃选择；
- 只要候选非空且与意图可能相关，必须至少选出 1 个设备，优先保证有效输出。

【用户意图】
{intent_text}

【上一层效果推理结果】
{prev_layer}

【候选具体设备（含偏好）】
{candidates}
""" + _LAYER_JSON_RULES

    raw, rendered_prompt, raw_response = await _ainvoke_intent_json(
        prompt,
        {
            "intent_text": intent_text,
            "prev_layer": json.dumps(prev_layer, ensure_ascii=False),
            "candidates": json.dumps(devices, ensure_ascii=False),
        },
    )
    filtered = _filter_layer_selection(raw, valid, name_by_id, prefer_int=False)
    if interactive:
        filtered = _expand_parallel_device_selection(filtered, devices)
        if not filtered.get("selected_nodes"):
            filtered = _select_all_devices_as_fallback(filtered, devices)
    else:
        filtered = _ensure_nonempty_selection(
            filtered, devices, id_key="c_instance_id", name_key="c_brand", prefer_int=False
        )
    filtered = _sort_selected_nodes_by_candidate_weight(filtered, devices, "c_instance_id")
    filtered["candidate_count"] = len(devices)
    return _attach_layer_trace(
        filtered,
        layer="l4",
        layer_input={
            "intent_text": intent_text,
            "prev_layer": prev_layer,
            "candidates": devices,
            "resolve_mode": resolve_mode,
        },
        prompt=rendered_prompt,
        raw_response=raw_response,
        raw_parsed=raw,
    )


def _expand_parallel_device_selection(filtered: dict, devices: list) -> dict:
    """
    复杂模式：在已选设备基础上，把同类（相同 a_ref）且参与检索的并列设备一并纳入，
    避免 L4 只留下 1 台导致 L5 无法做跨设备备选。
    """
    selected = list(filtered.get("selected_nodes") or [])
    if not selected or not devices:
        return filtered

    by_id = {_normalize_id(d.get("c_instance_id")): d for d in devices}
    selected_ids = {_normalize_id(n.get("id")) for n in selected if n.get("id") is not None}
    selected_a_refs = set()
    for nid in selected_ids:
        device = by_id.get(nid) or {}
        a_ref = str(device.get("a_ref") or "").strip()
        if a_ref:
            selected_a_refs.add(a_ref)

    if not selected_a_refs:
        return filtered

    added = 0
    for device in devices:
        nid = _normalize_id(device.get("c_instance_id"))
        if not nid or nid in selected_ids:
            continue
        a_ref = str(device.get("a_ref") or "").strip()
        if a_ref not in selected_a_refs:
            continue
        selected.append(
            {
                "id": nid,
                "name": str(device.get("c_brand") or nid),
                "reason": f"复杂模式：与已选设备同类（{a_ref}），并列可选",
            }
        )
        selected_ids.add(nid)
        added += 1

    if added:
        filtered["selected_nodes"] = selected
        guidance = filtered.get("nl_guidance") or ""
        suffix = f"【复杂模式】已按同类设备自动补全 {added} 台并列可选具体设备。"
        filtered["nl_guidance"] = f"{guidance}\n{suffix}".strip() if guidance else suffix
        filtered["parallel_devices_expanded"] = added
    return filtered


def _select_all_devices_as_fallback(filtered: dict, devices: list) -> dict:
    """复杂模式保底：模型未选出时纳入全部候选设备，保证后续可横向选择。"""
    if filtered.get("selected_nodes") or not devices:
        return filtered
    selected = []
    for device in sorted(devices, key=_candidate_sort_key):
        nid = _normalize_id(device.get("c_instance_id"))
        if not nid:
            continue
        selected.append(
            {
                "id": nid,
                "name": str(device.get("c_brand") or nid),
                "reason": "复杂模式保底：纳入全部候选具体设备供并列选择",
            }
        )
    filtered["selected_nodes"] = selected
    filtered["nl_guidance"] = (
        (filtered.get("nl_guidance") or "")
        + "\n【复杂模式保底】模型未给出有效设备选择，已纳入全部候选具体设备。"
    ).strip()
    filtered["fallback_applied"] = True
    return filtered


def _extract_param_placeholders(
    api_set,
    param_schema=None,
    param_details=None,
    preference_hint: str = "",
) -> list:
    """扫描 api_set 占位并结合 param_schema 生成填参视图。"""
    return build_param_placeholders_from_schema(
        api_set,
        param_schema=param_schema,
        param_details=param_details,
        preference_desc=preference_hint or None,
    )


def _read_cmd_weight(cmd: dict) -> int:
    try:
        return int(cmd.get("weight") if cmd.get("weight") is not None else 0)
    except (TypeError, ValueError):
        return 0


def _cmd_has_preference(cmd: dict) -> bool:
    return bool(str(cmd.get("preference_desc") or "").strip())


def _read_device_weight(cmd: dict) -> int:
    try:
        return int(cmd.get("device_weight") if cmd.get("device_weight") is not None else 0)
    except (TypeError, ValueError):
        return 0


def _extract_command_action(uid: str) -> str:
    """从 uid 提取动作语义（「设备：动作」中的动作部分）。"""
    text = str(uid or "").strip()
    for sep in ("：", ":"):
        if sep in text:
            text = text.split(sep, 1)[-1].strip()
            break
    return text


_ACTION_ANTONYM_PAIRS = (
    ("打开", "关闭"),
    ("开启", "关闭"),
    ("开", "关"),
    ("打开", "关掉"),
    ("开始", "结束"),
    ("启动", "停止"),
    ("启动", "关闭"),
    ("接通", "断开"),
    ("开启", "关掉"),
    ("升温", "降温"),
    ("加热", "制冷"),
    ("正向", "反向"),
    ("打开", "关"),
    ("开灯", "关灯"),
    ("开机", "关机"),
    ("on", "off"),
    ("start", "stop"),
    ("enable", "disable"),
    ("open", "close"),
)


def _normalize_action_text(action: str) -> str:
    return str(action or "").strip().lower().replace(" ", "").replace("　", "")


def _actions_are_antonyms(action_a: str, action_b: str) -> bool:
    a = _normalize_action_text(action_a)
    b = _normalize_action_text(action_b)
    if not a or not b or a == b:
        return False
    for left, right in _ACTION_ANTONYM_PAIRS:
        l, r = left.lower(), right.lower()
        if (l in a and r in b) or (r in a and l in b):
            return True
    return False


def _api_set_polarity_compatible(api_a, api_b) -> bool:
    """布尔控制类 api_set：极性必须一致，避免开/关混入备选。"""
    if not isinstance(api_a, list) or not isinstance(api_b, list):
        return True
    bool_a = [x.get("value") for x in api_a if isinstance(x, dict) and isinstance(x.get("value"), bool)]
    bool_b = [x.get("value") for x in api_b if isinstance(x, dict) and isinstance(x.get("value"), bool)]
    if not bool_a or not bool_b:
        return True
    return bool_a[0] == bool_b[0]


def _action_similarity(action_a: str, action_b: str) -> float:
    a = _normalize_action_text(action_a)
    b = _normalize_action_text(action_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return 0.0
    overlap = len(set_a & set_b) / max(len(set_a | set_b), 1)
    return overlap


def _commands_same_function(primary: dict, candidate: dict) -> bool:
    """
    判断候选是否与主指令实现同一功能：
    - 不同具体设备
    - 同一 e_id
    - 动作语义非相反（开/关等）
    - 动作文本足够相似，或 api_set 布尔极性兼容且有一定相似度
    """
    if not primary or not candidate:
        return False
    if primary.get("c_instance_id") == candidate.get("c_instance_id"):
        return False
    if primary.get("e_id") != candidate.get("e_id"):
        return False
    pk = primary.get("candidate_kind")
    ck = candidate.get("candidate_kind")
    if pk in {"recipe", "composed"} and ck in {"recipe", "composed"}:
        pp = str(primary.get("recipe_pattern") or "")
        cp = str(candidate.get("recipe_pattern") or "")
        if pp and cp and ("action" in pp) != ("action" in cp):
            return False
        if pp and cp and ("program" in pp) != ("program" in cp):
            return False
    pa = _extract_command_action(primary.get("display_name") or primary.get("uid") or "")
    ca = _extract_command_action(candidate.get("display_name") or candidate.get("uid") or "")
    if _actions_are_antonyms(pa, ca):
        return False
    if not _api_set_polarity_compatible(primary.get("api_set"), candidate.get("api_set")):
        return False
    sim = _action_similarity(pa, ca)
    return sim >= 0.45


_GOAL_CORE_KEYWORDS = (
    "洗衣",
    "洗涤",
    "清洗",
    "烘干",
    "干衣",
    "制冷",
    "制热",
    "清扫",
    "扫地",
    "速冷",
    "冷藏",
    "冷冻",
    "开灯",
    "关灯",
    "照明",
    "打开",
    "关闭",
    "开机",
    "关机",
    "加热",
    "降温",
    "升温",
    "按摩",
    "播放",
    "暂停",
    "继续",
    "开始",
    "模式",
)

# 过于宽泛、不足以单独证明「同目标」的词
_GENERIC_GOAL_TOKENS = {
    "打开",
    "关闭",
    "开始",
    "模式",
    "继续",
    "暂停",
    "照明",
}

# 同义目标词归一，避免「扫地」与「清扫」无法判定为同目标
_GOAL_TOKEN_ALIASES = {
    "清扫": "扫地",
    "扫地": "扫地",
    "洗涤": "洗衣",
    "清洗": "洗衣",
    "洗衣": "洗衣",
    "干衣": "烘干",
    "烘干": "烘干",
}


def _goal_tokens(text: str) -> Set[str]:
    t = _normalize_action_text(text)
    if not t:
        return set()
    raw = {k for k in _GOAL_CORE_KEYWORDS if k in t}
    return {_GOAL_TOKEN_ALIASES.get(k, k) for k in raw}


def _specific_goal_tokens(text: str) -> Set[str]:
    return _goal_tokens(text) - _GENERIC_GOAL_TOKENS


def _is_query_like_action(action: str) -> bool:
    a = _normalize_action_text(action)
    return any(x in a for x in ("查询", "查看", "获取", "读取", "状态", "报告"))


def _action_kind(action: str) -> str:
    """
    将指令粗分为：query / stop / set / start / other。
    用于禁止「开灯 vs 调亮度」「开始扫地 vs 关闭扫地」这类伪同目标。
    """
    a = _normalize_action_text(action)
    if not a:
        return "other"
    if any(x in a for x in ("查询", "查看", "获取", "读取", "状态", "报告")):
        return "query"
    if any(x in a for x in ("停止", "结束", "取消", "关闭", "关灯", "关机", "关掉", "暂停清扫", "暂停扫地")):
        return "stop"
    if any(x in a for x in ("设置", "调节", "调整", "设定", "模式为", "温度为", "亮度", "色温", "风速", "档位为")):
        return "set"
    if any(x in a for x in ("开始", "启动", "打开", "开启", "开机", "开灯", "自动", "清扫", "洗衣并开始")):
        return "start"
    return "other"


def _action_kinds_compatible(action_a: str, action_b: str) -> bool:
    ka, kb = _action_kind(action_a), _action_kind(action_b)
    if ka == "other" or kb == "other":
        # other 仅当双方都 other 才宽松放行
        return ka == kb
    return ka == kb


def _build_goal_analysis(cmd: dict, step_intent: str = "", *, is_recommended: bool = False) -> str:
    action = _extract_command_action(cmd.get("display_name") or cmd.get("uid") or "")
    e_name = str(cmd.get("e_name") or "").strip()
    kind = _action_kind(action)
    kind_zh = {
        "start": "启动/开启类操作",
        "stop": "停止/关闭类操作",
        "set": "参数调节类操作",
        "query": "状态查询类操作",
        "other": "一般控制操作",
    }.get(kind, "一般控制操作")
    intent = str(step_intent or "").strip()
    prefix = "推荐路径：" if is_recommended else "备选路径："
    if intent:
        base = f"{prefix}通过「{action}」达成步骤目标「{intent}」（{kind_zh}"
    else:
        base = f"{prefix}执行「{action}」（{kind_zh}"
    if e_name:
        base += f"，效果：{e_name}"
    base += "）。"
    return base


def _commands_same_device_same_goal(
    primary: dict,
    candidate: dict,
    step_intent: str = "",
) -> bool:
    """
    同设备指令变体：必须严格服务同一意图目标。
    典型：自动洗衣 vs 自定义模式洗衣 —— 路径不同但目标同为洗衣。
    禁止：开灯 vs 调亮度；开始扫地 vs 关闭扫地。
    默认从严：多数情况应返回 False。
    """
    if not primary or not candidate:
        return False
    if primary.get("c_instance_id") != candidate.get("c_instance_id"):
        return False
    if primary.get("e_id") != candidate.get("e_id"):
        return False
    puid = _normalize_id(primary.get("uid"))
    cuid = _normalize_id(candidate.get("uid"))
    if not puid or not cuid or puid == cuid:
        return False
    if (
        primary.get("candidate_kind") in {"recipe", "composed"}
        and candidate.get("candidate_kind") in {"recipe", "composed"}
        and str(primary.get("recipe_pattern") or "")
        and primary.get("recipe_pattern") == candidate.get("recipe_pattern")
    ):
        return False

    pa = _extract_command_action(primary.get("display_name") or primary.get("uid") or "")
    ca = _extract_command_action(candidate.get("display_name") or candidate.get("uid") or "")
    if not pa or not ca:
        return False
    if _actions_are_antonyms(pa, ca):
        return False
    if not _action_kinds_compatible(pa, ca):
        return False
    if _action_kind(pa) == "stop" or _action_kind(ca) == "stop":
        # 停止/关闭类不做同目标变体展开
        return False
    if _action_kind(pa) == "set" and _action_kind(ca) == "set":
        # 纯参数调节之间除非高度相似且同意图，否则不并列（避免亮度/色温乱入开灯）
        pass
    if not _api_set_polarity_compatible(primary.get("api_set"), candidate.get("api_set")):
        return False
    if _is_query_like_action(pa) != _is_query_like_action(ca):
        return False

    intent = str(step_intent or "").strip()
    intent_n = _normalize_action_text(intent)
    intent_sim_p = max(
        _action_similarity(intent, pa),
        _action_similarity(intent, str(primary.get("uid") or "")),
    )
    intent_sim_c = max(
        _action_similarity(intent, ca),
        _action_similarity(intent, str(candidate.get("uid") or "")),
    )
    pair_sim = _action_similarity(pa, ca)

    specific_p = _specific_goal_tokens(pa) | _specific_goal_tokens(intent)
    specific_c = _specific_goal_tokens(ca)
    # 「洗衬衣」↔「洗衣」
    if "洗衣" in _normalize_action_text(pa) and ("洗" in intent_n and "衣" in intent_n):
        specific_p.add("洗衣")
    if "洗衣" in _normalize_action_text(ca) and ("洗" in intent_n and "衣" in intent_n):
        specific_c.add("洗衣")
    specific_shared = specific_p & specific_c

    # 开启类意图（开灯/打开）不允许参数调节类指令混入
    if intent and _action_kind(pa) == "start":
        if _action_kind(ca) == "set":
            return False
        if any(x in intent_n for x in ("打开", "开启", "开灯", "开机", "开始", "启动")) and _action_kind(ca) != "start":
            return False

    # 候选必须足够贴合步骤意图
    if intent:
        intent_specific = _specific_goal_tokens(intent)
        if intent_sim_c < 0.4 and not (intent_specific & specific_c) and "洗衣" not in specific_shared:
            return False
        if intent_sim_p < 0.3 and not (intent_specific & specific_p) and "洗衣" not in specific_shared:
            return False

    # 必须有具体目标词交集；仅共享「打开/开始/模式」不够
    if specific_shared:
        return True

    # 无具体目标词时：仅允许动作高度相似，且双方都明显贴合意图，且同类为 start
    if (
        pair_sim >= 0.72
        and _action_kind(pa) == "start"
        and _action_kind(ca) == "start"
        and (not intent or min(intent_sim_p, intent_sim_c) >= 0.45)
    ):
        return True
    return False


def _build_command_variant_from_cmd(
    cmd: dict,
    uid: str,
    *,
    is_recommended: bool = False,
    variant_reason: str = "",
    nl_step: str = "",
    step_intent: str = "",
) -> dict:
    hint = str(cmd.get("preference_desc") or "")
    return {
        "payload_uid": uid,
        "nl_step": nl_step or str(cmd.get("display_name") or cmd.get("uid") or uid),
        "is_recommended": is_recommended,
        "variant_reason": variant_reason,
        "goal_analysis": _build_goal_analysis(cmd, step_intent, is_recommended=is_recommended),
        "command_weight": _read_cmd_weight(cmd),
        "api_set": cmd.get("api_set"),
        "param_placeholders": _extract_param_placeholders(
            cmd.get("api_set"),
            param_schema=cmd.get("param_schema"),
            param_details=cmd.get("param_details"),
            preference_hint=hint,
        ),
    }


def _find_same_device_command_variants(
    primary_uid: str,
    commands: list,
    cmd_by_uid: dict,
    *,
    step_intent: str = "",
    llm_variant_uids: Optional[List[str]] = None,
    max_variants: int = 4,
) -> List[dict]:
    """同设备同目标指令路径；按指令权重降序，最高者作为推荐；无合格变体时返回空列表。"""
    primary_nid = _normalize_id(primary_uid)
    primary = cmd_by_uid.get(primary_nid) or {}
    if not primary:
        return []
    device_id = str(primary.get("c_instance_id") or "")
    if not device_id:
        return []

    primary_action = _extract_command_action(primary.get("uid") or "")
    scored: List[tuple] = []
    seen: Set[str] = set()

    def consider(cmd: dict, reason: str, from_llm: bool) -> None:
        nid = _normalize_id(cmd.get("uid"))
        if not nid or nid in seen:
            return
        if nid != primary_nid and not _commands_same_device_same_goal(primary, cmd, step_intent):
            return
        if nid != primary_nid and str(cmd.get("c_instance_id") or "") != device_id:
            return
        seen.add(nid)
        action = _extract_command_action(cmd.get("uid") or "")
        # 权重优先：指令权重 > 意图贴合 > 与主指令相似 > 模型提示
        score = (
            _read_cmd_weight(cmd),
            _action_similarity(step_intent, action) if step_intent else 0.0,
            _action_similarity(primary_action, action),
            1 if from_llm else 0,
        )
        scored.append((score, cmd, reason if nid != primary_nid else "推荐指令路径（指令权重最高）"))

    consider(primary, "推荐指令路径（指令权重最高）", True)
    for raw_uid in llm_variant_uids or []:
        nid = _normalize_id(raw_uid)
        if nid and nid in cmd_by_uid:
            consider(cmd_by_uid[nid], "同设备同目标：模型推荐的不同指令路径", True)
    for cmd in commands:
        if str(cmd.get("c_instance_id") or "") != device_id:
            continue
        consider(cmd, "同设备同目标：不同指令路径（如自动/自定义）", False)

    if len(scored) <= 1:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    variants: List[dict] = []
    for idx, (_score, cmd, reason) in enumerate(scored):
        if len(variants) >= max_variants:
            break
        uid = _normalize_id(cmd.get("uid"))
        is_rec = idx == 0
        variants.append(
            _build_command_variant_from_cmd(
                cmd,
                uid,
                is_recommended=is_rec,
                variant_reason=reason if not is_rec else "推荐指令路径（指令权重最高）",
                nl_step=str(cmd.get("display_name") or cmd.get("uid") or uid),
                step_intent=step_intent,
            )
        )
    return variants if len(variants) > 1 else []


def _build_step_option_from_cmd(
    cmd: dict,
    uid: str,
    *,
    is_recommended: bool = False,
    tie_group: str = "",
    tie_reason: str = "",
    nl_step: str = "",
    step_intent: str = "",
    command_variants: Optional[List[dict]] = None,
) -> dict:
    hint = str(cmd.get("preference_desc") or "")
    return {
        "payload_uid": uid,
        "c_instance_id": cmd.get("c_instance_id") or "",
        "c_brand": cmd.get("c_brand") or "",
        "e_id": cmd.get("e_id"),
        "e_name": cmd.get("e_name") or "",
        "nl_step": nl_step or str(cmd.get("display_name") or cmd.get("uid") or uid),
        "is_recommended": is_recommended,
        "tie_group": tie_group,
        "tie_reason": tie_reason,
        "device_weight": _read_device_weight(cmd),
        "command_weight": _read_cmd_weight(cmd),
        "goal_analysis": _build_goal_analysis(cmd, step_intent, is_recommended=is_recommended),
        "api_set": cmd.get("api_set"),
        "param_placeholders": _extract_param_placeholders(
            cmd.get("api_set"),
            param_schema=cmd.get("param_schema"),
            param_details=cmd.get("param_details"),
            preference_hint=hint,
        ),
        "command_variants": list(command_variants or []),
    }


def _apply_variant_to_option(option: dict, variant: dict) -> None:
    option["payload_uid"] = variant["payload_uid"]
    option["nl_step"] = variant.get("nl_step") or variant["payload_uid"]
    option["api_set"] = variant.get("api_set")
    option["param_placeholders"] = variant.get("param_placeholders") or []
    if "command_weight" in variant:
        option["command_weight"] = variant.get("command_weight") or 0
    if "goal_analysis" in variant:
        option["goal_analysis"] = variant.get("goal_analysis") or ""


def _apply_step_option_to_step(step: dict, option: dict) -> None:
    selected = step.get("selected_uid") or option.get("payload_uid") or ""
    chosen = dict(option)
    for variant in option.get("command_variants") or []:
        if isinstance(variant, dict) and _normalize_id(variant.get("payload_uid")) == _normalize_id(selected):
            _apply_variant_to_option(chosen, variant)
            break
    step["payload_uid"] = chosen["payload_uid"]
    step["selected_uid"] = chosen["payload_uid"]
    step["c_instance_id"] = chosen.get("c_instance_id") or ""
    step["c_brand"] = chosen.get("c_brand") or ""
    step["e_id"] = chosen.get("e_id")
    step["e_name"] = chosen.get("e_name") or ""
    step["nl_step"] = chosen.get("nl_step") or chosen["payload_uid"]
    step["api_set"] = chosen.get("api_set")
    step["param_placeholders"] = chosen.get("param_placeholders") or []


def _find_alternatives_for_step(
    primary_uid: str,
    commands: list,
    cmd_by_uid: dict,
    *,
    step_intent: str = "",
    llm_alternative_uids: Optional[List[str]] = None,
    llm_same_device_uids: Optional[List[str]] = None,
    max_options: int = 5,
) -> List[dict]:
    """
    一级：跨具体设备同功能备选，按「设备权重 > 指令权重」降序，最高者为推荐。
    二级：每个设备卡片挂载同设备同目标指令路径（严格过滤，多数为空）。
    """
    primary_nid = _normalize_id(primary_uid)
    primary = cmd_by_uid.get(primary_nid) or {}
    if not primary:
        return []

    primary_action = _extract_command_action(primary.get("uid") or primary_nid)
    best_by_device: Dict[str, tuple] = {}

    def consider(cmd: dict, reason: str, group: str, from_llm: bool) -> None:
        nid = _normalize_id(cmd.get("uid"))
        device_id = str(cmd.get("c_instance_id") or "")
        if not nid or not device_id:
            return
        if nid != primary_nid and not _commands_same_function(primary, cmd):
            return
        # 同设备下其它指令留给 command_variants，不占跨设备槽位
        if nid != primary_nid and str(cmd.get("c_instance_id") or "") == str(primary.get("c_instance_id") or ""):
            return
        sim = _action_similarity(primary_action, _extract_command_action(cmd.get("uid") or ""))
        # 权重优先：设备权重 > 指令权重 > 动作相似度 > 模型提示
        score = (
            _read_device_weight(cmd),
            _read_cmd_weight(cmd),
            sim,
            1 if from_llm else 0,
        )
        prev = best_by_device.get(device_id)
        if prev is None or score > prev[0]:
            best_by_device[device_id] = (score, cmd, reason, group, from_llm)

    # 主设备种子
    consider(primary, "模型推荐设备", "primary", True)

    for raw_uid in llm_alternative_uids or []:
        nid = _normalize_id(raw_uid)
        if not nid or nid == primary_nid or nid not in cmd_by_uid:
            continue
        consider(cmd_by_uid[nid], "同功能可替代设备", "cross-device-llm", True)

    for cmd in commands:
        nid = _normalize_id(cmd.get("uid"))
        if not nid or nid == primary_nid:
            continue
        consider(cmd, "同功能可替代设备", "cross-device", False)

    ranked = sorted(best_by_device.values(), key=lambda x: x[0], reverse=True)
    primary_device_id = str(primary.get("c_instance_id") or "")

    def with_variants(cmd: dict, uid: str, **kwargs) -> dict:
        option = _build_step_option_from_cmd(cmd, uid, **kwargs)
        same_device_hints = (
            list(llm_same_device_uids or [])
            if str(cmd.get("c_instance_id") or "") == primary_device_id
            else []
        )
        option["command_variants"] = _find_same_device_command_variants(
            uid,
            commands,
            cmd_by_uid,
            step_intent=step_intent,
            llm_variant_uids=same_device_hints,
        )
        # 若同设备变体按指令权重重排，同步把推荐变体提升为该设备代表指令
        variants = option.get("command_variants") or []
        if variants:
            rec_variant = next((v for v in variants if v.get("is_recommended")), variants[0])
            _apply_variant_to_option(option, rec_variant)
            option["goal_analysis"] = rec_variant.get("goal_analysis") or option.get("goal_analysis") or ""
        return option

    options: List[dict] = []
    for idx, (_score, cmd, reason, group, _from_llm) in enumerate(ranked):
        if len(options) >= max_options:
            break
        uid = _normalize_id(cmd.get("uid"))
        is_rec = idx == 0
        option = with_variants(
            cmd,
            uid,
            is_recommended=is_rec,
            tie_group=group if not is_rec else "weight-top",
            tie_reason="" if is_rec else reason,
            nl_step=str(cmd.get("uid") or uid),
            step_intent=step_intent,
        )
        if is_rec:
            option["tie_reason"] = (
                f"按权重优先推荐（设备权重 {option.get('device_weight', 0)}，"
                f"指令权重 {option.get('command_weight', 0)}）"
            )
            option["goal_analysis"] = _build_goal_analysis(
                cmd_by_uid.get(_normalize_id(option.get("payload_uid"))) or cmd,
                step_intent,
                is_recommended=True,
            )
        options.append(option)

    # 变体替换后可能改变指令权重，再按权重稳定重排一次
    options.sort(
        key=lambda o: (
            int(o.get("device_weight") or 0),
            int(o.get("command_weight") or 0),
            str(o.get("payload_uid") or ""),
        ),
        reverse=True,
    )
    for idx, option in enumerate(options):
        is_rec = idx == 0
        option["is_recommended"] = is_rec
        if is_rec:
            option["tie_group"] = "weight-top"
            option["tie_reason"] = (
                f"按权重优先推荐（设备权重 {option.get('device_weight', 0)}，"
                f"指令权重 {option.get('command_weight', 0)}）"
            )
        elif not option.get("tie_reason"):
            option["tie_reason"] = "同功能可替代设备"
        cmd_for_goal = cmd_by_uid.get(_normalize_id(option.get("payload_uid"))) or {}
        if cmd_for_goal:
            option["goal_analysis"] = _build_goal_analysis(
                cmd_for_goal, step_intent, is_recommended=is_rec
            )
    return options


def _parse_step_intents_from_raw(raw: dict, ordered_uids: List[str]) -> Dict[str, str]:
    """从 LLM 输出解析每步语义 intent。"""
    intents: Dict[str, str] = {}
    steps_raw = raw.get("steps")
    if isinstance(steps_raw, list):
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            uid = _normalize_id(item.get("recommended_uid") or item.get("uid") or item.get("payload_uid"))
            intent = str(item.get("intent") or item.get("step_intent") or "").strip()
            if uid and intent:
                intents[uid] = intent
    step_notes = raw.get("step_notes") if isinstance(raw.get("step_notes"), dict) else {}
    for uid in ordered_uids:
        if uid in intents:
            continue
        note = step_notes.get(uid)
        if note:
            intents[uid] = str(note)
    return intents


def _resolve_command_uid(
    raw_uid,
    commands: list,
    cmd_by_uid: dict,
) -> Optional[str]:
    """
    将模型输出的 uid 映射回真实候选 uid。
    常见幻觉：用 c_instance_id + 动作 拼接，而非候选里的「品牌：动作」uid。
    """
    nid = _normalize_id(raw_uid)
    if not nid:
        return None
    if nid in cmd_by_uid:
        return nid

    best_uid: Optional[str] = None
    best_score = -1.0

    for cmd in commands:
        uid = _normalize_id(cmd.get("uid"))
        cid = str(cmd.get("c_instance_id") or "")
        brand = str(cmd.get("c_brand") or "")
        cmd_action = _extract_command_action(cmd.get("uid") or "")
        if not uid or not cmd_action:
            continue

        action_from_raw = ""
        id_bonus = 0.0
        if cid and nid.startswith(cid):
            action_from_raw = nid[len(cid) :].lstrip(":：/-_ ")
            id_bonus = 0.35
        elif cid and cid in nid:
            action_from_raw = nid.split(cid, 1)[-1].lstrip(":：/-_ ")
            id_bonus = 0.25
        else:
            action_from_raw = _extract_command_action(nid)

        if not action_from_raw:
            continue
        if _actions_are_antonyms(action_from_raw, cmd_action):
            continue

        sim = _action_similarity(action_from_raw, cmd_action)
        brand_bonus = 0.0
        if brand and (brand in nid or nid.startswith(brand)):
            brand_bonus = 0.2
        score = sim + id_bonus + brand_bonus
        if score > best_score:
            best_score = score
            best_uid = uid

    if best_uid is not None and best_score >= 0.55:
        return best_uid
    return None


def _resolve_command_uid_by_intent(intent_text: str, commands: list) -> Optional[str]:
    """用步骤语义文本在候选中找最接近的指令。"""
    intent = str(intent_text or "").strip()
    if not intent or not commands:
        return None
    best_uid = None
    best_score: Optional[tuple] = None
    for cmd in commands:
        uid = _normalize_id(cmd.get("uid"))
        action = _extract_command_action(cmd.get("uid") or "")
        e_name = str(cmd.get("e_name") or "")
        if not uid:
            continue
        if _actions_are_antonyms(intent, action):
            continue
        sim = max(
            _action_similarity(intent, action),
            _action_similarity(intent, e_name) * 0.7,
            _action_similarity(intent, str(cmd.get("uid") or "")) * 0.8,
        )
        # 语义相近时，设备/指令权重更高者优先
        score = (
            sim,
            _read_device_weight(cmd),
            _read_cmd_weight(cmd),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_uid = uid
    if best_uid is not None and best_score is not None and best_score[0] >= 0.5:
        return best_uid
    return None


def _collect_l5_step_plan(
    raw: dict,
    commands: list,
    cmd_by_uid: dict,
) -> List[dict]:
    """
    从 LLM 原始输出收集有序步骤，并对 uid 做纠偏映射。
    优先使用 steps[]，保证多步方案不被校验失败后的保底单步覆盖。
    """
    plan: List[dict] = []
    seen: Set[str] = set()

    def append_step(
        resolved: Optional[str],
        intent: str = "",
        alts_raw=None,
        same_device_raw=None,
        nl_hint: str = "",
    ) -> None:
        if not resolved or resolved not in cmd_by_uid or resolved in seen:
            return
        seen.add(resolved)
        alts: List[str] = []
        for a in alts_raw or []:
            ra = _resolve_command_uid(a, commands, cmd_by_uid)
            if ra and ra != resolved and ra not in alts and ra in cmd_by_uid:
                alts.append(ra)
        same_device_alts: List[str] = []
        for a in same_device_raw or []:
            ra = _resolve_command_uid(a, commands, cmd_by_uid)
            if ra and ra != resolved and ra not in same_device_alts and ra in cmd_by_uid:
                same_device_alts.append(ra)
        plan.append(
            {
                "uid": resolved,
                "intent": intent or "",
                "alts": alts,
                "same_device_alts": same_device_alts,
                "nl_hint": nl_hint or "",
            }
        )

    steps_raw = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for item in steps_raw:
        if not isinstance(item, dict):
            continue
        intent = str(item.get("intent") or item.get("step_intent") or "").strip()
        raw_uid = item.get("recommended_uid") or item.get("uid") or item.get("payload_uid")
        resolved = _resolve_command_uid(raw_uid, commands, cmd_by_uid)
        if not resolved and intent:
            resolved = _resolve_command_uid_by_intent(intent, commands)
        append_step(
            resolved,
            intent=intent,
            alts_raw=item.get("alternative_uids") or [],
            same_device_raw=item.get("same_device_alternative_uids") or item.get("same_device_uids") or [],
        )

    if not plan:
        for uid in raw.get("ordered_uids") or []:
            resolved = _resolve_command_uid(uid, commands, cmd_by_uid)
            append_step(resolved)

    step_notes = raw.get("step_notes") if isinstance(raw.get("step_notes"), dict) else {}
    if step_notes and not plan:
        for raw_key, note in step_notes.items():
            resolved = _resolve_command_uid(raw_key, commands, cmd_by_uid)
            if not resolved:
                resolved = _resolve_command_uid_by_intent(str(note or ""), commands)
            append_step(resolved, intent=str(note or ""), nl_hint=str(note or ""))

    # 回填 note 到已有步骤
    if step_notes and plan:
        for step in plan:
            if step.get("nl_hint"):
                continue
            uid = step["uid"]
            for raw_key, note in step_notes.items():
                resolved = _resolve_command_uid(raw_key, commands, cmd_by_uid)
                if resolved == uid and note:
                    step["nl_hint"] = str(note)
                    break

    return plan


def _build_l5_slim_candidates(commands: list, *, interactive: bool) -> list:
    """压缩 L5 候选，降低模型编造 uid 的概率。"""
    slim = []
    # 复杂模式下候选常因 L4 扩设备而暴涨，去掉 api_set 预览并突出真实 uid
    for c in commands:
        display = str(c.get("display_name") or c.get("uid") or "")
        item = {
            "uid": c.get("uid"),
            "c_brand": c.get("c_brand"),
            "c_instance_id": c.get("c_instance_id"),
            "action": _extract_command_action(display),
            "display_name": display,
            "e_id": c.get("e_id"),
            "e_name": c.get("e_name"),
            "weight": c.get("weight"),
            "device_weight": c.get("device_weight"),
            "preference_desc": c.get("preference_desc"),
            "candidate_kind": c.get("candidate_kind") or "atom",
            "env_match_score": c.get("env_match_score") or 0,
            "env_hint": c.get("env_hint") or "",
            "env_impact": c.get("env_impact") or [],
            "param_schema_summary": param_schema_summary(c.get("param_schema")),
            "optional_params": c.get("optional_param_labels") or [],
        }
        if not interactive:
            api_set = c.get("api_set")
            try:
                s = json.dumps(api_set, ensure_ascii=False)
                item["api_set_preview"] = api_set if len(s) <= 800 else {"_truncated": True, "preview": s[:500]}
            except Exception:
                item["api_set_preview"] = str(api_set)[:500]
        slim.append(item)
    return slim


async def intent_select_commands(
    intent_text: str,
    commands: list,
    prev_layer: dict,
    *,
    resolve_mode: str = "auto",
    max_options_per_step: int = 5,
) -> dict:
    """
    L5：选出有序指令草案。返回公共层字段 + final_plan 结构。
    resolve_mode=auto：托管择一；interactive：每步卡片并列备选供用户切换。
    """
    interactive = str(resolve_mode or "auto").lower() == "interactive"
    valid = {_normalize_id(c["uid"]) for c in commands}
    name_by_id = {
        _normalize_id(c["uid"]): c.get("display_name") or c.get("uid", "") for c in commands
    }
    cmd_by_uid = {_normalize_id(c["uid"]): c for c in commands}

    slim = _build_l5_slim_candidates(commands, interactive=interactive)

    if interactive:
        prompt = """
你是智能家居意图解析助手。请结合上一层「具体设备」结果，从候选可执行组合中规划有序执行草案（复杂选择模式）。
注意：
1. 候选可能是配方（一步内已含开机+效果+可选温度/转速等参数槽）。不要把同一配方里的参数再拆成另一步。
2. 参数数值请保持占位（如 "XX"），不要把温度/档位写进 api_set；口语中的程序名对应枚举槽，仍保持 XX。
3. 用户 preference_desc 仅作倾向提示，不要写死到 api_set。
4. 将用户意图完整分解为有序语义步骤，覆盖意图中的全部子目标，不要漏步。
5. 【最关键】recommended_uid / ordered_uids / alternative_uids 必须原样复制候选列表中的 uid 字段；
   禁止编造；禁止把 c_instance_id 与动作名拼接；禁止只写设备 ID。
6. alternative_uids 只能是「不同具体设备上、能达成与 recommended_uid 完全相同功能」的指令。
   - 禁止列入开/关、开始/结束、启动/停止等相反动作；
   - 若没有可替代设备，alternative_uids 必须为空数组 []。
7. same_device_alternative_uids 仅在少数情况下填写：同一具体设备下、达成相同意图目标的不同指令路径
   （例如「选择洗涤程序」与「自定义洗衣」）；多数步骤必须为空数组 []。
   - 禁止把开/关、查询/控制、或懒人单程序快捷指令列入。
8. ordered_uids 与 steps 中 recommended_uid 顺序必须一致。
9. 设备权重（device_weight）越高越优先作为 recommended_uid。
10. 候选已按 env_match_score 预排序。优先选覆盖 L3 主签名环境的配方（candidate_kind=recipe），不要用开新风/只读温度去替代制冷。
11. env_hint / env_impact 仅作参考，禁止编造环境 ID。
12. 只要候选非空且与意图可能相关，禁止输出空方案。

【用户意图】
{intent_text}

【上一层设备推理结果】
{prev_layer}

【候选可执行组合（uid 必须原样复制）】
{candidates}

【强制输出格式】
只能输出一个合法 JSON 对象：
{
  "selected_nodes": [{"id": "<必须是候选 uid 原文>", "name": "<简述>", "reason": "..."}],
  "ordered_uids": ["<候选 uid 原文>", "<候选 uid 原文>"],
  "steps": [
    {
      "step": 1,
      "intent": "本步语义说明",
      "recommended_uid": "<候选 uid 原文>",
      "alternative_uids": ["<其他设备同功能候选 uid 原文>"],
      "same_device_alternative_uids": []
    }
  ],
  "relations": [{"type": "sequence|cooperate|mutex|alternative", "from_id": "<uid>", "to_id": "<uid>", "note": "..."}],
  "plan_summary": "先……再……的自然语言总结",
  "step_notes": {"<候选 uid 原文>": "该步自然语言说明"},
  "nl_guidance": "整体方案说明"
}
"""
    else:
        prompt = """
你是智能家居意图解析助手。请结合上一层「具体设备」结果，从候选可执行组合中规划有序执行草案。
注意：
1. 候选可能是配方（一步内已含开机+效果+可选温度/转速等参数槽）。不要把同一配方里的参数再拆成另一步。
2. 参数数值请保持占位（如 "XX"），不要把温度/档位写进 api_set。
3. 用户 preference_desc 仅作倾向提示，写入 hint，不要写死到 api_set。
4. ordered_uids 必须全部来自候选 uid，并按建议执行顺序排列；必须原样复制候选 uid，禁止编造或拼接。
5. 将用户意图完整分解为有序步骤，覆盖全部子目标，不要漏步。
6. 可跨设备组合；用 relations 描述步骤间顺序/互斥。
7. 权重越高越优先；env_match_score 更高且 candidate_kind=recipe 的优先于无关原子（如开新风、温度数据获取）。
8. env_hint / env_impact 仅作参考，禁止编造环境 ID。
9. 【最重要】只要候选非空且与意图可能相关，禁止输出空方案；难以区分时任选其一即可。

【用户意图】
{intent_text}

【上一层设备推理结果】
{prev_layer}

【候选可执行组合（含偏好）】
{candidates}

【强制输出格式】
只能输出一个合法 JSON 对象：
{
  "selected_nodes": [{"id": "<uid>", "name": "<简述>", "reason": "..."}],
  "ordered_uids": ["uid1", "uid2"],
  "relations": [{"type": "sequence|cooperate|mutex|alternative", "from_id": "<uid>", "to_id": "<uid>", "note": "..."}],
  "plan_summary": "先……再……的自然语言总结",
  "step_notes": {"<uid>": "该步自然语言说明"},
  "nl_guidance": "整体方案说明"
}
"""
    raw, rendered_prompt, raw_response = await _ainvoke_intent_json(
        prompt,
        {
            "intent_text": intent_text,
            "prev_layer": json.dumps(prev_layer, ensure_ascii=False),
            "candidates": json.dumps(slim, ensure_ascii=False),
        },
    )

    filtered = _filter_layer_selection(raw, valid, name_by_id, prefer_int=False)
    step_plan = _collect_l5_step_plan(raw, commands, cmd_by_uid)

    if step_plan:
        filtered["selected_nodes"] = [
            {
                "id": item["uid"],
                "name": str((cmd_by_uid.get(item["uid"]) or {}).get("uid") or item["uid"]),
                "reason": item.get("intent") or "已映射到真实候选指令",
            }
            for item in step_plan
        ]
        filtered["fallback_applied"] = False
        filtered["uid_resolved"] = True
    else:
        filtered = _ensure_nonempty_selection(
            filtered, commands, id_key="uid", name_key="uid", prefer_int=False
        )
        step_plan = [
            {
                "uid": _normalize_id(n["id"]),
                "intent": "",
                "alts": [],
                "same_device_alts": [],
                "nl_hint": "",
            }
            for n in filtered.get("selected_nodes") or []
            if _normalize_id(n.get("id")) in cmd_by_uid
        ]

    llm_alts_by_uid: Dict[str, List[str]] = {item["uid"]: list(item.get("alts") or []) for item in step_plan}
    same_device_by_uid: Dict[str, List[str]] = {
        item["uid"]: list(item.get("same_device_alts") or []) for item in step_plan
    }
    ordered_steps = []
    weight_rank_decisions: List[dict] = []
    for idx, item in enumerate(step_plan, start=1):
        uid = item["uid"]
        cmd = cmd_by_uid.get(uid) or {}
        nl_step = item.get("nl_hint") or ""
        if not nl_step and filtered.get("fallback_applied"):
            nl_step = f"执行指令：{cmd.get('uid') or uid}"
        step_intent = item.get("intent") or nl_step or f"步骤 {idx}"

        options = _find_alternatives_for_step(
            uid,
            commands,
            cmd_by_uid,
            step_intent=step_intent,
            llm_alternative_uids=llm_alts_by_uid.get(uid),
            llm_same_device_uids=same_device_by_uid.get(uid),
            max_options=max_options_per_step,
        )
        if not options:
            options = [
                _build_step_option_from_cmd(
                    cmd,
                    uid,
                    is_recommended=True,
                    nl_step=nl_step or step_intent,
                    step_intent=step_intent,
                    command_variants=_find_same_device_command_variants(
                        uid,
                        commands,
                        cmd_by_uid,
                        step_intent=step_intent,
                        llm_variant_uids=same_device_by_uid.get(uid),
                    ),
                )
            ]
        recommended = next((o for o in options if o.get("is_recommended")), options[0])
        for opt in options:
            if not opt.get("nl_step"):
                opt["nl_step"] = step_intent

        weight_rank_decisions.append(
            {
                "step": idx,
                "step_intent": step_intent,
                "llm_uid": uid,
                "selected_uid": recommended.get("payload_uid"),
                "device_weight": recommended.get("device_weight"),
                "command_weight": recommended.get("command_weight"),
                "reordered_by_weight": _normalize_id(recommended.get("payload_uid")) != _normalize_id(uid),
                "ranked_options": [
                    {
                        "payload_uid": o.get("payload_uid"),
                        "device_weight": o.get("device_weight"),
                        "command_weight": o.get("command_weight"),
                        "is_recommended": bool(o.get("is_recommended")),
                    }
                    for o in options
                ],
            }
        )

        if interactive:
            step = {
                "step": idx,
                "step_intent": step_intent,
                "options": options,
                "selection_required": len(options) > 1
                or any(len(o.get("command_variants") or []) > 1 for o in options),
                "payload_uid": recommended["payload_uid"],
                "selected_uid": recommended["payload_uid"],
                "c_instance_id": recommended.get("c_instance_id") or "",
                "c_brand": recommended.get("c_brand") or "",
                "e_id": recommended.get("e_id"),
                "e_name": recommended.get("e_name") or "",
                "api_set": recommended.get("api_set"),
                "param_placeholders": recommended.get("param_placeholders") or [],
                "nl_step": recommended.get("nl_step") or nl_step or step_intent,
            }
        else:
            # 自动模式：同样按权重择优，仅保留推荐项作为最终选择
            step = {
                "step": idx,
                "step_intent": step_intent,
                "payload_uid": recommended["payload_uid"],
                "selected_uid": recommended["payload_uid"],
                "c_instance_id": recommended.get("c_instance_id") or "",
                "c_brand": recommended.get("c_brand") or "",
                "e_id": recommended.get("e_id"),
                "e_name": recommended.get("e_name") or "",
                "api_set": recommended.get("api_set"),
                "param_placeholders": recommended.get("param_placeholders") or [],
                "nl_step": recommended.get("nl_step") or nl_step or step_intent,
                "options": [
                    {
                        **recommended,
                        "is_recommended": True,
                        "command_variants": [],
                    }
                ],
                "selection_required": False,
            }
        ordered_steps.append(step)

    filtered["candidate_count"] = len(commands)
    filtered["weight_rank_decisions"] = weight_rank_decisions
    # selected_nodes 与最终权重择优结果对齐
    filtered["selected_nodes"] = [
        {
            "id": s["payload_uid"],
            "name": str(s.get("nl_step") or s["payload_uid"]),
            "reason": s.get("step_intent") or "按权重优先选定",
        }
        for s in ordered_steps
    ]
    plan_summary = str(raw.get("plan_summary") or filtered.get("nl_guidance") or "")
    if not plan_summary and ordered_steps:
        plan_summary = "；".join(
            s.get("step_intent") or s.get("nl_step") or s.get("payload_uid") for s in ordered_steps
        )
    bind_plan_placeholders(ordered_steps, intent_text)
    filtered["final_plan"] = {
        "plan_summary": plan_summary,
        "ordered_steps": ordered_steps,
        "relations": filtered["relations"],
        "nl_guidance": str(raw.get("nl_guidance") or filtered.get("nl_guidance") or ""),
        "resolve_mode": "interactive" if interactive else "auto",
        "weight_rank_decisions": weight_rank_decisions,
    }
    return _attach_layer_trace(
        filtered,
        layer="l5",
        layer_input={
            "intent_text": intent_text,
            "prev_layer": {
                "selected_nodes": (prev_layer or {}).get("selected_nodes") or [],
                "relations": (prev_layer or {}).get("relations") or [],
                "nl_guidance": (prev_layer or {}).get("nl_guidance") or "",
            },
            "candidate_count": len(commands),
            "candidate_uids": [c.get("uid") for c in slim],
            "resolve_mode": resolve_mode,
        },
        prompt=rendered_prompt,
        raw_response=raw_response,
        raw_parsed=raw,
    )
