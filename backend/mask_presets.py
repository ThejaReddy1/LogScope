"""
mask_presets.py
───────────────
All masking rules are pre-written here. The UI presents them as checkboxes;
the user selects which ones to activate. Drain3 then applies only the active
rules before tokenising each log line for clustering.

Each preset has:
  id          – stable identifier sent between frontend and backend
  label       – human-readable name shown in the UI
  description – one-line explanation shown in UI tooltip
  pattern     – Python regex applied by MaskingInstruction
  token       – the replacement placeholder (e.g. <IP_ADDRESS>)
  examples    – sample values the rule would mask (displayed in UI)
  category    – grouping for the UI (Network, Identity, Web, System, Security)
"""

MASK_PRESETS: list[dict] = [
    # ── System ───────────────────────────────────────────────────────────
    {
        "id":          "timestamp_all",
        "label":       "Any Timestamp",
        "description": "Masks ISO 8601, Common Log Format, Syslog (with days/TZ), and Epoch timestamps",
        "pattern":     r"\b(?:\d{4}[-/.]\d{2}[-/.]\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\d{2}/(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/\d{4}:\d{2}:\d{2}:\d{2}\s[+-]\d{4}|(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[,\s]+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s+[A-Z]{3,5})?|[12]\d{9}(?:\d{3})?)\b",
        "token":       "<TIMESTAMP>",
        "examples":    [
            "2023-10-25T14:30:00Z", 
            "2026/06/12 17:18:02",
            "2026.06.12 17:18:02",
            "Fri Jun 12 17:17:59.101 UTC",
            "10/Oct/2000:13:55:36 -0700", 
            "1698244200"
        ],
        "category":    "System",
        "default":     True,
    },
    {
        "id":          "pid",
        "label":       "Process / Thread ID",
        "description": "Masks PID and TID numbers in error logs",
        "pattern":     r"\b(?:pid|tid|PID|TID)\s+\d+\b|\[pid \d+\]|\b\d+#\d+\b",
        "token":       "<PID>",
        "examples":    ["[pid 4521]", "pid 9981", "1234#5"],
        "category":    "System",
        "default":     True,
    },
    {
        "id":          "file_path",
        "label":       "File System Path",
        "description": "Masks absolute Unix file paths",
        "pattern":     r"(?:/[\w.\-]+){3,}",
        "token":       "<FILE_PATH>",
        "examples":    ["/var/www/html/index.php", "/etc/nginx/conf.d/default.conf"],
        "category":    "System",
        "default":     False,
    },
    {
        "id":          "hex_address",
        "label":       "Hex / Memory Address",
        "description": "Masks hexadecimal pointers, useful for crash logs and segfaults",
        "pattern":     r"\b0x[a-fA-F0-9]+\b",
        "token":       "<HEX_ADDR>",
        "examples":    ["0x7f8a9b00", "0x00000000"],
        "category":    "System",
        "default":     False,
    },
    {
        "id":          "semver",
        "label":       "Semantic Version",
        "description": "Masks software version numbers",
        "pattern":     r"\b(?:v)?\d+\.\d+\.\d+(?:-[a-zA-Z0-9.\-]+)?(?:\+[a-zA-Z0-9.\-]+)?\b",
        "token":       "<VERSION>",
        "examples":    ["v1.24.0", "2.0.1-rc.1"],
        "category":    "System",
        "default":     False,
    },
    {
        "id":          "number",
        "label":       "Generic Numbers",
        "description": "Masks standalone numeric tokens (coarse — use sparingly)",
        "pattern":     r"\b\d{3,}\b",
        "token":       "<NUM>",
        "examples":    ["1024", "50000", "8080"],
        "category":    "System",
        "default":     False,
    },
    {
        "id":          "database_url",
        "label":       "Database Connection URL",
        "description": "Masks DB connection strings which often leak credentials",
        "pattern":     r"(?:postgres|mysql|mongodb(?:\+srv)?|redis)://(?:[^:]+:[^@]+@)?(?:[\w.-]+)(?::\d+)?(?:/[\w.-]+)?",
        "token":       "<DB_URL>",
        "examples":    ["postgres://user:password@localhost:5432/mydb", "mongodb+srv://admin:secret@cluster0.net/test"],
        "category":    "System",
        "default":     True,
    },
    # ── Network ──────────────────────────────────────────────────────────
    {
        "id":          "ipv4",
        "label":       "IPv4 Address",
        "description": "Masks dotted-quad IPv4 addresses (e.g. 203.0.113.1)",
        "pattern":     r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "token":       "<IP_ADDRESS>",
        "examples":    ["203.0.113.1", "10.0.0.42", "192.168.1.100"],
        "category":    "Network",
        "default":     True,
    },
    {
        "id":          "ipv6",
        "label":       "IPv6 Address",
        "description": "Masks full and compressed IPv6 addresses",
        "pattern":     r"(?<![a-zA-Z0-9])(?:[a-fA-F0-9]{1,4}:){1,7}[a-fA-F0-9]{1,4}(?![a-zA-Z0-9])|(?<![a-zA-Z0-9])(?:[a-fA-F0-9]{1,4}:){1,7}:(?![a-zA-Z0-9])|(?<![a-zA-Z0-9])::(?:[a-fA-F0-9]{1,4}:){0,6}[a-fA-F0-9]{1,4}(?![a-zA-Z0-9])",
        "token":       "<IPV6_ADDRESS>",
        "examples":    ["2001:db8::1", "fe80::1%eth0", "::1"],
        "category":    "Network",
        "default":     False,
    },
    {
        "id":          "mac_address",
        "label":       "MAC Address",
        "description": "Masks standard MAC addresses",
        "pattern":     r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b",
        "token":       "<MAC_ADDRESS>",
        "examples":    ["00:1A:2B:3C:4D:5E", "00-1A-2B-3C-4D-5E"],
        "category":    "Network",
        "default":     False,
    },
    {
        "id":          "port",
        "label":       "Port Number",
        "description": "Masks standalone port numbers (1–65535)",
        "pattern":     r"(?<=:)\b([1-9][0-9]{0,4})\b(?!\.\d)",
        "token":       "<PORT>",
        "examples":    [":8080", ":443", ":9030"],
        "category":    "Network",
        "default":     True,
    },
    # ── Identity ─────────────────────────────────────────────────────────
    {
        "id":          "email",
        "label":       "Email Address",
        "description": "Masks email addresses in log bodies",
        "pattern":     r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "token":       "<EMAIL>",
        "examples":    ["user@example.com", "admin@corp.io"],
        "category":    "Identity",
        "default":     False,
    },
    {
        "id":          "uuid",
        "label":       "UUID / GUID",
        "description": "Masks RFC 4122 UUIDs and GUIDs",
        "pattern":     r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "token":       "<UUID>",
        "examples":    ["550e8400-e29b-41d4-a716-446655440000"],
        "category":    "Identity",
        "default":     False,
    },
    {
        "id":          "trace_id",
        "label":       "Trace / Span ID",
        "description": "Masks 32-char trace IDs and 16-char span IDs (hex strings)",
        "pattern":     r"\b[0-9a-fA-F]{32}\b|\b[0-9a-fA-F]{16}\b",
        "token":       "<TRACE_ID>",
        "examples":    ["4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7"],
        "category":    "Identity",
        "default":     False,
    },
    # ── Web ───────────────────────────────────────────────────────────────
    {
        "id":          "http_method",
        "label":       "HTTP Method",
        "description": "Masks standard uppercase HTTP request methods",
        "pattern":     r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|TRACE|CONNECT)\b",
        "token":       "<HTTP_METHOD>",
        "examples":    ["GET", "POST", "DELETE"],
        "category":    "Web",
        "default":     True,
    },
    {
        "id":          "http_numeric_id",
        "label":       "HTTP Path Numeric ID",
        "description": "Masks numeric segments in URL paths (e.g. /orders/9831 → /orders/<ID>)",
        "pattern":     r"(?<=/)\d{2,}(?=[/?#\s\"']|$)",
        "token":       "<ID>",
        "examples":    ["/orders/9831", "/users/42", "/products/1234"],
        "category":    "Web",
        "default":     False,
    },
    {
        "id":          "query_string",
        "label":       "URL Query String",
        "description": "Masks the query string portion of URLs",
        "pattern":     r"\?[^\s\"']+",
        "token":       "?<QUERY>",
        "examples":    ["?token=abc123", "?page=2&limit=50"],
        "category":    "Web",
        "default":     False,
    },
    {
        "id":          "user_agent_all",
        "label":       "Any User-Agent",
        "description": "Masks all known User-Agents (Browsers, Bots, Mobile, and CLI tools)",
        "pattern":     r'(?i)"[^"]*(?:mozilla|chrome|safari|firefox|edg|opera|bot|crawler|spider|slurp|curl|wget|python|go-http|postman|java|mobile|android|iphone|ipad|dalvik|cfnetwork|darwin)[^"]*"',
        "token":       '"<USER_AGENT>"',
        "examples":    [
            '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"', 
            '"curl/8.4.0"'
        ],
        "category":    "Web",
        "default":     True,
    },
    # ── Security ──────────────────────────────────────────────────────────
    {
        "id":          "bearer_token",
        "label":       "Bearer Token",
        "description": "Masks Authorization: Bearer … header values",
        "pattern":     r"(?i)bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*",
        "token":       "Bearer <TOKEN>",
        "examples":    ["Bearer eyJhbGciOiJSUzI1NiIsInR5c…"],
        "category":    "Security",
        "default":     False,
    },
    {
        "id":          "api_key",
        "label":       "API Key / Secret",
        "description": "Masks API keys assigned via equals, colon, or JSON syntax",
        "pattern":     r"(?i)(?:api[_-]?key|token|secret|password)[\s:=]+[\"']?[A-Za-z0-9+/\-_]{16,64}[\"']?",
        "token":       "<API_KEY>",
        "examples":    ["api_key=sk-abc123...", "\"token\": \"ghp_xXxXxX\""],
        "category":    "Security",
        "default":     False,
    },
    {
        "id":          "jwt",
        "label":       "JSON Web Token (JWT)",
        "description": "Masks standard JWTs (Header.Payload.Signature)",
        "pattern":     r"\beyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b",
        "token":       "<JWT>",
        "examples":    ["eyJhbGciOiJIUzI1Ni.eyJzdWI.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"],
        "category":    "Security",
        "default":     False,
    },    
]

# Build a dict for O(1) lookup by id
PRESETS_BY_ID: dict[str, dict] = {p["id"]: p for p in MASK_PRESETS}

DEFAULT_ACTIVE_IDS: list[str] = [p["id"] for p in MASK_PRESETS if p["default"]]
