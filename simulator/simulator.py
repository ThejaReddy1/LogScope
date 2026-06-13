"""
LogScope Simulator
==================
Generates realistic Apache httpd and Nginx access/error logs and ships them
as OTLP LogRecords to the OpenTelemetry Collector via HTTP (port 4318).

Log formats simulated
─────────────────────
  Apache Combined:  %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i"
  Nginx Combined:   $remote_addr - $remote_user [$time_local] "$request"
                    $status $body_bytes_sent "$http_referer" "$http_user_agent"
  Apache Error:     [%a %b %d %H:%M:%S.%f %Y] [%l] [pid %P] %F: %E: %M
  Nginx Error:      %Y/%m/%d %H:%M:%S [%l] %P#%T: *%c %m

Each log is wrapped in an OTLP LogRecord:
  Body             → raw log line string
  SeverityText     → INFO / WARN / ERROR
  SeverityNumber   → 9 (INFO) / 13 (WARN) / 17 (ERROR)
  LogAttributes    → parsed key/value fields (method, status, path, bytes …)
  ResourceAttributes → {service.name, server.type, deployment.environment}
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone

import requests

# ─── Config ──────────────────────────────────────────────────────────────────

OTEL_ENDPOINT = os.environ.get("OTEL_ENDPOINT", "http://otel-collector:4318")
LOGS_ENDPOINT = f"{OTEL_ENDPOINT}/v1/logs"
EMIT_INTERVAL  = float(os.environ.get("EMIT_INTERVAL", "0.4"))   # seconds between batches
BATCH_SIZE     = int(os.environ.get("BATCH_SIZE", "5"))           # records per HTTP call

# ─── Realistic data pools ─────────────────────────────────────────────────────

SERVICES = [
    {"name": "apache-frontend",  "type": "apache", "env": "production"},
    {"name": "nginx-gateway",    "type": "nginx",  "env": "production"},
    {"name": "apache-api",       "type": "apache", "env": "staging"},
    {"name": "nginx-static",     "type": "nginx",  "env": "production"},
]

CLIENT_IPS = [
    "203.0.113.1", "198.51.100.42", "192.0.2.17", "185.220.101.34",
    "104.18.22.55", "172.67.174.160", "151.101.64.81", "13.226.14.22",
    "34.120.177.193", "66.249.90.77", "157.55.39.108", "40.77.167.130",
] + ["10.0.0." + str(i) for i in range(1, 20)]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Safari/605.1",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "curl/8.7.1",
    "python-requests/2.31.0",
    "Googlebot/2.1 (+http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0)",
    "Go-http-client/1.1",
    "aws-sdk-java/1.12.0",
    "Datadog/v1 (go1.21)",
]

PATHS = [
    ("/",                          "GET",  200, 2048),
    ("/index.html",                "GET",  200, 4096),
    ("/api/v1/users",              "GET",  200, 512),
    ("/api/v1/users",              "POST", 201, 256),
    ("/api/v1/orders",             "GET",  200, 8192),
    ("/api/v1/orders",             "POST", 201, 128),
    ("/api/v1/orders/9831",        "GET",  200, 1024),
    ("/api/v1/products",           "GET",  200, 16384),
    ("/api/v1/products/453",       "GET",  200, 2048),
    ("/api/v1/auth/login",         "POST", 200, 256),
    ("/api/v1/auth/logout",        "POST", 204, 0),
    ("/static/css/main.css",       "GET",  200, 32768),
    ("/static/js/bundle.js",       "GET",  200, 524288),
    ("/static/img/logo.png",       "GET",  200, 8192),
    ("/favicon.ico",               "GET",  200, 1150),
    ("/health",                    "GET",  200, 16),
    ("/metrics",                   "GET",  200, 4096),
    ("/robots.txt",                "GET",  200, 64),
    ("/api/v1/nonexistent",        "GET",  404, 128),
    ("/admin/config",              "GET",  403, 256),
    ("/api/v1/users/99999",        "GET",  404, 64),
    ("/.env",                      "GET",  403, 0),
    ("/wp-admin/",                 "GET",  404, 512),
    ("/api/v1/orders",             "DELETE", 405, 128),
    ("/api/v1/crash",              "GET",  500, 512),
    ("/api/v1/slow-query",         "GET",  503, 256),
    ("/api/v1/timeout",            "GET",  504, 128),
]

REFERERS = [
    "-", "-", "-", "-",   # most requests have no referer
    "https://example.com/",
    "https://google.com/search?q=api+docs",
    "https://app.example.com/dashboard",
    "https://docs.example.com/quickstart",
]

APACHE_ERROR_MESSAGES = [
    ("error",   "AH00124: Request exceeded the limit of 10 internal redirects due to probable configuration error"),
    ("error",   "AH01630: client denied by server configuration: /var/www/html/admin"),
    ("error",   "AH00035: access to /.env denied (filesystem path '/var/www/html/.env')"),
    ("error",   "AH00819: PROPFIND of /api not supported"),
    ("warn",    "AH00128: File does not exist: /var/www/html/favicon.ico"),
    ("warn",    "AH00126: Invalid URI in request OPTIONS * HTTP/1.0"),
    ("notice",  "AH00094: Command line: '/usr/sbin/apache2 -D FOREGROUND'"),
    ("info",    "AH00489: Apache/2.4.57 configured -- resuming normal operations"),
    ("error",   "PHP Fatal error:  Uncaught Error: Call to undefined function mysql_connect() in /var/www/html/db.php:12"),
    ("error",   "SSL Library Error: -8179 Certificate has expired"),
]

NGINX_ERROR_MESSAGES = [
    ("error",   "connect() to unix:/run/php/php8.2-fpm.sock failed (11: Resource temporarily unavailable)"),
    ("error",   "upstream timed out (110: Connection timed out) while reading response header from upstream"),
    ("warn",    "upstream server temporarily disabled while reading response header from upstream"),
    ("error",   "no live upstreams while connecting to upstream, client: 203.0.113.1, server: example.com"),
    ("error",   "recv() failed (104: Connection reset by peer)"),
    ("warn",    "client exceeded rate limit: requests per second"),
    ("error",   "SSL_read() failed (SSL: error:1408F10B:SSL routines) while reading client request headers"),
    ("info",    "upstream keepalive connections pool capacity hit, closing oldest connection"),
    ("error",   "open() \"/etc/nginx/html/api/v1/crash\" failed (2: No such file or directory)"),
    ("warn",    "buffering data to a temporary file, client: 198.51.100.42, upstream: http://backend"),
]

# ─── Severity mapping ─────────────────────────────────────────────────────────

SEVERITY_MAP = {
    "trace":   (1,  "TRACE"),
    "debug":   (5,  "DEBUG"),
    "info":    (9,  "INFO"),
    "notice":  (10, "INFO"),
    "warn":    (13, "WARN"),
    "warning": (13, "WARN"),
    "error":   (17, "ERROR"),
    "crit":    (21, "ERROR"),
    "fatal":   (21, "ERROR"),
}

STATUS_SEVERITY = {
    2: (9,  "INFO"),
    3: (9,  "INFO"),
    4: (13, "WARN"),
    5: (17, "ERROR"),
}

# ─── Log line generators ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S +0000")

def _ts_nano() -> int:
    return int(time.time() * 1e9)

def _rand_bytes(nominal: int) -> int:
    return max(0, nominal + random.randint(-nominal // 4, nominal // 4))

def _rand_latency_ms() -> int:
    # Log-normal distribution: most fast, occasional slow
    return max(1, int(random.lognormvariate(4.5, 1.2)))

def apache_access_log(svc: dict) -> dict:
    ip   = random.choice(CLIENT_IPS)
    path, method, status, nominal_bytes = random.choice(PATHS)
    b    = _rand_bytes(nominal_bytes) if status < 400 else random.randint(100, 512)
    ua   = random.choice(USER_AGENTS)
    ref  = random.choice(REFERERS)
    ms   = _rand_latency_ms()
    ts   = _now_iso()
    body = (f'{ip} - - [{ts}] "{method} {path} HTTP/1.1" '
            f'{status} {b} "{ref}" "{ua}"')
    sev_num, sev_txt = STATUS_SEVERITY.get(status // 100, (9, "INFO"))
    attrs = {
        "http.method":         method,
        "http.target":         path,
        "http.status_code":    status,
        "http.response_size":  b,
        "http.user_agent":     ua,
        "http.referer":        ref,
        "net.peer.ip":         ip,
        "http.latency_ms":     ms,
        "log.type":            "access",
    }
    return _make_record(body, sev_num, sev_txt, svc, attrs)

def nginx_access_log(svc: dict) -> dict:
    ip   = random.choice(CLIENT_IPS)
    path, method, status, nominal_bytes = random.choice(PATHS)
    b    = _rand_bytes(nominal_bytes) if status < 400 else random.randint(100, 512)
    ua   = random.choice(USER_AGENTS)
    ref  = random.choice(REFERERS)
    ts   = _now_iso()
    body = (f'{ip} - - [{ts}] "{method} {path} HTTP/1.1" '
            f'{status} {b} "{ref}" "{ua}"')
    sev_num, sev_txt = STATUS_SEVERITY.get(status // 100, (9, "INFO"))
    attrs = {
        "http.method":         method,
        "http.target":         path,
        "http.status_code":    status,
        "http.response_size":  b,
        "http.user_agent":     ua,
        "http.referer":        ref,
        "net.peer.ip":         ip,
        "log.type":            "access",
    }
    return _make_record(body, sev_num, sev_txt, svc, attrs)

def apache_error_log(svc: dict) -> dict:
    level, msg = random.choice(APACHE_ERROR_MESSAGES)
    now  = datetime.now(timezone.utc)
    ts   = now.strftime("%a %b %d %H:%M:%S.%f")[:-3]
    body = f"[{ts} UTC] [{level}] [pid {random.randint(1000,9999)}] {msg}"
    sev_num, sev_txt = SEVERITY_MAP.get(level, (9, "INFO"))
    attrs = {
        "log.type":   "error",
        "error.type": "apache_error",
    }
    return _make_record(body, sev_num, sev_txt, svc, attrs)

def nginx_error_log(svc: dict) -> dict:
    level, msg = random.choice(NGINX_ERROR_MESSAGES)
    now  = datetime.now(timezone.utc)
    ts   = now.strftime("%Y/%m/%d %H:%M:%S")
    pid  = random.randint(1000, 9999)
    tid  = random.randint(1, 32)
    cid  = random.randint(1000, 99999)
    body = f"{ts} [{level}] {pid}#{tid}: *{cid} {msg}"
    sev_num, sev_txt = SEVERITY_MAP.get(level, (9, "INFO"))
    attrs = {
        "log.type":   "error",
        "error.type": "nginx_error",
    }
    return _make_record(body, sev_num, sev_txt, svc, attrs)

# ─── OTLP record builder ──────────────────────────────────────────────────────

def _make_record(
    body: str,
    severity_number: int,
    severity_text: str,
    svc: dict,
    log_attrs: dict,
) -> dict:
    nano = _ts_nano()
    return {
        "timeUnixNano":         str(nano),
        "observedTimeUnixNano": str(nano),
        "severityNumber":       severity_number,
        "severityText":         severity_text,
        "body":                 {"stringValue": body},
        "attributes": [
            {"key": k, "value": {"stringValue": str(v)}}
            for k, v in log_attrs.items()
        ],
    }

# ─── Dispatch ─────────────────────────────────────────────────────────────────

GENERATORS = {
    "apache": [apache_access_log, apache_access_log, apache_access_log, apache_error_log],
    "nginx":  [nginx_access_log,  nginx_access_log,  nginx_access_log,  nginx_error_log],
}

def build_otlp_payload(records_by_service: dict[str, list]) -> dict:
    resource_logs = []
    for svc, records in records_by_service.items():
        svc_info = next(s for s in SERVICES if s["name"] == svc)
        resource_logs.append({
            "resource": {
                "attributes": [
                    {"key": "service.name",              "value": {"stringValue": svc_info["name"]}},
                    {"key": "service.instance.id",       "value": {"stringValue": svc_info["name"] + "-01"}},
                    {"key": "server.type",               "value": {"stringValue": svc_info["type"]}},
                    {"key": "deployment.environment",    "value": {"stringValue": svc_info["env"]}},
                    {"key": "telemetry.sdk.name",        "value": {"stringValue": "logscope-simulator"}},
                ]
            },
            "scopeLogs": [{
                "scope": {"name": "logscope.simulator", "version": "1.0.0"},
                "logRecords": records,
            }]
        })
    return {"resourceLogs": resource_logs}


def emit_batch(session: requests.Session) -> int:
    records_by_service: dict[str, list] = {s["name"]: [] for s in SERVICES}
    for _ in range(BATCH_SIZE):
        svc = random.choice(SERVICES)
        gen = random.choice(GENERATORS[svc["type"]])
        rec = gen(svc)
        records_by_service[svc["name"]].append(rec)

    payload = build_otlp_payload({k: v for k, v in records_by_service.items() if v})
    try:
        resp = session.post(
            LOGS_ENDPOINT,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return BATCH_SIZE
    except Exception as exc:
        print(f"[simulator] emit error: {exc}")
        return 0


def main():
    print(f"[simulator] LogScope simulator starting")
    print(f"[simulator] Target: {LOGS_ENDPOINT}")
    print(f"[simulator] Batch size: {BATCH_SIZE}  Interval: {EMIT_INTERVAL}s")

    # Wait for OTel Collector
    session = requests.Session()
    for attempt in range(40):
        try:
            r = session.get(f"{OTEL_ENDPOINT.replace('4318','13133')}/", timeout=3)
            print(f"[simulator] OTel Collector ready.")
            break
        except Exception:
            print(f"[simulator] Waiting for collector... attempt {attempt+1}/40")
            time.sleep(5)

    total = 0
    while True:
        sent = emit_batch(session)
        total += sent
        print(f"[simulator] Sent batch of {sent} records (total={total})")
        time.sleep(EMIT_INTERVAL)


if __name__ == "__main__":
    main()
