# VoltimaxChat — Support Chat AI Flows

> Complete documentation of every flow in the VoltimaxChat system: widget UX, AI agents, escalation pipeline, and infrastructure.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Widget Lifecycle](#widget-lifecycle)
3. [Authentication & Verification](#authentication--verification)
4. [Topic Selection Flow](#topic-selection-flow)
5. [Chat & AI Response Flow](#chat--ai-response-flow)
6. [Specialized AI Agents (Groot)](#specialized-ai-agents-groot)
7. [Confirmation Flow](#confirmation-flow)
8. [Escalation Pipeline](#escalation-pipeline)
9. [Feedback & Rating Flow](#feedback--rating-flow)
10. [Connection & Reconnection](#connection--reconnection)
11. [Widget Features](#widget-features)
12. [Dashboard Analytics](#dashboard-analytics)
13. [n8n Workflow Automation](#n8n-workflow-automation)
14. [Knowledge Base & RAG](#knowledge-base--rag)
15. [Logging & Monitoring](#logging--monitoring)
16. [Data Flow Diagram](#data-flow-diagram)

---

## System Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────┐
│   Shopware Store    │     │   FastAPI (Server B)  │     │   MongoDB   │
│   (Server A)        │     │                       │     │             │
│                     │     │  ┌─────────────────┐  │     │  sessions   │
│  Chat Widget (JS)  ◄──WS──►  WebSocket Handler │  │     │  messages   │
│  Verification API   │     │  └────────┬────────┘  │     │  analytics  │
│  Data Provider API  │     │           │           │     │  logs       │
│  JWT Token Issuer   │     │  ┌────────▼────────┐  │     │  kb_vectors │
│                     │     │  │  LangGraph AI    │  │     │  admin_cfg  │
└─────────────────────┘     │  │  Engine          │  │     └──────┬──────┘
                            │  │  (Groot)         │  │            │
                            │  └────────┬────────┘  │     ┌──────▼──────┐
                            │           │           │     │ Mongo Express│
                            │  ┌────────▼────────┐  │     │ :8081       │
                            │  │ Anthropic Claude │  │     └─────────────┘
                            │  │ (LLM Provider)   │  │
                            │  └─────────────────┘  │     ┌─────────────┐
                            │                       │     │    n8n      │
                            │  ┌─────────────────┐  ├────►│   :5678     │
                            │  │ Escalation       │  │     │  Workflows  │
                            │  │ + Zendesk + SMTP │  │     └─────────────┘
                            │  └─────────────────┘  │
                            │                       │     ┌─────────────┐
                            │  React Dashboard     ◄─────►│  Browser    │
                            │  :8000/dashboard/     │     │  (Admin)    │
                            └──────────────────────┘     └─────────────┘
```

### Services

| Service | Port | Purpose |
|---------|------|---------|
| Shopware (Server A) | 8180 | Storefront, admin, widget host, JWT issuer |
| FastAPI (Server B) | 8000 | AI engine, WebSocket, analytics, dashboard |
| MongoDB | 27017 | All persistent data |
| n8n | 5678 | Workflow automation (escalation alerts, reports) |
| Mongo Express | 8081 | Database browser UI |
| React Dashboard | 3001 (dev) | Analytics dashboard (also served at :8000/dashboard/) |

---

## Widget Lifecycle

### States

```
CLOSED → OPEN → TOPICS → CHATTING → (RATING) → CLOSED
                  ↑                      │
                  └──── NEW CHAT ────────┘
```

### Opening the Widget

```
User clicks chat bubble
        │
        ▼
┌─ Returning user? (localStorage, 24h TTL) ──┐
│                                              │
│  YES                                    NO   │
│  ▼                                      ▼    │
│  Silent auto-verify                Topics    │
│  in background                     shown     │
│  ▼                                immediately│
│  Success → Topics +                with      │
│  "Welcome back, Max" banner        consent   │
│  ▼                                 footer    │
│  Failure → Clear storage,                    │
│  show topics with consent                    │
└──────────────────────────────────────────────┘
```

### Minimizing & Unread Badge

- Minimize: widget hides, bubble remains
- While minimized: incoming messages increment an unread badge (1, 2, ... 9+)
- Click bubble again: widget reappears, badge resets

### Closing

```
User clicks X
        │
        ▼
Currently chatting?
  YES → Show rating overlay (1-5 stars)
        User rates → "Thank you 🙏" → Close after 1.2s
        User skips → Close immediately
  NO  → Close immediately
```

On close:
- Session end tracked to MongoDB
- WebSocket closed
- localStorage chat_id cleared
- Widget DOM removed

---

## Authentication & Verification

### Progressive Disclosure (No Blocking Screens)

**Old flow (removed):** Consent screen → Verification form → Topics
**New flow:** Topics shown immediately → Inline verification only when needed

### For New Users

```
Widget opens
        │
        ▼
Topics grid shown immediately
+ Free-text input: "Or type your question..."
+ Passive consent footer: "By continuing you agree to our privacy policy ↗"
        │
User clicks a topic or types a question
        │
        ▼
Inline verification bar slides down:
┌────────────────────────────────────┐
│ To help you personally:            │
│ [Your name    ] [Your email      ] │
│ [           Continue →            ]│
└────────────────────────────────────┘
        │
User fills in name + email → Continue
        │
        ▼
Server A: POST /voltimax-chat/consent (name, email)
Server A: POST /voltimax-chat/verify (name, email)
        │
        ▼
Returns JWT token + customer context
(has_orders, is_b2b, name, email, customer_id)
        │
        ▼
Save to localStorage (24h TTL)
Proceed to chat with selected topic
```

### For Returning Users (24h)

```
Widget opens
        │
        ▼
localStorage has valid saved user (< 24h)
        │
        ▼
Auto-verify silently in background:
  POST /consent + POST /verify with saved credentials
        │
  Success → Topics + "Welcome back, Max" banner
  Failure → Clear storage, show topics with consent
```

### JWT Token Contents

```json
{
  "email": "max@example.com",
  "name": "Max Mustermann",
  "customer_id": "abc123",
  "has_orders": true,
  "is_b2b": false,
  "iat": 1776684000,
  "exp": 1776685800
}
```

---

## Topic Selection Flow

### Topic Card Grid

Topics are filtered by customer context:

| Visibility | Who sees it |
|-----------|-------------|
| `always` | Everyone |
| `has_orders` | Customers with at least one order |
| `is_b2b` | Business customers only |

### Default Topic Hierarchy

```
📦 Orders (has_orders)
  ├── 🚚 Track Shipment
  ├── ↩️ Return / Refund
  └── ⚠️ Order Problem

🛍️ Products (always)
  ├── ❓ Product Question
  ├── 📊 Stock & Availability
  └── 🚗 Vehicle Compatibility

🚛 Shipping (always)
  ├── ⏱️ Delivery Times
  ├── 💰 Shipping Costs
  └── ⚡ Express Delivery

🔧 Technical Help (always)
  ├── 🛠️ Installation Guide
  ├── 🔍 Compatibility Check
  └── 📋 Technical Specs

👤 Account (always)
  ├── 💳 Payment Methods
  ├── 📍 Address Management
  └── 🧾 Invoice / Receipt

🏢 B2B (is_b2b)
  ├── 📝 Request Quote
  └── 👥 Employee Accounts

💬 More (always)
  ├── 📖 FAQ
  └── 📢 Complaint
```

### Topic Click → Chat Flow

```
User clicks a topic card
        │
        ├── Has sub-cards? ──YES──► Start chat for parent topic
        │                           Bot's first message includes
        │                           sub-card chips:
        │                           [🚚 Track] [↩️ Return] [⚠️ Problem]
        │                           User clicks chip → selects sub-topic
        │
        └── Leaf topic ──────────► Start chat directly
```

### Sub-Cards as Chat Chips (Not Separate Screen)

Instead of navigating to a new grid, sub-topics appear as clickable pills inside the chat:

```
Groot: "Hi Max! I'm Groot. How can I help with your order?"

  [🚚 Track Shipment]  [↩️ Return/Refund]  [⚠️ Order Problem]

User clicks "Track Shipment" → topic switches, greeting follows
```

### Free-Text Input on Topics Screen

If the user types a question directly (without picking a topic):
1. If not verified → show inline verification bar first
2. After verification → start chat with topic `general`
3. Send the typed text as the first user message

---

## Chat & AI Response Flow

### Message Processing Pipeline (LangGraph)

```
User sends message
        │
        ▼
┌─ Intent Classifier (LLM) ──────────────────────┐
│ Classifies into:                                 │
│ order_query, return_query, product_query,        │
│ customer_query, b2b_query, rag_query,            │
│ direct, escalation                               │
│ Also extracts search_query for Shopware          │
└─────────────┬───────────────────────────────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
Needs data? RAG only   Direct/Escalation
    │         │          │
    ▼         │          │
┌──────────┐  │          │
│ Shopware │  │          │
│ Data     │  │          │
│ Fetcher  │  │          │
│ (orders, │  │          │
│ products,│  │          │
│ customer)│  │          │
└────┬─────┘  │          │
     │        │          │
     ▼        ▼          │
┌──────────────────┐     │
│ Knowledge Base   │     │
│ RAG Retriever    │     │
│ (571 CMS chunks) │     │
└────────┬─────────┘     │
         │               │
         ▼               ▼
┌────────────────────────────┐
│ Response Generator         │
│                            │
│ Builds system prompt with: │
│ • Groot identity           │
│ • Agent specialization     │
│ • Language auto-detect     │
│ • Shop context (voltimax)  │
│ • Customer context         │
│ • Shopware data            │
│ • RAG knowledge            │
│ • Confirmation rules       │
│ • Intent-specific guidance │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Escalation Detector        │
│ Frustration score 0.0-1.0  │
│ Threshold: 0.75            │
│ Also checks failed count   │
└────────────┬───────────────┘
             │
             ▼
Stream response token-by-token to widget
```

### Streaming in the Widget

```
Server B sends:
  stream_start → typing indicator appears
  stream_chunk × N → tokens render live in AI bubble
  stream_end (message_id) → finalize bubble, add timestamp + feedback buttons
```

### Quick Replies

Each topic has 3 preset quick reply chips shown above the input:

```
[Where is my order?]  [Track shipment]  [Report delay]
```

Clicking a chip sends it as a regular message. Typing removes the chips.

---

## Specialized AI Agents (Groot)

The AI assistant is named **Groot**. Each topic routes to a specialized agent with its own system prompt:

| Topic | Agent Name | Specialization |
|-------|-----------|---------------|
| `order_status` | Order Tracking Specialist | Carrier URLs, tracking links, delivery status |
| `returns` | Returns & Refunds Agent | Eligibility, labels, packaging, refund timeline |
| `order_issue` | Order Problem Resolver | Wrong items, damage, missing goods |
| `product_help` | Product Expert | Battery types, specs, vehicle matching |
| `stock` | Inventory Specialist | Real-time stock, alternatives |
| `compatibility` | Vehicle Compatibility Expert | Battery group sizes, CCA, dimensions |
| `delivery_time` | Delivery Time Advisor | Estimates, cut-off times |
| `shipping_costs` | Shipping Cost Calculator | Rates, free shipping thresholds |
| `express_delivery` | Express Delivery Specialist | Next-day, same-day options |
| `installation` | Installation Guide Expert | Step-by-step, safety, tools |
| `compatibility_check` | Technical Compatibility Checker | Dimensions, voltage, connectors |
| `tech_specs` | Technical Specifications Expert | Capacity, chemistry, cycle life |
| `payment` | Payment Methods Advisor | Cards, PayPal, invoice, installments |
| `address` | Address Management Helper | Add, edit, default addresses |
| `invoice` | Invoice & Receipts Agent | Download, request, VAT details |
| `b2b_quotes` | B2B Quotation Specialist | Bulk pricing, volume discounts |
| `b2b_employees` | B2B Account Manager | Team access, permissions |
| `faq` | FAQ & Policy Expert | Store policies, warranties |
| `complaint` | Complaint Resolution Specialist | Empathetic, never defensive |
| `general` | General Support Assistant | Versatile, redirects when needed |

### Language Handling

- No hardcoded DE/EN — Groot auto-detects the customer's language from their messages
- Responds in the same language the customer writes in
- Works for German, English, French, Turkish, Polish, or any language

### Shop Context

Every Groot response includes full knowledge of voltimax.de:
- 5,300+ products across batteries, solar, electronics, camper build-out
- 50+ brands (own brands: ACCONIC, VOLTIMA, NOQON, Voltimax)
- Battery technology (AGM, GEL, Lithium, starter vs deep-cycle)
- Solar expertise (MPPT/PWM, Balkonkraftwerk 0% VAT regulations)
- German e-commerce policies (14-day withdrawal, BattG battery return)

---

## Confirmation Flow

### When Confirmation is Required

Any action with real consequences requires explicit customer confirmation:
- Creating a support ticket
- Initiating a return
- Cancelling an order
- Changing account details
- Filing a complaint

### AI-Level Confirmation (Conversational)

Groot is instructed to always summarize and ask before proceeding:

```
Customer: "I want to return order #10234"

Groot: "Just to confirm: you'd like to return order #10234.
        Could you tell me the reason for the return and
        whether you'd prefer a refund or exchange?"

Customer: "Wrong item, I want a refund"

Groot: "Understood — return for order #10234, reason: wrong item,
        requesting a full refund. Shall I create a support ticket
        for this?"

Customer: "Yes"
```

### UI-Level Confirmation (Confirmation Card)

When the system creates a ticket (manual or AI-detected), a structured card appears:

```
┌──────────────────────────────────────┐
│ 🛡 Create Support Ticket             │
│                                      │
│ A support ticket will be created     │
│ and sent to our team for review.     │
│                                      │
│ NAME        Max Mustermann           │
│ EMAIL       max@example.com          │
│ TOPIC       Returns                  │
│ ISSUE       [                    ]   │ ← editable
│             [Wrong item in #10234]   │
│                                      │
│           [Cancel]    [Confirm →]    │
└──────────────────────────────────────┘
```

**Fields:**
- Read-only: Name, Email, Topic (pre-filled from session)
- Editable: Issue Description (customer can type/edit)

**Actions:**
- **Confirm →** → sends `confirm_action` to Server B → creates ticket + emails
- **Cancel** → sends `cancel_action` → Groot says "No problem — request cancelled"

**After confirmation:**
```
Card turns green: "✓ Request confirmed and submitted"
        │
        ▼
Groot: "Ticket #12345 created. Confirmation sent to max@example.com."
```

---

## Escalation Pipeline

### Escalation Triggers

| Trigger | How | Threshold |
|---------|-----|-----------|
| Frustration detection | LLM scores 0.0-1.0 | ≥ 0.75 |
| Failed responses | Count of "I don't know" replies | ≥ 3 |
| User request | "I want to speak to a human" | Immediate |
| "Not helpful" button | Widget UI button | Immediate |

### AI-Detected Escalation Flow

```
LangGraph detects frustration score ≥ 0.75
        │
        ▼
Groot sends empathetic message:
"I understand this needs human attention."
        │
        ▼
Confirmation card appears automatically:
┌──────────────────────────────────────┐
│ 🛡 Create Support Ticket             │
│ Groot detected this needs human      │
│ attention. Create a support ticket?  │
│ ...editable fields...                │
│           [Cancel]    [Confirm →]    │
└──────────────────────────────────────┘
        │
Customer clicks Confirm
        │
        ▼
┌─ Ticket Creation ───────────────────────────────┐
│                                                  │
│  1. AI summarizes conversation (LLM call)        │
│  2. Build full transcript text                   │
│  3. Create Zendesk ticket:                       │
│     Subject: "AI Escalation — [topic]"           │
│     Body: summary + full transcript + metadata   │
│     Tags: voltimax-chat, ai-escalation           │
│     Requester: customer email                    │
│  4. Mark session as "escalated" in MongoDB       │
│  5. Send email to support@voltimax.de:           │
│     - Full alert with transcript                 │
│     - Customer details, session ID, topic        │
│  6. Send email to customer:                      │
│     - Ticket ID + session ID                     │
│     - AI summary of conversation                 │
│     - Follow-up reference instructions           │
│                                                  │
└──────────────────────────────────────────────────┘
        │
        ▼
Groot tells customer in chat:
"Ticket #12345 created. Confirmation sent to max@example.com."
```

### Manual "Not Helpful" Flow

```
Customer clicks "Not Helpful" escalation bar
        │
        ▼
Session marked as escalated (reason: user_not_helpful)
Groot: "I'm sorry I couldn't help. Would you like to contact our support team?"
        │
Customer clicks "Create Ticket"
        │
        ▼
Confirmation card → Confirm → Full ticket + email pipeline
```

### Zendesk Ticket Structure

```
Subject: AI Escalation — order_status
Tags:    [voltimax-chat, ai-escalation]
Requester: Max Mustermann <max@example.com>

Body:
  AI Summary:
  Customer asked about order #10234 tracking. AI provided
  tracking link but customer reported the package shows
  delivered while they haven't received it. Needs human
  intervention for delivery investigation.

  --- Metadata ---
  session_id: a9e0ef61-aa74-4363-847d-7fe036dc74a1
  topic: order_status
  escalation_reason: ai_frustration_detected
  message_count: 8
  order_number: 10234

  --- Full Transcript ---
  Customer: Where is my order #10234?
  Groot (AI): Let me check that for you...
  ...
```

### Email to Support (support@voltimax.de)

```
Subject: AI Escalation — order_status — Ticket #12345

┌─ RED HEADER: "AI Escalation Alert" ─────────┐
│ Ticket: #12345                                │
│ Session: a9e0ef61-...                         │
│ Customer: Max Mustermann (max@example.com)    │
│ Topic: order_status                           │
│ Reason: ai_frustration_detected               │
├───────────────────────────────────────────────┤
│ AI Summary: [summarized conversation]         │
├───────────────────────────────────────────────┤
│ Full Transcript: [complete chat log]          │
└───────────────────────────────────────────────┘
```

### Email to Customer

```
Subject: Voltimax Support — Your request #12345

┌─ PURPLE HEADER: "Voltimax Support" ─────────┐
│ Hi Max,                                       │
│ Your support request has been received.       │
│                                               │
│ Ticket ID: #12345                             │
│ Session:   a9e0ef61-...                       │
│ Topic:     order_status                       │
│                                               │
│ Summary of your conversation:                 │
│ ▎ Customer asked about order #10234...        │
│                                               │
│ Reference ticket #12345 for follow-up.        │
│                                               │
│ — Groot, AI Assistant at Voltimax             │
└───────────────────────────────────────────────┘
```

---

## Feedback & Rating Flow

### Per-Message Feedback (👍/👎)

Every AI message gets a feedback row:

```
Groot: "Here are your order details..."
                              [👍] [👎]
```

- Click 👍 → sends `feedback: "up"` to Server B → stored in analytics_events
- Click 👎 → sends `feedback: "down"` → stored, may trigger "Not Helpful" bar
- Both buttons disable after click (one-shot)

### Session Rating (1-5 Stars)

Shown as an overlay when the user closes the chat:

```
┌───────────────────────────────┐
│ How was your chat experience? │
│                               │
│    ★ ★ ★ ★ ★                │
│                               │
│         [Skip]                │
└───────────────────────────────┘
```

- Click a star → rating sent to Server B → stored on session + analytics event
- "Thank you! 🙏" message → close after 1.2s
- Skip → close immediately

---

## Connection & Reconnection

### WebSocket Primary + SSE Fallback

```
Widget connects to Server B:
  1. Try WebSocket: wss://server-b/ws/chat
     │
     ├── Success → auth message → session created
     │   Connection status dot: 🟢 green
     │
     └── Failure → Fallback to SSE
                   GET /sse/chat?token=...
                   Connection status dot: 🟡 yellow
```

### Auto-Reconnect (Exponential Backoff)

```
WebSocket disconnects unexpectedly
  Connection status dot: 🔴 red
        │
        ▼
Attempt 1: wait 1s → reconnect
Attempt 2: wait 2s → reconnect
Attempt 3: wait 4s → reconnect
Attempt 4: wait 8s → reconnect
Attempt 5: wait 16s → reconnect (max)
        │
All 5 failed → stop trying
```

### Connection Status Dot

Visible in the widget header, next to "Online":

| Color | Meaning |
|-------|---------|
| 🟢 Green | WebSocket connected |
| 🟡 Yellow | SSE fallback |
| 🔴 Red | Disconnected |

Uses CSS custom properties for smooth color transitions.

---

## Widget Features

### Dark Mode

Three modes (set via plugin config):
- `light` — always light
- `dark` — always dark
- `auto` — follows OS `prefers-color-scheme` media query

### Sounds (Web Audio API)

No audio files — synthesized via Web Audio oscillator:
- **Outgoing** (user sends): Short 600→800Hz rising tone, 0.12s
- **Incoming** (AI responds): 880→660Hz falling tone, 0.15s
- **Server-triggered**: `play_sound` event from Server B

### Copy Transcript

Header button copies the full chat as text to clipboard:
```
Sie: Wo ist meine Bestellung #10234?
AI: Hier sind die Details zu Ihrer Bestellung...
```

### New Chat

Header button starts a fresh session — closes WS, resets state, shows topics.

### Markdown Rendering

AI responses support (XSS-safe, no innerHTML):
- **Bold** and *italic*
- Bullet and numbered lists
- Links: `[text](url)` → clickable anchor
- Tracking links: DHL/DPD/UPS/GLS URLs get special chip with copy button

---

## Dashboard Analytics

### React + Tailwind CSS Dashboard

Accessible at `http://localhost:8000/dashboard/` (production) or `http://localhost:3001/dashboard/` (dev).

**Auth:** `X-Dashboard-Key` header (same as Shopware integration API key).

### Sections

| Section | Content |
|---------|---------|
| **Overview** | 6 KPI cards (total chats, active, escalation rate, AI resolution, tickets, tokens) + escalation reasons + star ratings chart |
| **Topics** | Bar chart + table of topic session counts and escalation rates |
| **Conversations** | Searchable, paginated table with transcript modal (chat bubble view) |
| **Feedback** | 👍/👎 stats + doughnut chart + rating distribution |
| **Costs** | LLM cost per provider (tokens × rate estimate) |
| **Escalations** | Doughnut chart + breakdown table with percentage bars |
| **Performance** | Response time, LLM latency, chat duration KPIs + grouped bar chart by provider |
| **Logs** | Application logs from MongoDB with level/search/time filters and pagination |
| **LLM Config** | Provider cards (OpenAI, Anthropic, Google, Mistral, Custom) with toggle/key/model |
| **Topics Config** | CRUD editor for topic cards and sub-cards with visibility/LLM provider |
| **Knowledge** | KB status, CMS sync, file upload, sources table |

### Tech Stack

- React 19 + TypeScript
- Tailwind CSS v4
- react-router-dom (client-side routing)
- react-chartjs-2 + Chart.js (charts)
- lucide-react (icons)
- Vite (build + dev server with API proxy)

---

## n8n Workflow Automation

### Active Workflows

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| **Escalation Alert** | `POST /webhook/voltimax-alert` | Logs escalation to Server B analytics |
| **Create Zendesk Ticket** | `POST /webhook/voltimax-ticket` | Logs ticket creation to Server B |
| **Knowledge Ingestion** | `POST /webhook/voltimax-ingestion` | Triggers CMS content sync |
| **Weekly Report** | Cron: Monday 08:00 | Fetches analytics + costs, formats report, stores on Server B |

### Access

- URL: `http://localhost:5678`
- Login: `admin@voltimax.local` / `Voltimax2026!`

---

## Knowledge Base & RAG

### Current State

- **571 chunks** from **97 Shopware CMS pages** indexed in MongoDB
- Embedding provider: `fake` (random vectors — TODO: switch to OpenAI)
- Chunking: 512 tokens, 50 overlap

### RAG Pipeline

```
User asks a question
        │
        ▼
Intent classified as rag_query (or as supplement to other intents)
        │
        ▼
Question → embedding → cosine similarity search in knowledge_vectors
        │
        ▼
Top-k chunks injected into system prompt as KNOWLEDGE BASE context
        │
        ▼
LLM generates answer grounded in retrieved content
```

### Sources

| Source Type | How | Status |
|------------|-----|--------|
| CMS Pages | Sync from Shopware via Store API | ✅ 571 chunks indexed |
| File Upload | PDF/TXT/MD/DOCX via dashboard | ✅ Ready (none uploaded) |
| URL Crawler | Crawl external URLs | ⚠️ Configured, not active |
| Q&A Pairs | Manual question-answer pairs | ✅ Ready (none added) |

---

## Logging & Monitoring

### Application Logs in MongoDB

- Python `logging` → `MongoLogHandler` → `logs` collection
- Buffer: flushes every 5 records or every 10 seconds
- TTL: auto-expires after 30 days
- Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Dashboard Log Viewer

- Filter by level, time range (1h/6h/24h/3d/7d), text search
- Color-coded level badges
- Expandable tracebacks for errors
- Paginated (100 per page)

### Other Monitoring

| Tool | URL | Purpose |
|------|-----|---------|
| Grafana | :3007 | Infrastructure metrics |
| Prometheus | :9091 | Metrics collection |
| Uptime Kuma | :3006 | Uptime monitoring |
| Dozzle | :8085 | Docker log viewer |
| cAdvisor | :8086 | Container resource usage |
| RabbitMQ | :15672 | Message queue dashboard |

---

## Data Flow Diagram

### Chat Session Lifecycle

```
1. Widget opens → localStorage check
2. Verification (if needed) → Server A issues JWT
3. WebSocket connect to Server B → auth with JWT
4. Server B creates session in MongoDB (chat_sessions)
5. User selects topic → Server B sets topic + LLM provider
6. Groot generates greeting via LLM
7. User sends message:
   a. Store in MongoDB (chat_messages)
   b. Run through LangGraph pipeline
   c. Stream response back via WebSocket
   d. Store AI response in MongoDB
   e. Track response_time + token_usage in analytics_events
8. Feedback: stored in analytics_events
9. Escalation (if triggered):
   a. AI summary via LLM
   b. Confirmation card → customer confirms
   c. Zendesk ticket created
   d. Email to support + customer
   e. Session marked escalated
10. Session end:
    a. Rating overlay (1-5 stars)
    b. session_end event in analytics
    c. Session status → closed
    d. WebSocket closed
```

### MongoDB Collections

| Collection | Documents | Purpose |
|-----------|-----------|---------|
| `chat_sessions` | 84+ | Session state, customer, topic, status |
| `chat_messages` | 253+ | All messages (user + AI) |
| `analytics_events` | 241+ | Events: session_started, topic_selected, escalation, response_time, token_usage, message_feedback, session_rated, session_end |
| `knowledge_vectors` | 571 | CMS page chunks with embeddings |
| `admin_config` | — | Live LLM provider + topic overrides |
| `qa_pairs` | — | Manual Q&A for RAG boost |
| `knowledge_sources` | — | Source metadata |
| `logs` | — | Application logs (30-day TTL) |

---

## Configuration

### Key Config Files

| File | Purpose |
|------|---------|
| `config.yaml` | Server B: LLM providers, topic routing, KB, escalation, rate limits |
| `app/ai/agents.py` | 21 specialized agent system prompts |
| `app/ai/shop_context.py` | Full voltimax.de shop knowledge |
| `docker-compose.yml` | MongoDB, n8n, mongo-express services |

### Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `N8N_PASSWORD` | changeme | n8n basic auth password |
| `VOLTIMAX_DASHBOARD_KEY` | (from config) | Dashboard API key for n8n |

---

*Last updated: 2026-04-20*
*VoltimaxChat v1.0 — Powered by Groot 🌳*
