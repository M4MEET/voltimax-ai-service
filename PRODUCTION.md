# Production Maintenance Guide

> **Last updated:** 2026-05-05
>
> This document covers the full two-server architecture, deployment, configuration, monitoring, and troubleshooting for the AI Chat system.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Server B Setup (AI Service)](#server-b-setup-ai-service-at-chat<SHOP_DOMAIN>)
- [Server A Setup (Shopware Plugin)](#server-a-setup-shopware-plugin-at-shop-domain)
- [Credentials & Tokens](#credentials--tokens)
- [Monitoring & Debugging](#monitoring--debugging)
- [Backup & Recovery](#backup--recovery)
- [Deployment Workflow](#deployment-workflow)
- [Important URLs](#important-urls)
- [Quick Reference Commands](#quick-reference-commands)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              INTERNET                                         │
└──────────────┬───────────────────────────────────────────┬───────────────────┘
               │                                           │
               ▼                                           ▼
┌──────────────────────────────┐       ┌──────────────────────────────────────┐
│   SERVER A (<SHOP_DOMAIN>)     │       │   SERVER B (chat.<SHOP_DOMAIN>)        │
│   Plesk / Cloud Provider     │       │   Cloud VPS                             │
│                              │       │                                      │
│  ┌────────────────────────┐  │       │  ┌─────────────────────────────────┐ │
│  │  Shopware 6.6.10       │  │       │  │  Nginx (reverse proxy)          │ │
│  │  + Chat Plugin         │  │       │  │  - /        → :8000 (FastAPI)   │ │
│  │                        │  │       │  │  - /ws      → :8000 (WebSocket) │ │
│  │  - Widget JS           │  │       │  │  - /n8n/    → :5678 (N8N)       │ │
│  │  - JWT issuer          │  │       │  │  - /db/     → :8081 (MongoExpr) │ │
│  │  - Store API           │  │       │  │  - /dashboard → :8000           │ │
│  │  - Dev mode gate       │  │       │  └─────────────────────────────────┘ │
│  └────────────────────────┘  │       │                                      │
│                              │       │  ┌─────────────────────────────────┐ │
│  DB: MySQL (Shopware)        │       │  │  Docker Compose Stack           │ │
│                              │       │  │                                 │ │
└──────────────────────────────┘       │  │  ┌─────────────┐ ┌───────────┐ │ │
                                       │  │  │ app-service │ │   n8n     │ │ │
         Communication:                │  │  │ (FastAPI)   │ │ workflows │ │ │
                                       │  │  │ :8000       │ │ :5678     │ │ │
  1. Widget JS → WebSocket → Server B  │  │  └─────────────┘ └───────────┘ │ │
  2. Server B → REST → Server A        │  │                                 │ │
     (Admin API for orders/customers)  │  │  ┌─────────────┐ ┌───────────┐ │ │
  3. Server A → REST → Server B        │  │  │  MongoDB    │ │  Mongo    │ │ │
     (JWT token endpoint, config)      │  │  │  atlas-local│ │  Express  │ │ │
  4. Server B → Webhook → N8N          │  │  │  :27017     │ │  :8081    │ │ │
     (escalation, tickets)             │  │  └─────────────┘ └───────────┘ │ │
                                       │  └─────────────────────────────────┘ │
                                       └──────────────────────────────────────┘
```

### What Each Server Does

| Server | Role | Key Responsibilities |
|--------|------|---------------------|
| **A** (<SHOP_DOMAIN>) | Shopware storefront | Serves the shop, renders the chat widget, issues JWT tokens, provides Store API + Admin API endpoints for order/product/customer data |
| **B** (chat.<SHOP_DOMAIN>) | AI service backend | Handles WebSocket chat sessions, runs LLM inference (Anthropic/OpenAI), performs RAG with knowledge base, manages escalation to Zendesk, runs N8N automations, stores conversation history in MongoDB |

### Communication Flow

1. **Customer opens widget** → Browser loads JS from Server A
2. **Widget connects** → WebSocket to `wss://chat.<SHOP_DOMAIN>/ws/{session_id}?token={jwt}`
3. **AI needs shop data** → Server B calls Server A's Admin API (orders, customers) using OAuth2 client credentials
4. **Escalation triggered** → Server B fires webhook to N8N → N8N creates Zendesk ticket / sends email

---

## Server B Setup (AI Service at chat.<SHOP_DOMAIN>)

### Prerequisites

- Linux VPS (minimum 4GB RAM recommended)
- Docker Engine 24+ and Docker Compose v2
- Nginx installed on host (for reverse proxy)
- Domain `chat.<SHOP_DOMAIN>` pointed to server IP
- SSL certificate (Let's Encrypt via certbot)

### Installation

```bash
# 1. Clone the repository
git clone git@github.com:<GITHUB_ORG>/<AI_SERVICE_REPO>.git <AI_SERVICE_ROOT>
cd <AI_SERVICE_ROOT>

# 2. Create environment file
cp .env.example .env
nano .env    # Fill in all API keys

# 3. Create configuration file
cp config.example.yaml config.yaml
nano config.yaml    # Fill in Shopware credentials, JWT secret, etc.

# 4. Create required directories
mkdir -p data/n8n knowledge_files static/forms

# 5. Start the stack
docker compose -f docker-compose.prod.yml up -d

# 6. Verify
curl http://localhost:8000/health
```

### Docker Commands

#### Start / Stop / Rebuild

| Action | Command |
|--------|---------|
| Start all services | `docker compose -f docker-compose.prod.yml up -d` |
| Stop all services | `docker compose -f docker-compose.prod.yml down` |
| Restart a single service | `docker compose -f docker-compose.prod.yml restart app` |
| Rebuild after code change | `docker compose -f docker-compose.prod.yml up -d --build app` |
| Rebuild everything | `docker compose -f docker-compose.prod.yml up -d --build` |
| View running containers | `docker compose -f docker-compose.prod.yml ps` |

#### Logs

| Service | Command |
|---------|---------|
| AI service | `docker compose -f docker-compose.prod.yml logs -f app` |
| MongoDB | `docker compose -f docker-compose.prod.yml logs -f mongo` |
| N8N | `docker compose -f docker-compose.prod.yml logs -f n8n` |
| Mongo Express | `docker compose -f docker-compose.prod.yml logs -f mongo-express` |
| All services (last 100 lines) | `docker compose -f docker-compose.prod.yml logs --tail=100` |

#### docker-compose.prod.yml vs docker-compose.yml

| File | Use Case |
|------|----------|
| `docker-compose.prod.yml` | **Production.** All ports bound to `127.0.0.1` (except FastAPI on `0.0.0.0:8000`). Uses `restart: unless-stopped`. |
| `docker-compose.yml` | **Development.** Ports exposed on all interfaces, may include LangGraph Studio or additional dev tools. |

Always use `-f docker-compose.prod.yml` on the production server.

### Environment Variables (.env)

| Variable | Description | How to Get |
|----------|-------------|-----------|
| `MONGO_URI` | MongoDB connection string | Default: `mongodb://localhost:27017/<DB_NAME>` (Docker internal: `mongodb://mongo:27017`) |
| `CONFIG_PATH` | Path to config.yaml inside container | Default: `config.yaml` (mounted at `/app/config.yaml`) |
| `LANGCHAIN_API_KEY` | LangSmith API key for tracing | [smith.langchain.com/settings](https://smith.langchain.com/settings) |
| `LANGCHAIN_TRACING_V2` | Enable LangChain tracing | Set to `true` |
| `LANGSMITH_TRACING` | Enable LangSmith tracing | Set to `true` |
| `LANGCHAIN_PROJECT` | LangSmith project name | e.g., `<LANGSMITH_PROJECT>` (production) or `<LANGSMITH_PROJECT_DEV>` |
| `LANGCHAIN_ENDPOINT` | LangSmith API endpoint | `https://eu.api.smith.langchain.com` (EU region) |
| `LANGSMITH_API_KEY` | Same as LANGCHAIN_API_KEY | Same key, duplicated for compatibility |
| `LANGSMITH_ENDPOINT` | Same as LANGCHAIN_ENDPOINT | Same endpoint |
| `LANGSMITH_PROJECT` | Same as LANGCHAIN_PROJECT | Same project name |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI API key (embeddings + fallback) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `DASHBOARD_KEY` | API key for dashboard & N8N auth | Generate with `openssl rand -hex 16` |
| `MONGO_EXPRESS_PASSWORD` | Password for Mongo Express web UI | Generate with `openssl rand -hex 16` |

> **Note:** `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `.env` are used by LangGraph Studio and direct imports. The same keys should also be placed in `config.yaml` under `llm_providers`.

### Configuration (config.yaml)

#### JWT

```yaml
jwt:
  secret: "<64-char-hex-string>"   # MUST match Server A plugin config
  algorithm: "HS256"
```

The JWT secret is the critical shared credential between Server A and Server B. If they don't match, every chat session will fail with auth errors.

#### Shopware Connection

```yaml
shopware:
  server_a_url: "https://<SHOP_DOMAIN>"
  api_key: "<integration-access-key>"        # From Shopware Admin → Integrations
  integration_secret: "<integration-secret>"  # From same Integration
  store_api_key: "<sw-access-key>"           # Sales Channel API access key
  timeout: 10
  verify_ssl: true
```

- `api_key` + `integration_secret`: Used together for OAuth2 `client_credentials` grant to get Admin API bearer tokens
- `store_api_key`: The `sw-access-key` header value for Store API calls (read-only, no OAuth needed)

#### Escalation (Zendesk)

```yaml
escalation:
  ai_detection_enabled: true
  frustration_threshold: 0.75
  zendesk:
    subdomain: "<ZENDESK_SUBDOMAIN>"            # → <ZENDESK_SUBDOMAIN>.zendesk.com
    email: "agent@<SHOP_DOMAIN>"       # Zendesk agent email
    api_token: "<zendesk-api-token>" # Zendesk Admin → API Tokens
  support_email: "support@<SHOP_DOMAIN>"
```

#### CORS Origins

```yaml
server:
  cors_origins:
    - "https://<SHOP_DOMAIN>"
    - "https://www.<SHOP_DOMAIN>"
    - "https://chat.<SHOP_DOMAIN>"
```

Every domain that loads the chat widget must be listed here. Missing entries cause CORS errors in the browser console.

#### LLM Providers

```yaml
llm_providers:
  openai:
    api_key: "<openai-key>"
    default_model: "gpt-4.1"
  anthropic:
    api_key: "<anthropic-key>"
    default_model: "claude-haiku-4-5-20251001"
  anthropic-sonnet:
    api_key: "<anthropic-key>"           # Same key, different model
    default_model: "claude-sonnet-4-6"   # Used for complex queries
```

#### Topic Routing

```yaml
topic_routing:
  order_status: "anthropic"
  order_issue: "anthropic"
  returns: "anthropic"
  product_help: "anthropic"
  general: "anthropic"
  fallback: "anthropic"
```

Maps each conversation topic to an LLM provider key. Change to `"openai"` or `"anthropic-sonnet"` to route specific topics to different models.

#### Knowledge Base

```yaml
knowledge_base:
  embedding_provider: "openai"
  embedding_model: "text-embedding-3-large"   # 3072 dimensions
  chunk_size: 512
  chunk_overlap: 100
```

#### Rate Limiting

```yaml
rate_limiting:
  max_messages_per_session: 50
  max_messages_per_minute: 10
  daily_token_cap: 1000000
  abuse_detection: true
```

### Services

#### MongoDB (atlas-local)

- **Image:** `mongodb/mongodb-atlas-local:latest`
- **Why atlas-local:** Provides Atlas Search (vector search) capabilities locally without Atlas cloud
- **Privileged mode:** Required for keyfile permissions on Docker volumes
- **Ports:** `127.0.0.1:27017` (host-only, not exposed to internet)
- **Volumes:** `mongodb_data` (Docker-managed), `mongodb_config` (Docker-managed)
- **Health check:** Pings every 10s, waits up to 60s on start

#### N8N

- **Image:** `n8nio/n8n`
- **Accessible at:** `https://chat.<SHOP_DOMAIN>/n8n/`
- **Key environment:**
  - `N8N_PATH=/n8n/` — serves under subpath
  - `N8N_EDITOR_BASE_URL=https://chat.<SHOP_DOMAIN>/n8n/` — correct asset URLs
  - `WEBHOOK_URL=https://chat.<SHOP_DOMAIN>/n8n/` — webhook callbacks
  - `AI_SERVICE_URL=http://app:8000` — internal Docker network call
  - `AI_API_KEY=${DASHBOARD_KEY}` — auth for AI service
- **Volumes:** `./data/n8n` (persistent data), `./n8n/workflows` (workflow JSON files)
- **Workflows:** Zendesk Ticket, Escalation Alert, Knowledge Ingestion, Weekly Report

#### Mongo Express

- **Image:** `mongo-express:latest`
- **Accessible at:** `https://chat.<SHOP_DOMAIN>/db/`
- **Auth:** Basic auth with `admin` / `${MONGO_EXPRESS_PASSWORD}`
- **Base URL config:** `ME_CONFIG_SITE_BASEURL=/db`

#### Dashboard

- **Part of the the FastAPI app** (not a separate container)
- **Accessible at:** `https://chat.<SHOP_DOMAIN>/dashboard`
- **Auth:** `DASHBOARD_KEY` header or configured `shopware.api_key`

### Nginx Configuration

Nginx is configured as a reverse proxy on the host. Key routing rules:

| Path | Proxied to | Notes |
|------|-----------|-------|
| `/` | `:8000` (FastAPI) | Main API and dashboard |
| `/ws/` | `:8000` (WebSocket) | Chat WebSocket with upgrade headers, 24h timeout |
| `/n8n/` | `:5678` (N8N) | Subpath with rewrite, requires `N8N_PATH=/n8n/` |
| `/db/` | `:8081` (Mongo Express) | Requires `ME_CONFIG_SITE_BASEURL=/db` |

SSL is managed via Let's Encrypt (certbot). Renew with `certbot renew --nginx`.

---

## Server A Setup (Shopware Plugin at <SHOP_DOMAIN>)

### Plugin Installation

```bash
# Navigate to Shopware custom plugins directory
cd /var/www/<SHOP_DOMAIN>/src/custom/plugins/

# Option 1: Git clone
git clone git@github.com:<GITHUB_ORG>/<PLUGIN_REPO>.git

# Option 2: Upload zip via Shopware Admin → Extensions → Upload

# Install and activate
cd /var/www/<SHOP_DOMAIN>/
bin/console plugin:refresh
bin/console plugin:install <PLUGIN_NAME>
bin/console plugin:activate <PLUGIN_NAME>
bin/console theme:compile
bin/console cache:clear
```

### Plugin Configuration

Configure in Shopware Admin → Extensions → My Extensions → <PLUGIN_NAME> → Config.

#### Card 1: General

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `pluginEnabled` | Boolean | `false` | Master switch — enables/disables the chat widget on storefront |
| `widgetPosition` | Select | `bottom-right` | Widget bubble position: `bottom-right` or `bottom-left` |
| `salesChannelId` | Entity select | — | Sales channel whose CMS pages are synced to the knowledge base |

#### Card 2: AI Server Connection

| Setting | Type | Description |
|---------|------|-------------|
| `serverBUrl` | URL | Base URL of Server B (e.g., `https://chat.<SHOP_DOMAIN>`) |
| `sharedApiKey` | Password | Shared API key for Server A ↔ Server B auth |
| `jwtSecret` | Password | **Must match** `jwt.secret` in Server B's `config.yaml` |
| `jwtTtlMinutes` | Integer (default: 30) | How long JWT tokens are valid before refresh |

#### Card 3: Appearance

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `primaryColor` | Color | `#4338CA` | Gradient start — header, bubble, user messages |
| `secondaryColor` | Color | `#D4A04A` | Gradient end — header, bubble, avatar ring |
| `logoMediaId` | Media | — | Custom avatar/logo for the assistant |
| `widgetTitle` | Text | `Chat Support` | Title shown in widget header |
| `welcomeMessage` | Textarea | `Hallo! Wie kann ich dir helfen?` | First message shown on open |
| `themeMode` | Select | `light` | `light`, `dark`, or `auto` (follows system) |
| `customCss` | Textarea | — | Additional CSS injected into widget shadow DOM |

#### Card 4: Privacy

| Setting | Type | Description |
|---------|------|-------------|
| `privacyPolicyUrl` | URL | Link shown in consent dialog |
| `contactFormUrl` | URL | Fallback redirect when user requests human support |

#### Card 5: API Scope

Boolean toggles that control which Shopware data the AI can access:

| Setting | Default | Controls |
|---------|---------|----------|
| `scopeOrders` | `true` | Order lookup, status, tracking |
| `scopeProducts` | `true` | Product search, details, stock |
| `scopeCustomers` | `true` | Customer profile, address |
| `scopeReturns` | `true` | Return requests, status |
| `scopeCms` | `true` | CMS page content for RAG |
| `scopeB2bQuotes` | `false` | B2B quote management |

#### Card 6: Rate Limiting

| Setting | Default | Description |
|---------|---------|-------------|
| `rateLimitPerMinute` | `30` | Max chat requests per minute per session |
| `rateLimitVerifyPerMinute` | `5` | Max email verification requests per minute |

#### Card 7: Development Mode

| Setting | Default | Description |
|---------|---------|-------------|
| `devModeEnabled` | `false` | When `true`, widget only visible to allowed IPs |
| `devModeAllowedIps` | — | Comma-separated list of IPs that can see the widget |

### Dev Mode

Development mode restricts widget visibility to specific IP addresses. This allows testing on the live shop without customers seeing the widget.

**How it works:**

1. Plugin checks `devModeEnabled` flag
2. If enabled, resolves client IP from (in priority order):
   - `CF-Connecting-IP` header (Cloudflare)
   - `X-Forwarded-For` header (first IP)
   - Direct `clientIp` from PHP
3. Compares against `devModeAllowedIps` list
4. Widget `<div>` is only rendered if IP matches

**Finding your IP:**

```bash
# IPv4
curl -4 ifconfig.me

# IPv6
curl -6 ifconfig.me
```

> **Cloudflare note:** If the site uses Cloudflare, the relevant header is `CF-Connecting-IP`. Your IP as seen by the server may differ from `ifconfig.me` if Cloudflare is not passing the correct header. Test by temporarily adding both your IPv4 and IPv6 addresses.

### Storefront Build

After any plugin changes that affect templates or JS:

```bash
cd /var/www/<SHOP_DOMAIN>/
bin/console theme:compile
bin/console cache:clear
```

For production with asset optimization:

```bash
bin/console theme:compile --active-only
bin/console cache:clear
```

### Database

The plugin creates one custom table:

**`<PLUGIN_PREFIX>_consent_log`** — Records user consent for data processing before chat sessions.

```bash
# Connect to Shopware MySQL
mysql -u shopware -p shopware_db

# Check table exists
SHOW TABLES LIKE '<PLUGIN_PREFIX>%';

# View recent consents
SELECT * FROM <PLUGIN_PREFIX>_consent_log ORDER BY created_at DESC LIMIT 10;

# Count consents by day
SELECT DATE(created_at) as day, COUNT(*) as consents
FROM <PLUGIN_PREFIX>_consent_log
GROUP BY day ORDER BY day DESC LIMIT 7;
```

---

## Credentials & Tokens

### How to Generate

```bash
# JWT Secret (64 characters hex = 32 bytes)
openssl rand -hex 32

# Dashboard Key (32 characters hex = 16 bytes)
openssl rand -hex 16

# Shared API Key (48 characters hex = 24 bytes)
openssl rand -hex 24

# Mongo Express Password
openssl rand -hex 16
```

### Where Each Credential Goes

| Credential | Server A (Shopware Plugin Config) | Server B (config.yaml / .env) |
|-----------|-----------------------------------|-------------------------------|
| **JWT Secret** | `jwtSecret` in plugin config | `jwt.secret` in config.yaml |
| **Shared API Key** | `sharedApiKey` in plugin config | `shopware.api_key` in config.yaml |
| **Integration Access Key** | Created in Admin → Integrations | `shopware.api_key` in config.yaml |
| **Integration Secret** | Created in Admin → Integrations | `shopware.integration_secret` in config.yaml |
| **Store API Key** | Found in Sales Channel settings | `shopware.store_api_key` in config.yaml |
| **Dashboard Key** | Not needed | `DASHBOARD_KEY` in .env |
| **Mongo Express Password** | Not needed | `MONGO_EXPRESS_PASSWORD` in .env |
| **Anthropic API Key** | Not needed | `ANTHROPIC_API_KEY` in .env + `llm_providers.anthropic.api_key` in config.yaml |
| **OpenAI API Key** | Not needed | `OPENAI_API_KEY` in .env + `llm_providers.openai.api_key` in config.yaml |
| **LangSmith API Key** | Not needed | `LANGCHAIN_API_KEY` / `LANGSMITH_API_KEY` in .env |
| **Zendesk API Token** | Not needed | `escalation.zendesk.api_token` in config.yaml |

### Shopware Integration

Server B needs Admin API access to query orders, customers, and products. This requires a Shopware **Integration** (machine-to-machine credential).

**How to create:**

1. Shopware Admin → Settings → System → **Integrations**
2. Click **Add integration**
3. Name: `<INTEGRATION_NAME>`
4. Check **Administrator** (or assign specific roles for least privilege)
5. Save
6. Copy the **Access key ID** → this is `shopware.api_key` in config.yaml
7. Copy the **Secret access key** → this is `shopware.integration_secret` in config.yaml

**How it's used:**

Server B sends a POST to `https://<SHOP_DOMAIN>/api/oauth/token`:
```json
{
  "grant_type": "client_credentials",
  "client_id": "<api_key>",
  "client_secret": "<integration_secret>"
}
```
This returns a bearer token used for subsequent Admin API calls.

---

## Monitoring & Debugging

### Health Check

```bash
# From Server B (local)
curl http://localhost:8000/health

# From anywhere (through Nginx)
curl https://chat.<SHOP_DOMAIN>/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "<SERVICE_NAME>",
  "version": "1.0.0",
  "mongodb": "connected",
  "semantic_cache": { "hits": 142, "misses": 891, "size": 312 }
}
```

If `mongodb` shows `"disconnected"`, the MongoDB container is down or unhealthy.

### Logs

```bash
# Server B — Docker services
docker compose -f docker-compose.prod.yml logs -f app    # AI service
docker compose -f docker-compose.prod.yml logs -f mongo           # MongoDB
docker compose -f docker-compose.prod.yml logs -f n8n             # N8N workflows
docker compose -f docker-compose.prod.yml logs -f mongo-express   # Mongo Express

# Server B — Nginx
tail -f /var/log/nginx/chat.<SHOP_DOMAIN>-access.log
tail -f /var/log/nginx/chat.<SHOP_DOMAIN>-error.log

# Server A — Shopware
tail -f /var/www/<SHOP_DOMAIN>/var/log/prod-$(date +%Y-%m-%d).log
```

### LangSmith

- **Dashboard:** [https://eu.smith.langchain.com](https://eu.smith.langchain.com)
- **Production project:** `<LANGSMITH_PROJECT>`
- **Development project:** `<LANGSMITH_PROJECT_DEV>`

LangSmith traces every LLM call, including:
- Input/output tokens
- Latency
- Chain of thought
- Tool calls (Shopware API, RAG retrieval)
- Error traces

### Common Issues

#### MongoDB keyfile permission error

**Symptom:** MongoDB container crashes on start with `keyfile permission` error.

**Cause:** `mongodb/mongodb-atlas-local` requires specific file permissions on internal keyfiles, which fail with bind mounts.

**Fix:** The `docker-compose.prod.yml` uses `privileged: true` and Docker-managed volumes (not bind mounts) to avoid this. If you changed to bind mounts, revert to Docker volumes:

```yaml
volumes:
  - mongodb_data:/data/db       # Docker volume, NOT ./data/mongo
  - mongodb_config:/data/configdb
```

#### OpenAI quota exceeded (429 error)

**Symptom:** Embedding or chat responses fail with `429 Rate limit exceeded`.

**Fix:**
1. Check usage at [platform.openai.com/usage](https://platform.openai.com/usage)
2. Increase spending limit or wait for reset
3. Temporary: Switch `knowledge_base.embedding_provider` to `anthropic` in config.yaml (requires re-embedding)

#### JWT token expired (auth error loop)

**Symptom:** Widget connects but immediately disconnects. Browser console shows 401 errors in a loop.

**Causes:**
1. `jwtTtlMinutes` too low (default 30 min is usually fine)
2. Clock skew between Server A and Server B
3. JWT secrets don't match between servers

**Fix:**
1. Verify secrets match: compare plugin config `jwtSecret` with `config.yaml` `jwt.secret`
2. Check server clocks: `date` on both machines — should be within 1 minute
3. If clock skew: `timedatectl set-ntp true` or install `chrony`

#### CORS errors

**Symptom:** Browser console shows `Access-Control-Allow-Origin` errors.

**Fix:** Add the missing domain to `config.yaml`:
```yaml
server:
  cors_origins:
    - "https://<SHOP_DOMAIN>"
    - "https://www.<SHOP_DOMAIN>"      # Don't forget www!
    - "https://staging.<SHOP_DOMAIN>"  # Add staging if needed
```
Then restart the AI service:
```bash
docker compose -f docker-compose.prod.yml restart app
```

#### N8N blank page

**Symptom:** Navigating to `/n8n/` shows a blank white page or 404s on assets.

**Cause:** N8N subpath configuration mismatch.

**Fix:** Ensure all three N8N subpath variables are consistent:
```yaml
- N8N_PATH=/n8n/
- N8N_EDITOR_BASE_URL=https://chat.<SHOP_DOMAIN>/n8n/
- WEBHOOK_URL=https://chat.<SHOP_DOMAIN>/n8n/
```
And the Nginx location block uses trailing slash rewrite:
```nginx
location /n8n/ {
    proxy_pass http://127.0.0.1:5678/;
    rewrite ^/n8n/(.*) /$1 break;
}
```

#### Cloudflare IP mismatch (dev mode not working)

**Symptom:** Dev mode is enabled with your IP, but widget doesn't appear.

**Cause:** Cloudflare proxies requests, so the server sees Cloudflare's IP, not yours.

**Fix:** The plugin checks `CF-Connecting-IP` header first. Ensure:
1. Cloudflare is sending this header (it does by default when proxied)
2. Your real IP (from `curl ifconfig.me`) is in `devModeAllowedIps`
3. Add both IPv4 AND IPv6 addresses if your ISP uses both

---

## Backup & Recovery

### What's Backed Up Where

| Data | Location | Type | Critical? |
|------|----------|------|-----------|
| MongoDB (conversations, KB embeddings) | Docker volume `mongodb_data` | Docker volume | Yes |
| N8N workflows & credentials | `./data/n8n/` | Bind mount | Yes |
| Configuration | `config.yaml`, `.env` | Files (NOT in git) | Critical |
| Knowledge files | `./knowledge_files/` | Bind mount | Yes |
| Form definitions | `./static/forms/` | Bind mount | Moderate |
| Application code | Git repository | Git | Recoverable |

### How to Backup MongoDB

```bash
cd <AI_SERVICE_ROOT>

# Create backup directory
mkdir -p backup

# Backup MongoDB data volume to tar.gz
docker run --rm \
  -v <PROJECT>_mongodb_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/mongo-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .

# Backup N8N data
tar czf backup/n8n-backup-$(date +%Y%m%d-%H%M%S).tar.gz data/n8n/

# Backup config files
cp config.yaml backup/config.yaml.bak
cp .env backup/.env.bak
```

**Automated daily backup (crontab):**

```bash
# Add to root crontab: crontab -e
0 3 * * * cd <AI_SERVICE_ROOT> && docker run --rm -v <PROJECT>_mongodb_data:/data -v <AI_SERVICE_ROOT>/backup:/backup alpine tar czf /backup/mongo-backup-$(date +\%Y\%m\%d).tar.gz -C /data . 2>/dev/null
```

### How to Restore

#### Restore MongoDB

```bash
cd <AI_SERVICE_ROOT>

# Stop services
docker compose -f docker-compose.prod.yml down

# Remove old volume
docker volume rm <PROJECT>_mongodb_data

# Restore from backup
docker volume create <PROJECT>_mongodb_data
docker run --rm \
  -v <PROJECT>_mongodb_data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/mongo-backup-YYYYMMDD-HHMMSS.tar.gz -C /data

# Restart
docker compose -f docker-compose.prod.yml up -d
```

#### Restore N8N

```bash
# Stop N8N
docker compose -f docker-compose.prod.yml stop n8n

# Restore
rm -rf data/n8n
tar xzf backup/n8n-backup-YYYYMMDD-HHMMSS.tar.gz

# Restart
docker compose -f docker-compose.prod.yml start n8n
```

### Rolling Back Code

```bash
cd <AI_SERVICE_ROOT>

# View recent commits
git log --oneline -10

# Roll back to specific commit
git checkout <commit-hash>

# Rebuild and restart
docker compose -f docker-compose.prod.yml up -d --build app
```

To return to latest:
```bash
git checkout main
docker compose -f docker-compose.prod.yml up -d --build app
```

---

## Deployment Workflow

### Updating Server B (AI Service)

```bash
ssh root@chat.<SHOP_DOMAIN>
cd <AI_SERVICE_ROOT>

# Pull latest code
git pull origin main

# Rebuild only the AI service container (MongoDB/N8N unchanged)
docker compose -f docker-compose.prod.yml up -d --build app

# Verify
curl http://localhost:8000/health

# Check logs for errors
docker compose -f docker-compose.prod.yml logs --tail=50 app
```

**Zero-downtime note:** The FastAPI container restarts in ~5-10 seconds. Active WebSocket connections will drop and clients will auto-reconnect.

### Updating Plugin (Server A)

```bash
ssh admin@<SHOP_DOMAIN>
cd /var/www/<SHOP_DOMAIN>/src/custom/plugins/<PLUGIN_DIR>/

# Pull latest
git pull origin main

# Back in Shopware root
cd /var/www/<SHOP_DOMAIN>/

# Refresh plugin registry
bin/console plugin:refresh

# Update plugin (runs migrations if any)
bin/console plugin:update <PLUGIN_NAME>

# Recompile storefront assets
bin/console theme:compile

# Clear all caches
bin/console cache:clear
```

### Version Tags

| Repository | Versioning | Example |
|-----------|-----------|---------|
| <PROJECT_NAME> | Git tags (semver) | `v1.2.0` |
| <PLUGIN_REPO> (plugin) | `composer.json` version + Git tags | `1.2.0` |

To deploy a specific version:
```bash
# Server B
git fetch --tags
git checkout v1.2.0
docker compose -f docker-compose.prod.yml up -d --build app

# Server A (plugin)
git fetch --tags
git checkout v1.2.0
cd /var/www/<SHOP_DOMAIN> && bin/console plugin:update <PLUGIN_NAME> && bin/console theme:compile && bin/console cache:clear
```

---

## Important URLs

| Resource | URL |
|----------|-----|
| **Production Shop** | https://<SHOP_DOMAIN> |
| **AI Service (API)** | https://chat.<SHOP_DOMAIN> |
| **Health Check** | https://chat.<SHOP_DOMAIN>/health |
| **Dashboard** | https://chat.<SHOP_DOMAIN>/dashboard |
| **N8N Workflows** | https://chat.<SHOP_DOMAIN>/n8n/ |
| **Mongo Express** | https://chat.<SHOP_DOMAIN>/db/ |
| **LangSmith Traces** | https://eu.smith.langchain.com (project: <LANGSMITH_PROJECT>) |
| **Zendesk** | https://<ZENDESK_SUBDOMAIN>.zendesk.com |
| **Shopware Admin** | https://<SHOP_DOMAIN>/admin |
| **Plugin Config** | https://<SHOP_DOMAIN>/admin#/sw/extension/config/<PLUGIN_NAME> |

---

## Quick Reference Commands

### Server B (chat.<SHOP_DOMAIN>)

| Task | Command |
|------|---------|
| Start all | `docker compose -f docker-compose.prod.yml up -d` |
| Stop all | `docker compose -f docker-compose.prod.yml down` |
| Rebuild AI service | `docker compose -f docker-compose.prod.yml up -d --build app` |
| View AI logs | `docker compose -f docker-compose.prod.yml logs -f app` |
| View Mongo logs | `docker compose -f docker-compose.prod.yml logs -f mongo` |
| Health check | `curl http://localhost:8000/health` |
| Clear semantic cache | `curl -X POST http://localhost:8000/cache/clear` |
| Mongo shell | `docker compose -f docker-compose.prod.yml exec mongo mongosh` |
| Backup MongoDB | `docker run --rm -v <PROJECT>_mongodb_data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/mongo-$(date +%Y%m%d).tar.gz -C /data .` |
| Check disk usage | `docker system df` |
| Prune old images | `docker image prune -a --filter "until=168h"` |
| Restart Nginx | `systemctl restart nginx` |
| Renew SSL | `certbot renew --nginx` |

### Server A (<SHOP_DOMAIN>)

| Task | Command |
|------|---------|
| Plugin refresh | `bin/console plugin:refresh` |
| Plugin update | `bin/console plugin:update <PLUGIN_NAME>` |
| Theme compile | `bin/console theme:compile` |
| Clear cache | `bin/console cache:clear` |
| View logs | `tail -f var/log/prod-$(date +%Y-%m-%d).log` |
| Find your IP | `curl -4 ifconfig.me` |
| MySQL console | `mysql -u shopware -p shopware_db` |

### Credential Generation

| Credential | Command |
|-----------|---------|
| JWT Secret | `openssl rand -hex 32` |
| Dashboard Key | `openssl rand -hex 16` |
| Shared API Key | `openssl rand -hex 24` |
| Mongo Express PW | `openssl rand -hex 16` |
