"""意图寻址后台作业。前端轮询 GET /api/intent/jobs/{id}。"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

PHASE_INDEX = {"l1": 0, "l2": 1, "l3": 2, "l4": 3, "l5": 4}
PHASE_LABELS = {
    "l1": "L1 领域",
    "l2": "L2 对象",
    "l3": "L3 效果",
    "l4": "L4 设备",
    "l5": "L5 指令",
}

_CURRENT_JOB_ID: ContextVar[Optional[str]] = ContextVar("intent_job_id", default=None)
_JOBS: Dict[str, "IntentJob"] = {}
_LOCK = asyncio.Lock()


@dataclass
class IntentJob:
    job_id: str
    status: str = "queued"
    phase: str = "l1"
    phase_index: int = 0
    message: str = ""
    intent_text: str = ""
    resolve_mode: str = "auto"
    layers: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    def snapshot(self) -> Dict[str, Any]:
        now = self.finished_at or time.time()
        return {
            "job_id": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "phase_index": self.phase_index,
            "phase_label": PHASE_LABELS.get(self.phase, self.phase or ""),
            "message": self.message,
            "intent_text": self.intent_text,
            "layers": dict(self.layers or {}),
            "result": self.result,
            "elapsed_ms": int(max(0, now - self.started_at) * 1000),
        }


def get_job(job_id: str) -> Optional[IntentJob]:
    return _JOBS.get(str(job_id or "").strip())


def running_job() -> Optional[IntentJob]:
    for job in _JOBS.values():
        if job.status in {"queued", "running"}:
            return job
    return None


def current_job() -> Optional[IntentJob]:
    jid = _CURRENT_JOB_ID.get()
    if not jid:
        return None
    return _JOBS.get(jid)


def _layers_dump(layers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in (layers or {}).items():
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            out[key] = dumped if isinstance(dumped, dict) else {"layer": key}
        elif isinstance(value, dict):
            out[key] = dict(value)
        else:
            out[key] = {"layer": key}
    return out


def report(*, phase: str = "", message: str = "", layers: Optional[Dict[str, Any]] = None) -> None:
    job = current_job()
    if not job:
        return
    if phase:
        job.phase = phase
        job.phase_index = PHASE_INDEX.get(phase, job.phase_index)
        job.message = message or f"正在执行 {PHASE_LABELS.get(phase, phase)}…"
    elif message:
        job.message = message
    if layers is not None:
        job.layers = _layers_dump(layers)


def report_layers(phase: str, layers: Dict[str, Any], message: str = "") -> None:
    report(phase=phase, message=message, layers=layers)


async def start_intent_job(body: Dict[str, Any]) -> IntentJob:
    async with _LOCK:
        live = running_job()
        if live:
            raise RuntimeError("已有意图实现作业在运行，请等待结束后再开始")
        options = body.get("options") if isinstance(body.get("options"), dict) else {}
        job = IntentJob(
            job_id=f"intent-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
            intent_text=str(body.get("intent_text") or "").strip(),
            resolve_mode=str(options.get("resolve_mode") or "auto"),
            status="queued",
            phase="l1",
            phase_index=0,
            message="排队中…",
        )
        _JOBS[job.job_id] = job
        if len(_JOBS) > 40:
            stale = [jid for jid, row in _JOBS.items() if row.status not in {"queued", "running"}]
            for jid in stale[:-20]:
                _JOBS.pop(jid, None)
    asyncio.create_task(execute_job(job.job_id, body))
    return job


async def execute_job(job_id: str, body: Dict[str, Any]) -> None:
    job = get_job(job_id)
    if not job:
        return
    token = _CURRENT_JOB_ID.set(job.job_id)
    job.status = "running"
    job.started_at = time.time()
    job.message = "正在执行 L1 领域层推理…"
    try:
        from database import AsyncSessionLocal
        from schemas import IntentResolveRequest
        import main as main_mod

        req = IntentResolveRequest(**body)
        async with AsyncSessionLocal() as db:
            result = await main_mod.resolve_intent(req, db)
        dump = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        job.result = dump
        job.layers = dump.get("layers") or job.layers
        job.status = "success"
        job.phase = "l5" if dump.get("layers", {}).get("l5") else (dump.get("stopped_at") or job.phase)
        job.phase_index = PHASE_INDEX.get(str(job.phase), 4)
        job.message = dump.get("message") or "意图实现完成"
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        job.status = "failed"
        job.message = str(detail or exc)[:400]
    finally:
        job.finished_at = time.time()
        _CURRENT_JOB_ID.reset(token)
