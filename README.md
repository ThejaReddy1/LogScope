# LogScope — OTel Log Analysis Platform

Full-stack observability platform for Apache/Nginx log analysis built on:

| Layer | Technology | Role |
|---|---|---|
| Ingestion | **Apache/Nginx Log Simulator** | Generates realistic access + error logs as OTLP |
| Transport | **OTel Collector 0.102** | OTLP → Doris Stream Load pipeline |
| Storage | **Apache Doris 4.0** | OTel native schema with inverted-index FTS |
| Analysis | **FastAPI + Drain3** | Read-only queries, on-demand pattern detection |
| UI | **React + Recharts** | 4-tab dashboard — Overview, Logs, Patterns, Settings |

---

## Quick Start

```bash
docker compose up --build
```

Wait ~2 minutes for Doris to initialise. Watch for:
```
logscope-simulator   | [simulator] Sent batch of 5 records (total=5)
logscope-otel-collector | ... exported 5 log records
```

Open **http://localhost:3000**

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Apache/Nginx Log Simulator              │
│  Generates Combined + Error format logs as OTLP      │
│  4 services: apache-frontend, nginx-gateway,          │
│              apache-api, nginx-static                 │
└────────────────────────┬────────────────────────────┘
                         │ OTLP/HTTP :4318
┌────────────────────────▼────────────────────────────┐
│           OTel Collector contrib:0.102.0              │
│  Receiver: OTLP (gRPC :4317 / HTTP :4318)            │
│  Processor: batch (5000 records / 5s)                │
│  Exporter: dorisexporter → Stream Load               │
└────────────────────────┬────────────────────────────┘
                         │ HTTP Stream Load :8030
┌────────────────────────▼────────────────────────────┐
│            Apache Doris 4.0                          │
│   FE (query planner)    :9030 MySQL / :8030 HTTP     │
│   BE (columnar storage) :8040 HTTP                   │
│                                                      │
│   Database: otel                                     │
│   Table:    otel_logs  (OTel native schema)          │
│   Indexes:  INVERTED on Body, SeverityText,          │
│             ServiceName                              │
│   Partition: RANGE(Timestamp) by quarter             │
└─────────────┬───────────────────────────────────────┘
              │ PyMySQL :9030 (READ-ONLY)
