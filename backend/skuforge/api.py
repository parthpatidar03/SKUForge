"""FastAPI app: enrich SKUs, stream agent events (SSE), HITL review, batch runs.

Run: uvicorn skuforge.api:app --reload --port 8000
"""
import asyncio
import csv
import io
import logging
import uuid

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import config, store
from .models import AttributeStatus, PipelineEvent, RecordStatus, SKUInput
from .orchestrator import run_sku

logger = logging.getLogger("skuforge")

app = FastAPI(title="SKUForge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# record_id -> asyncio.Queue of PipelineEvent (None terminates the stream)
_event_queues: dict[str, asyncio.Queue] = {}


def _emit_factory(record_id: str, loop: asyncio.AbstractEventLoop):
    queue: asyncio.Queue = asyncio.Queue()
    _event_queues[record_id] = queue

    def emit(event: PipelineEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    return emit


async def _run_in_thread(sku: SKUInput, record_id: str) -> None:
    loop = asyncio.get_running_loop()
    emit = _emit_factory(record_id, loop)
    try:
        await asyncio.to_thread(run_sku, sku, emit, record_id)
    except Exception:
        # Record is already persisted as failed by the orchestrator, but the
        # traceback must still reach the server log or failures are invisible.
        logger.exception("pipeline failed for record %s (%s)", record_id, sku.mpn)
    finally:
        queue = _event_queues.get(record_id)
        if queue:
            loop.call_soon_threadsafe(queue.put_nowait, None)


@app.post("/api/enrich")
async def enrich(sku: SKUInput):
    """Start pipeline for one SKU. Returns record_id; stream events via SSE."""
    record_id = uuid.uuid4().hex[:12]
    asyncio.create_task(_run_in_thread(sku, record_id))
    return {"record_id": record_id}


@app.get("/api/events/{record_id}")
async def events(record_id: str):
    """SSE stream of PipelineEvents for the agent theatre."""
    queue = _event_queues.get(record_id)
    if queue is None:
        raise HTTPException(404, "no active run for this record_id")

    async def gen():
        while True:
            event = await queue.get()
            if event is None:
                yield "event: done\ndata: {}\n\n"
                _event_queues.pop(record_id, None)
                break
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/records")
async def list_records():
    return [
        {
            "id": r.id, "mpn": r.input.mpn, "brand": r.input.brand,
            "category": r.category, "status": r.status.value,
            "seo_title": r.seo_title, "cost_usd": r.cost_usd,
            "duration_s": r.duration_s, "created_at": r.created_at,
            "attribute_count": len(r.attributes),
            "conflict_count": sum(
                1 for a in r.attributes if a.status == AttributeStatus.conflict
            ),
        }
        for r in store.list_all()
    ]


@app.get("/api/records/{record_id}")
async def get_record(record_id: str):
    record = store.get(record_id)
    if record is None:
        raise HTTPException(404, "record not found")
    return record


class ReviewAction(BaseModel):
    attribute_name: str
    action: str  # approve | reject | edit
    new_value: str = ""
    new_unit: str = ""


@app.post("/api/records/{record_id}/review")
async def review(record_id: str, body: ReviewAction):
    """HITL: approve/reject/edit one attribute; approve record when clean."""
    record = store.get(record_id)
    if record is None:
        raise HTTPException(404, "record not found")

    for attr in record.attributes:
        if attr.name == body.attribute_name:
            if body.action == "approve":
                attr.human_reviewed = True
                attr.confidence = 1.0
                attr.status = AttributeStatus.verified
                attr.conflicting_values = []
            elif body.action == "edit":
                attr.value = body.new_value
                attr.unit = body.new_unit or attr.unit
                attr.human_reviewed = True
                attr.confidence = 1.0
                attr.status = AttributeStatus.verified
                attr.conflicting_values = []
            elif body.action == "reject":
                record.attributes = [
                    a for a in record.attributes if a.name != body.attribute_name
                ]
            else:
                raise HTTPException(400, "action must be approve|edit|reject")
            break
    else:
        raise HTTPException(404, "attribute not found")

    if all(
        a.human_reviewed or a.confidence >= config.AUTO_APPROVE_THRESHOLD
        for a in record.attributes
    ):
        record.status = RecordStatus.approved
    store.save(record)
    return record


@app.post("/api/batch")
async def batch(file: UploadFile):
    """CSV upload: columns mpn,brand,description. Runs pipeline per row."""
    content = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(content)))
    if not rows or "mpn" not in rows[0]:
        raise HTTPException(400, "CSV needs header: mpn,brand,description")

    record_ids = []
    for row in rows:
        sku = SKUInput(
            mpn=row["mpn"].strip(),
            brand=row.get("brand", "").strip(),
            description=row.get("description", "").strip(),
        )
        record_id = uuid.uuid4().hex[:12]
        record_ids.append(record_id)
        asyncio.create_task(_run_in_thread(sku, record_id))
    return {"record_ids": record_ids, "count": len(record_ids)}


@app.get("/api/stats")
async def stats():
    """Batch dashboard numbers: throughput, cost, auto-approval rate."""
    records = store.list_all()
    done = [r for r in records if r.status != RecordStatus.processing]
    auto = [r for r in done if r.status == RecordStatus.auto_approved]
    total_attrs = sum(len(r.attributes) for r in done)
    flagged_attrs = sum(
        1 for r in done for a in r.attributes
        if a.confidence < config.AUTO_APPROVE_THRESHOLD
        or a.status == AttributeStatus.conflict
    )
    return {
        "total_records": len(records),
        "completed": len(done),
        "auto_approved": len(auto),
        "auto_approval_rate": round(len(auto) / len(done), 3) if done else 0,
        "total_cost_usd": round(sum(r.cost_usd for r in done), 4),
        "avg_cost_usd": round(sum(r.cost_usd for r in done) / len(done), 4) if done else 0,
        "avg_duration_s": round(sum(r.duration_s for r in done) / len(done), 1) if done else 0,
        "total_attributes": total_attrs,
        "attributes_flagged_for_review": flagged_attrs,
        "mock_mode": config.MOCK_MODE,
    }


@app.get("/api/export/{record_id}.csv")
async def export_csv(record_id: str):
    """Syndication-ready flat CSV of one record."""
    record = store.get(record_id)
    if record is None:
        raise HTTPException(404, "record not found")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["field", "value", "confidence", "status"])
    w.writerow(["mpn", record.input.mpn, "", ""])
    w.writerow(["brand", record.input.brand, "", ""])
    w.writerow(["category", record.category, record.category_confidence, ""])
    w.writerow(["seo_title", record.seo_title, "", ""])
    w.writerow(["short_description", record.short_description, "", ""])
    for a in record.attributes:
        w.writerow([a.name, f"{a.value} {a.unit}".strip(), a.confidence, a.status.value])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={record.input.mpn}.csv"},
    )
