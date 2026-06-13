"""
LogScope Backend – FastAPI + Drain3 + Apache Doris 4.x (OTel Native Schema)
============================================================================

Column names used throughout match the EXACT dorisexporter schema:

    timestamp             DATETIME(6)
    service_name          VARCHAR(200)
    service_instance_id   VARCHAR(200)
    trace_id              VARCHAR(200)
    span_id               STRING
    severity_number       INT
    severity_text         STRING
    body                  STRING           ← full-text indexed (unicode parser)
    resource_attributes   VARIANT
    log_attributes        VARIANT
    scope_name            STRING
    scope_version         STRING

Design principles
─────────────────
• READ-ONLY Doris  – logs arrive via OTel Collector → Doris Stream Load.
  This backend only SELECTs from otel.otel_logs; it never INSERTs.

• On-demand Drain3 – /api/patterns pulls body strings from Doris for the
  requested time window, runs Drain3, returns clusters. Nothing is stored.

• Pre-written mask presets – 14 named rules, user selects via checkboxes.
  No free-form regex input; patterns visible as amber tokens in the UI.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone as _tz
from typing import Any

import pymysql
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.masking import MaskingInstruction

from config import settings
from mask_presets import MASK_PRESETS, PRESETS_BY_ID, DEFAULT_ACTIVE_IDS

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="LogScope API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Drain3 state (in-process, protected by lock) ──────────────────────────────

_drain_lock = threading.Lock()

_drain_state: dict[str, Any] = {
    "sim_th":           0.5,
    "depth":            6,
    "active_mask_ids":  list(DEFAULT_ACTIVE_IDS),
}


def _build_miner(sim_th: float, depth: int, active_ids: list[str]) -> TemplateMiner:
    cfg = TemplateMinerConfig()
    cfg.drain_sim_th              = sim_th
    cfg.drain_depth               = depth
    cfg.drain_max_children        = 100
    cfg.parametrize_numeric_tokens = True
    cfg.masking_instructions = [
        MaskingInstruction(PRESETS_BY_ID[pid]["pattern"], PRESETS_BY_ID[pid]["token"])
        for pid in active_ids
        if pid in PRESETS_BY_ID
    ]
    return TemplateMiner(config=cfg)


# ── Doris helpers ─────────────────────────────────────────────────────────────

def _get_conn() -> pymysql.Connection:
    return pymysql.connect(
        host=settings.DORIS_HOST,
        port=settings.DORIS_PORT,
        user=settings.DORIS_USER,
        password=settings.DORIS_PASSWORD,
        database=settings.DORIS_DB,
        connect_timeout=10,
        read_timeout=60,
    )


def _norm_ts(ts: str) -> str:
    """ISO 8601 → Doris DATETIME string."""
    return ts.replace("T", " ").replace("Z", "")


def _where(clauses: list[str]) -> str:
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DrainConfigUpdate(BaseModel):
    sim_th: float | None = None
    depth:  int   | None = None


class MaskSelectionUpdate(BaseModel):
    active_ids: list[str]


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    for attempt in range(40):
        try:
            _get_conn().close()
            print("LogScope API: Doris connection OK.")
            return
        except Exception as exc:
            print(f"[startup] Waiting for Doris ({attempt + 1}/40): {exc}")
            time.sleep(4)
    print("[startup] WARNING: could not reach Doris. API starting anyway.")


# ═════════════════════════════════════════════════════════════════════════════
# LOGS
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/logs")
def get_logs(
    q:        str = Query(default="", description="Full-text search on body (MATCH_ANY unicode)"),
    severity: str = Query(default="", description="Filter by severity_text"),
    service:  str = Query(default="", description="Filter by service_name"),
    start:    str = Query(default="", description="ISO 8601 start timestamp"),
    end:      str = Query(default="", description="ISO 8601 end timestamp"),
    limit:    int = Query(default=200, le=2000),
    offset:   int = Query(default=0),
    q_mode:   str = Query(default="MATCH_ANY", description="Match operator for body search"),
):
    """
    Query otel_logs with optional full-text search on body via Doris
    MATCH_ANY (unicode inverted index), plus severity/service/time filters.
    Returns paginated rows shaped as the OTel native schema.
    """
    valid_modes = {
        "MATCH_ANY",
        "MATCH_ALL",
        "MATCH_PHRASE",
        "MATCH_PHRASE_PREFIX",
        "MATCH_PHRASE_EDGE",
        "MATCH_REGEXP",
    }
    if q_mode not in valid_modes:
        q_mode = "MATCH_ANY"

    clauses: list[str] = []
    params:  list[Any] = []

    if q:
        clauses.append(f"body {q_mode} %s")
        params.append(q)
    if severity:
        clauses.append("severity_text = %s")
        params.append(severity.upper())
    if service:
        clauses.append("service_name = %s")
        params.append(service)
    if start:
        clauses.append("timestamp >= %s")
        params.append(_norm_ts(start))
    if end:
        clauses.append("timestamp <= %s")
        params.append(_norm_ts(end))

    where = _where(clauses)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT timestamp, service_name, service_instance_id, "
                f"trace_id, span_id, severity_number, severity_text, "
                f"body, log_attributes, scope_name, scope_version "
                f"FROM otel_logs {where} "
                f"ORDER BY timestamp DESC LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            rows = cur.fetchall()

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM otel_logs {where}", params)
            total = cur.fetchone()[0]

        logs = [
            {
                "timestamp":           str(r[0]),
                "service_name":        r[1],
                "service_instance_id": r[2],
                "trace_id":            r[3],
                "span_id":             r[4],
                "severity_number":     r[5],
                "severity_text":       r[6],
                "body":                r[7],
                "log_attributes":      r[8],
                "scope_name":          r[9],
                "scope_version":       r[10],
            }
            for r in rows
        ]
        return {"total": total, "logs": logs}
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# PATTERNS  (on-demand Drain3 — no storage)
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/patterns")
def get_patterns(
    start:     str = Query(default=""),
    end:       str = Query(default=""),
    service:   str = Query(default=""),
    severity:  str = Query(default=""),
    min_count: int = Query(default=2),
    limit:     int = Query(default=50, le=500),
    max_logs:  int = Query(default=50000, le=200000),
):
    """
    On-demand log pattern detection:
    1. Pull body strings from otel_logs for the time window (read-only).
    2. Build a fresh Drain3 TemplateMiner with the active masking presets.
    3. Feed all bodies into Drain3 (first pass: build clusters).
    4. Re-match every body to count hits per cluster (second pass).
    5. Return sorted cluster list with templates, counts, and mask labels.
    Patterns are NOT persisted anywhere.
    """
    with _drain_lock:
        sim_th     = _drain_state["sim_th"]
        depth      = _drain_state["depth"]
        active_ids = list(_drain_state["active_mask_ids"])

    miner = _build_miner(sim_th, depth, active_ids)

    clauses: list[str] = []
    params:  list[Any] = []
    if start:
        clauses.append("timestamp >= %s");  params.append(_norm_ts(start))
    if end:
        clauses.append("timestamp <= %s");  params.append(_norm_ts(end))
    if service:
        clauses.append("service_name = %s"); params.append(service)
    if severity:
        clauses.append("severity_text = %s"); params.append(severity.upper())

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT body FROM otel_logs {_where(clauses)} "
                f"ORDER BY timestamp DESC LIMIT %s",
                params + [max_logs],
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return {"patterns": [], "logs_analysed": 0, "active_masks": active_ids}

    # Pass 1 – build clusters
    for (body,) in rows:
        if body:
            miner.add_log_message(str(body))

    # Pass 2 – count hits per cluster
    counts: dict[int, int] = {}
    for (body,) in rows:
        if body:
            cluster = miner.match(str(body))
            if cluster:
                counts[cluster.cluster_id] = counts.get(cluster.cluster_id, 0) + 1

    # Build response
    patterns = []
    for c in miner.drain.clusters:
        count = counts.get(c.cluster_id, 0)
        if count < min_count:
            continue
        template = c.get_template()
        # Which mask labels appear in this template?
        mask_labels = [
            PRESETS_BY_ID[pid]["label"]
            for pid in active_ids
            if pid in PRESETS_BY_ID
            and PRESETS_BY_ID[pid]["token"].replace("<", "").replace(">", "")
                in template
        ]
        patterns.append({
            "cluster_id":  c.cluster_id,
            "template":    template,
            "count":       count,
            "mask_tokens": mask_labels,
        })

    patterns.sort(key=lambda x: x["count"], reverse=True)
    return {
        "patterns":      patterns[:limit],
        "logs_analysed": len(rows),
        "active_masks":  active_ids,
    }


@app.get("/api/patterns/timeseries")
def pattern_timeseries(
    cluster_id: int = Query(...),
    start:      str = Query(default=""),
    end:        str = Query(default=""),
    service:    str = Query(default=""),
    bucket:     str = Query(default="1h", description="5m|15m|1h|6h|1d"),
    max_logs:   int = Query(default=50000, le=200000),
):
    """
    Time-bucketed hit count for one cluster_id.
    Re-builds Drain3 from Doris data then buckets matching rows by timestamp.
    """
    bucket_secs = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}
    secs = bucket_secs.get(bucket, 3600)

    with _drain_lock:
        sim_th     = _drain_state["sim_th"]
        depth      = _drain_state["depth"]
        active_ids = list(_drain_state["active_mask_ids"])

    miner = _build_miner(sim_th, depth, active_ids)

    clauses: list[str] = []
    params:  list[Any] = []
    if start:
        clauses.append("timestamp >= %s"); params.append(_norm_ts(start))
    if end:
        clauses.append("timestamp <= %s"); params.append(_norm_ts(end))
    if service:
        clauses.append("service_name = %s"); params.append(service)

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT timestamp, body FROM otel_logs {_where(clauses)} "
                f"ORDER BY timestamp ASC LIMIT %s",
                params + [max_logs],
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    for (_, body) in rows:
        if body:
            miner.add_log_message(str(body))

    buckets: dict[int, int] = {}
    for (ts, body) in rows:
        if not body:
            continue
        cluster = miner.match(str(body))
        if cluster and cluster.cluster_id == cluster_id:
            epoch = ts.timestamp() if hasattr(ts, "timestamp") else \
                datetime.fromisoformat(str(ts)).replace(tzinfo=_tz.utc).timestamp()
            bk = int(epoch // secs) * secs
            buckets[bk] = buckets.get(bk, 0) + 1

    series = [
        {
            "ts":    datetime.fromtimestamp(k, tz=_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": v,
        }
        for k, v in sorted(buckets.items())
    ]
    return {"cluster_id": cluster_id, "bucket": bucket, "series": series}


@app.get("/api/patterns/{cluster_id}/samples")
def pattern_samples(
    cluster_id: int,
    start:      str = Query(default=""),
    end:        str = Query(default=""),
    service:    str = Query(default=""),
    severity:   str = Query(default=""),
    sample_size: int = Query(default=10, le=20),
    max_logs:   int = Query(default=50000, le=200000),
):
    """
    Return a small sample of actual log lines that match a specific Drain3
    cluster.  Re-builds the miner from the same data window, then collects
    rows whose match() returns the requested cluster_id.
    """
    with _drain_lock:
        sim_th     = _drain_state["sim_th"]
        depth      = _drain_state["depth"]
        active_ids = list(_drain_state["active_mask_ids"])

    miner = _build_miner(sim_th, depth, active_ids)

    clauses: list[str] = []
    params:  list[Any] = []
    if start:
        clauses.append("timestamp >= %s");  params.append(_norm_ts(start))
    if end:
        clauses.append("timestamp <= %s");  params.append(_norm_ts(end))
    if service:
        clauses.append("service_name = %s"); params.append(service)
    if severity:
        clauses.append("severity_text = %s"); params.append(severity.upper())

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT timestamp, service_name, severity_text, body "
                f"FROM otel_logs {_where(clauses)} "
                f"ORDER BY timestamp DESC LIMIT %s",
                params + [max_logs],
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return {"cluster_id": cluster_id, "samples": [], "total_matched": 0}

    # Pass 1 – build clusters
    for r in rows:
        if r[3]:
            miner.add_log_message(str(r[3]))

    # Pass 2 – collect matching samples
    samples: list[dict] = []
    total_matched = 0
    for (ts, svc, sev, body) in rows:
        if not body:
            continue
        cluster = miner.match(str(body))
        if cluster and cluster.cluster_id == cluster_id:
            total_matched += 1
            if len(samples) < sample_size:
                samples.append({
                    "timestamp":     str(ts),
                    "service_name":  svc,
                    "severity_text": sev,
                    "body":          str(body),
                })

    return {
        "cluster_id":    cluster_id,
        "samples":       samples,
        "total_matched": total_matched,
    }


# ═════════════════════════════════════════════════════════════════════════════
# DRAIN CONFIG
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/drain/config")
def get_drain_config():
    return {
        "sim_th":          _drain_state["sim_th"],
        "depth":           _drain_state["depth"],
        "active_mask_ids": _drain_state["active_mask_ids"],
    }


@app.put("/api/drain/config")
def update_drain_config(cfg: DrainConfigUpdate):
    if cfg.sim_th is not None:
        if not (0.1 <= cfg.sim_th <= 1.0):
            raise HTTPException(400, "sim_th must be 0.1–1.0")
        _drain_state["sim_th"] = round(cfg.sim_th, 2)
    if cfg.depth is not None:
        if not (2 <= cfg.depth <= 10):
            raise HTTPException(400, "depth must be 2–10")
        _drain_state["depth"] = cfg.depth
    return {"status": "ok", "sim_th": _drain_state["sim_th"], "depth": _drain_state["depth"]}


# ═════════════════════════════════════════════════════════════════════════════
# MASK PRESETS
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/masks/presets")
def get_mask_presets():
    """All 14 pre-written mask presets with metadata for UI checkboxes."""
    return {"presets": MASK_PRESETS}


@app.get("/api/masks/active")
def get_active_masks():
    return {
        "active_ids": _drain_state["active_mask_ids"],
        "presets": [
            PRESETS_BY_ID[pid]
            for pid in _drain_state["active_mask_ids"]
            if pid in PRESETS_BY_ID
        ],
    }


@app.put("/api/masks/active")
def update_active_masks(body: MaskSelectionUpdate):
    """Set active mask preset IDs. Only IDs from MASK_PRESETS are accepted."""
    unknown = [pid for pid in body.active_ids if pid not in PRESETS_BY_ID]
    if unknown:
        raise HTTPException(400, f"Unknown preset IDs: {unknown}")
    _drain_state["active_mask_ids"] = list(body.active_ids)
    return {"status": "ok", "active_ids": _drain_state["active_mask_ids"]}


@app.post("/api/masks/reset")
def reset_active_masks():
    _drain_state["active_mask_ids"] = list(DEFAULT_ACTIVE_IDS)
    return {"status": "reset", "active_ids": _drain_state["active_mask_ids"]}


# ═════════════════════════════════════════════════════════════════════════════
# STATS
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/stats")
def get_stats(
    start: str = Query(default=""),
    end:   str = Query(default=""),
):
    clauses: list[str] = []
    params:  list[Any] = []
    if start:
        clauses.append("timestamp >= %s"); params.append(_norm_ts(start))
    if end:
        clauses.append("timestamp <= %s"); params.append(_norm_ts(end))
    where = _where(clauses)

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM otel_logs {where}", params)
            total = cur.fetchone()[0]

            cur.execute(
                f"SELECT severity_text, COUNT(*) FROM otel_logs {where} "
                f"GROUP BY severity_text",
                params,
            )
            by_severity = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute(
                f"SELECT service_name, COUNT(*) FROM otel_logs {where} "
                f"GROUP BY service_name ORDER BY 2 DESC",
                params,
            )
            by_service = [{"service": r[0], "count": r[1]} for r in cur.fetchall()]

            # Hourly sparkline – always last 24 h regardless of time filter
            cur.execute(
                "SELECT DATE_FORMAT(timestamp,'%Y-%m-%dT%H:00:00Z') AS hr, COUNT(*) "
                "FROM otel_logs "
                "WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR) "
                "GROUP BY hr ORDER BY hr ASC"
            )
            hourly = [{"ts": r[0], "count": r[1]} for r in cur.fetchall()]

    finally:
        conn.close()

    return {
        "total":       total,
        "by_severity": by_severity,
        "by_service":  by_service,
        "hourly":      hourly,
    }


@app.get("/api/services")
def get_services():
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT service_name FROM otel_logs "
                "WHERE service_name IS NOT NULL AND service_name != '' "
                "ORDER BY service_name"
            )
            return {"services": [r[0] for r in cur.fetchall()]}
    finally:
        conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}