┌─────────────▼───────────────────────────────────────┐
│            FastAPI Backend                           │
│  • Queries otel_logs – never INSERTs                 │
│  • On-demand Drain3 analysis per request             │
│  • Pre-written masking presets (14 rules)            │
│  • Drain3 sim_th / depth configurable                │
└─────────────┬───────────────────────────────────────┘
              │ HTTP /api/* (proxied by Nginx)
┌─────────────▼───────────────────────────────────────┐
│            React UI  :3000                           │
│  Overview │ Logs │ Patterns │ Settings               │
└─────────────────────────────────────────────────────┘
```

---

## Ports

| Port | Service | Purpose |
|------|---------|---------|
| 3000 | frontend | LogScope React UI |
| 8000 | backend | FastAPI direct access |
| 8030 | doris-fe | Doris HTTP / Stream Load |
| 9030 | doris-fe | Doris MySQL protocol |
| 8040 | doris-be | Doris BE HTTP |
| 4317 | otel-collector | OTLP gRPC |
| 4318 | otel-collector | OTLP HTTP |
| 13133 | otel-collector | Health check |
| 8888 | otel-collector | Self-telemetry metrics |

---

## OTel Native Schema — otel.otel_logs

```sql
CREATE TABLE otel_logs (
    Timestamp           DATETIME(6)  -- Event time (partition key)
    ObservedTimestamp   DATETIME(6)  -- Collector receive time
    TraceId             VARCHAR(32)  -- 128-bit trace ID (hex)
    SpanId              VARCHAR(16)  -- 64-bit span ID (hex)
    TraceFlags          TINYINT      -- W3C trace flags
    SeverityText        VARCHAR(32)  -- INFO / WARN / ERROR / DEBUG
    SeverityNumber      TINYINT      -- 9=INFO 13=WARN 17=ERROR
    ServiceName         VARCHAR(256) -- service.name resource attr
    Body                TEXT         -- Raw log line (FTS indexed)
    ResourceAttributes  VARIANT      -- OTel resource attrs (JSON)
    LogAttributes       VARIANT      -- Parsed log fields (JSON)
)
PARTITION BY RANGE(Timestamp)   -- Partition pruning for time queries
DISTRIBUTED BY HASH(ServiceName) BUCKETS 4
INDEX idx_body    ON Body    USING INVERTED (parser=english)
INDEX idx_sev     ON SeverityText USING INVERTED
INDEX idx_service ON ServiceName  USING INVERTED
```

The `Body` column stores the raw Apache/Nginx log line. LogAttributes holds parsed fields (http.method, http.status_code, net.peer.ip, etc.) as a VARIANT JSON column.

---

## Simulated Log Formats

**Apache Combined Access Log:**
```
203.0.113.1 - - [04/Jun/2026:12:00:00 +0000] "GET /api/v1/orders HTTP/1.1" 200 1024 "-" "Mozilla/5.0"
```

**Nginx Combined Access Log:**
```
198.51.100.42 - - [04/Jun/2026:12:00:01 +0000] "POST /api/v1/auth/login HTTP/1.1" 200 256 "-" "curl/8.7.1"
```

**Apache Error Log:**
```
[Thu Jun 04 12:00:02.123456 UTC] [error] [pid 4521] AH01630: client denied by server configuration
```

**Nginx Error Log:**
```
2026/06/04 12:00:03 [error] 1234#5: *9871 upstream timed out (110: Connection timed out)
```

---

## Pattern Analysis — How It Works

1. User sets time range, service/severity filters, and clicks **Analyse Patterns**
2. Backend pulls `Body` strings from `otel_logs` (up to 50,000 rows, read-only)
3. A fresh Drain3 `TemplateMiner` is built with the active masking presets
4. All log lines are fed into Drain3 (first pass: cluster building)
5. Each log is re-matched against clusters (second pass: accurate counting)
6. Templates are returned with counts and highlighted mask tokens
7. **No patterns are stored** — every analysis call is stateless and fresh

### Example Drain3 Templates (with masking active)

| Raw logs | Drain3 template |
|----------|----------------|
| `203.0.113.1 - - [...] "GET /api/v1/orders/9831 HTTP/1.1" 200 1024` | `<IP_ADDRESS> - - [<*>] "GET /api/v1/orders/<ID> HTTP/1.1" <*> <*>` |
| `2026/06/04 12:00:03 [error] 1234#5: *9871 upstream timed out` | `<*> [error] <PID>: <*> upstream timed out (<*>: Connection timed out)` |

---

## Masking Presets (14 Pre-Written Rules)

| Category | ID | Label | Token |
|----------|----|-------|-------|
| Network | ipv4 | IPv4 Address | `<IP_ADDRESS>` |
| Network | ipv6 | IPv6 Address | `<IPV6_ADDRESS>` |
| Network | port | Port Number | `<PORT>` |
| Identity | email | Email Address | `<EMAIL>` |
| Identity | uuid | UUID / GUID | `<UUID>` |
| Identity | trace_id | Trace / Span ID | `<TRACE_ID>` |
| Web | http_numeric_id | HTTP Path Numeric ID | `<ID>` |
| Web | query_string | URL Query String | `?<QUERY>` |
| Web | user_agent | User-Agent String | `"<USER_AGENT>"` |
| System | pid | Process / Thread ID | `<PID>` |
| System | file_path | File System Path | `<FILE_PATH>` |
| System | number | Generic Numbers | `<NUM>` |
| Security | bearer_token | Bearer Token | `Bearer <TOKEN>` |
| Security | api_key | API Key / Secret | `<API_KEY>` |

**Defaults active:** `ipv4`, `uuid`, `trace_id`, `http_numeric_id`, `pid`

---

## API Reference

### Logs
```
GET /api/logs
  ?q=<full-text>     MATCH_ANY inverted index on Body
  &severity=ERROR    Filter by SeverityText
  &service=nginx-gateway
  &start=<ISO8601>
  &end=<ISO8601>
  &limit=200  &offset=0
```

### Patterns (on-demand Drain3)
```
GET /api/patterns
  ?start=&end=&service=&severity=&min_count=2&limit=50&max_logs=50000

GET /api/patterns/timeseries
  ?cluster_id=<int>&start=&end=&service=&bucket=1h
  bucket: 5m | 15m | 1h | 6h | 1d
```

### Drain3 Config
```
GET  /api/drain/config
PUT  /api/drain/config        {"sim_th": 0.4, "depth": 4}
```

### Mask Presets
```
GET  /api/masks/presets       All 14 pre-written presets with metadata
GET  /api/masks/active        Currently active preset IDs
PUT  /api/masks/active        {"active_ids": ["ipv4", "uuid", "pid"]}
POST /api/masks/reset         Reset to defaults
```

### Stats
```
GET /api/stats?start=&end=    Severity breakdown, service counts, hourly volume
GET /api/services             Distinct ServiceName values
GET /health                   {"status":"ok"}
```

---

## Drain3 Tuning

| Symptom | Fix |
|---------|-----|
| Too many clusters (over-split) | Lower `sim_th` (try 0.3). Enable `http_numeric_id` + `ipv4` masking |
| Too few clusters (over-merge) | Raise `sim_th` (try 0.6–0.7). Disable `number` masking |
| Access + error logs merge | Enable `user_agent` masking. Raise `depth` to 6 |
| PID numbers split error clusters | Enable `pid` masking |
| Slow analysis | Reduce `max_logs` query param (default 50,000) |

---

## Development

```bash
# Backend only
cd backend
pip install -r requirements.txt
DORIS_HOST=localhost uvicorn main:app --reload --port 8000

# Frontend only
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start

# Direct Doris SQL
mysql -h 127.0.0.1 -P 9030 -u root otel

# Watch live logs in Doris
mysql -h 127.0.0.1 -P 9030 -u root -e \
  "SELECT Timestamp, SeverityText, ServiceName, LEFT(Body,80) FROM otel.otel_logs ORDER BY Timestamp DESC LIMIT 20;"
```
