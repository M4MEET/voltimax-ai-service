# VoltimaxChat — System Flowchart

## Message Processing Flow

```
                        VOLTIMAXCHAT MESSAGE FLOW

  ┌──────────┐     WebSocket      ┌──────────────┐
  │  Chat    │ ──── auth ───────► │  Server B    │
  │  Widget  │ ◄── auth_success ─ │  (FastAPI)   │
  │  (JS)    │    (+ suggestions)  │              │
  │          │                     │  No topic    │
  │          │  type: "message" ──►│  selection   │
  │          │ ◄── ai_card ─────── │  required    │
  └──────────┘                    └──────┬───────┘
       │                                 │
       │  Topics auto-detected           │
       │  by intent classifier           │
       ▼                                 ▼

  CONNECTION HANDLER (connection.py)
  ──────────────────────────────────

  ┌─────────────────────┐
  │ 1. Input Response?  │──yes──► Handle order verification (form submit)
  │    (form submit)    │         └──► Shopware API → verify → cache order
  └─────────┬───────────┘
            no
            ▼
  ┌─────────────────────┐
  │ 2. Order Chip?      │──yes──► Switch topic to order_status/returns
  │    (action button)  │
  └─────────┬───────────┘
            no
            ▼
  ┌─────────────────────────────────────────────────────┐
  │ 3. UNIFIED CLASSIFIER                               │
  │    LangSmith: groot-unified-classifier (mustache)   │
  │                                                     │
  │    Input:  message + session context                │
  │            (has_order, order_number, topic, cache)   │
  │                                                     │
  │    ONE LLM call → { action, intent, search_query,  │
  │                      complexity }                   │
  │    Also does smart model routing (Haiku vs Sonnet)  │
  │    ~40 tokens, temperature=0                        │
  └──────────────┬──────────────────────────────────────┘
                 │
                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                    ROUTE BY ACTION                                │
  │                                                                  │
  │  action != "none"                    action == "none"            │
  │  ┌──────────────┐                   │                            │
  │  │ SHOW CARD    │                   ▼                            │
  │  │ (instant)    │          ┌─────────────────┐                   │
  │  └──────┬───────┘          │ AI PIPELINE     │                   │
  │         │                  │ (LangGraph)     │                   │
  │         ▼                  └────────┬────────┘                   │
  │                                     │                            │
  │  Card Action Map:                   │ (see AI Pipeline below)    │
  │                                     │                            │
  │  HAS verified order:                │                            │
  │  • tracking        → 📦 card       │                            │
  │  • payment         → 💳 card       │                            │
  │  • invoice         → 🧾 card       │                            │
  │  • warranty        → 🛡️ card       │                            │
  │  • return_ticket   → ticket form    │                            │
  │  • problem_ticket  → ticket form    │                            │
  │  • another_order   → 🔍 lookup     │                            │
  │                                     │                            │
  │  ANY state (order or not):          │                            │
  │  • escalation_ticket → ticket form  │                            │
  │  • ticket_lookup   → 🔍 ticket form│                            │
  │  • compatibility   → 🚗 vehicle    │                            │
  │  • batteriepfand   → 📄 pfand flow │                            │
  │  • account_info    → 🔑 login link │                            │
  │  • clarify         → AI asks       │                            │
  │    follow-up question               │                            │
  │                                     │                            │
  │  NO verified order:                 │                            │
  │  • order_lookup    → 🔍 lookup     │                            │
  │    (also for payment/tracking/      │                            │
  │     invoice without verified order) │                            │
  │  • no_order        → 💬 help card  │                            │
  │                                     │                            │
  │  ALL cards sent as type "ai_card"   │                            │
  │  = Groot intro text + card in       │                            │
  │    one unified message bubble       │                            │
  └──────────────────────────────────────────────────────────────────┘
```

## AI Pipeline (LangGraph StateGraph)

```
  Pre-fetch: For product_query intents, products are fetched
  BEFORE the pipeline runs (classifier already provided search_query).

  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
  │ 1. INTENT     │    │ 2. DATA       │    │ 3. RAG        │
  │ CLASSIFIER    │───►│ FETCHER       │───►│ RETRIEVER     │
  │               │    │               │    │               │
  │ SKIPPED       │    │ Shopware API  │    │ MongoDB       │
  │ (pre-classi-  │    │ (cached order │    │ knowledge     │
  │ fied by uni-  │    │  data first)  │    │ vectors       │
  │ fied classi-  │    │               │    │               │
  │ fier)         │    │ Fetches:      │    │ Searches:     │
  │               │    │ • orders      │    │ • FAQ         │
  │ Values from   │    │ • products    │    │ • policies    │
  │ classifier:   │    │ • customers   │    │ • CMS pages   │
  │ • intent      │    │ Also builds:  │    │ • PDFs        │
  │ • search_query│    │ • card_context│    │               │
  │ • data_type   │    │               │    │ • service pages│
  │ • resolved_   │    │               │    │               │
  │   topic       │    │               │    │               │
  └───────────────┘    └───────────────┘    └───────────────┘
  Intents: product_query, product_doc_query, order_query,
  return_query, customer_query, b2b_query, rag_query, direct,
  escalation. Classifier uses last 10 messages for context.
  
  Topic auto-switching: account_info→account, batteriepfand→batteriepfand,
  tracking/payment/invoice/order_lookup→order_status, product_query→product_help
         │                    │                    │
         ▼                    ▼                    ▼
  ┌─────────────────────────────────────────────────────────┐
  │ 4. RESPONSE GENERATOR                                   │
  │                                                         │
  │ LangSmith: groot-system-prompt (mustache template)      │
  │                                                         │
  │ Mustache variables:                                     │
  │ ┌─────────────────────────────────────────────────────┐ │
  │ │ {{agent_prefix}}     ← specialized agent persona    │ │
  │ │ {{customer_name}}    ← from JWT claims              │ │
  │ │ {{customer_email}}   ← from JWT / verification      │ │
  │ │ {{topic_id}}         ← auto-detected topic          │ │
  │ │ {{shop_data}}        ← Shopware order/product data  │ │
  │ │ {{rag_context}}      ← knowledge base matches       │ │
  │ │ {{session_activity}} ← past events (cards, verifs)  │ │
  │ │ {{card_context}}     ← what card is shown NOW       │ │
  │ │ {{instructions}}     ← intent-specific guidance     │ │
  │ │ {{conversation_summary}} ← rolling summary of chat  │ │
  │ │ {{customer_phase}}   ← pre-purchase / post-purchase │ │
  │ └─────────────────────────────────────────────────────┘ │
  │                                                         │
  │ → Streams response via astream_events                   │
  └─────────────────────────────────────────────────────────┘
         │
         ▼
  ┌───────────────┐
  │ 5. ESCALATION │     LangSmith: groot-escalation-detector
  │ DETECTOR      │     Score 0.0-1.0 → threshold 0.7 (0.85 if verified)
  │               │     If triggered → confirmation_request → Zendesk
  └───────────────┘
```

## LangSmith Prompt Hub (8 Prompts)

```
  EU endpoint (eu.api.smith.langchain.com) — 5-min cache TTL
  Fallback: hardcoded templates if LangSmith unavailable
  All pipeline functions decorated with @traceable for full tracing.

  LangSmith Tracing:
    thread_id = chat_id (configurable)  → groups runs by conversation
    tags: ["groot-chat", "session:{chat_id}", "topic:{topic}"]
    metadata: session_id, chat_id, topic_id, customer_email, intent, order_number
    → Search in LangSmith UI by tag "session:FF1CC288" or Threads view

  ┌──────────────────────────────┬──────────┬──────────────────────────────────┐
  │ Prompt Name                  │ Type     │ Used By                          │
  ├──────────────────────────────┼──────────┼──────────────────────────────────┤
  │ groot-system-prompt          │ Mustache │ Response Generator (node 4)      │
  │ groot-unified-classifier     │ Mustache │ Unified Classifier (replaces     │
  │                              │          │ card-router + intent-classifier) │
  │ groot-escalation-detect      │ Plain    │ Escalation Detector (node 5)     │
  │ groot-summarizer             │ Plain    │ Conversation Summarizer          │
  │ groot-card-router            │ Mustache │ Smart Card Router (legacy)       │
  │ groot-pre-classifier         │ Mustache │ Pre-classifier (tier check)      │
  │ groot-greeting               │ Mustache │ Topic greeting generator         │
  │ groot-intent-classifier      │ Plain    │ Intent Classifier (legacy)       │
  └──────────────────────────────┴──────────┴──────────────────────────────────┘

  Pull flow:  LangSmith Hub ──► prompt_hub.py cache ──► chevron render
  Fallback:   If LangSmith down ──► hardcoded template ──► chevron render
```

## Order Verification Flow

```
  User clicks "Look up your order"
       │
       ▼
  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
  │ Order Lookup │    │ User submits │    │ Shopware API │
  │ Card (form) │───►│ order# +     │───►│ get_order()  │
  │ 🔍          │    │ postcode     │    │ (no email    │
  └─────────────┘    └──────────────┘    │  filter)     │
                                         └──────┬───────┘
                                                │
                               ┌────────────────┼────────────────┐
                               ▼                ▼                ▼
                          ┌─────────┐    ┌───────────┐    ┌──────────┐
                          │ VERIFIED │    │ NOT FOUND │    │ WRONG    │
                          │ ✓       │    │ ✗         │    │ POSTCODE │
                          └────┬────┘    └─────┬─────┘    └────┬─────┘
                               │               │               │
                               ▼               ▼               ▼
                        ┌──────────┐    ┌──────────┐    ┌──────────┐
                        │ Cache    │    │ Error    │    │ Error    │
                        │ order in │    │ card     │    │ card     │
                        │ MongoDB  │    │ "Try     │    │ "Check   │
                        │ session  │    │  again"  │    │ postcode"│
                        └────┬─────┘    └──────────┘    └──────────┘
                             │
                             ▼
                     ┌───────────────┐
                     │ Verified Card │  Actions:
                     │ ✓ Order #XXX  │  • Sendung verfolgen
                     │ Status: ...   │  • Zahlungsstatus
                     │ Items: ...    │  • Rechnung anfordern
                     │ Total: €XX.XX │  • Retoure starten
                     └───────────────┘  • Garantie prüfen
                                        • Problem melden
                          │             • An Support eskalieren
                          │             • Andere Bestellung prüfen
                          ▼ (user clicks an action button)

                     Card Router re-classifies
                     → Shows ai_card (Groot intro + card in one bubble)
```

## Dynamic Card System

```
  Universal card schema — all cards use card_type: "dynamic"

  ┌─────────────────────────────────────────────┐
  │  icon  title                     style      │
  │  ─────────────────────────────────────────── │
  │  description text                           │
  │                                             │
  │  ┌─────────────────────────────────────┐    │
  │  │ rows[]                              │    │
  │  │  label: value                       │    │
  │  │  label: value                       │    │
  │  └─────────────────────────────────────┘    │
  │                                             │
  │  ┌─────────────────────────────────────┐    │
  │  │ links[]                             │    │
  │  │  🔗 tracking_code  [copy] [open]    │    │
  │  │  📄 invoice.pdf    [download]       │    │
  │  └─────────────────────────────────────┘    │
  │                                             │
  │  ┌─────────────────────────────────────┐    │
  │  │ form (optional)                     │    │
  │  │  Order number: [___________]        │    │
  │  │  Postcode:     [___________]        │    │
  │  │  [Submit →]                         │    │
  │  └─────────────────────────────────────┘    │
  │                                             │
  │  [action] [action] [action]    actions[]    │
  │                                             │
  │  meta_actions[] (secondary, smaller)        │
  └─────────────────────────────────────────────┘

  Styles: green (success), blue (info), red (error),
          amber (warning), gray (inactive), purple (docs)

  Card Types:
  ┌────────────────────────┬───────┬─────────────────────────────────────────────┐
  │ Builder Function       │ Style │ Content                                     │
  ├────────────────────────┼───────┼─────────────────────────────────────────────┤
  │ order_verified         │ green │ status, items, total, date                  │
  │ tracking               │ *     │ delivery status, carrier                    │
  │ payment                │ *     │ payment status, total                       │
  │ invoice                │purple │ document download links                     │
  │ warranty               │ blue  │ warranty per item                           │
  │ order_failed           │ red   │ error message, try again                    │
  │ order_lookup           │ blue  │ verification form                           │
  │ no_order               │ blue  │ pre-sales help options                      │
  │ batteriepfand_download │ green │ Batteriepfand info, steps, PDF downloads    │
  │ batteriepfand_upload   │ green │ File upload form (radio select + single PDF)│
  │ close_chat             │ blue  │ End-of-conversation card with Close/New Chat│
  │ product_card           │ green │ + cheaper_alternative entries (green border)│
  └────────────────────────┴───────┴─────────────────────────────────────────────┘
  * = color varies by status (shipped=green, open=blue, etc.)
```

## Infrastructure

```
  Server A (Shopware 6)          Server B (FastAPI)        External
  ┌──────────────────┐           ┌──────────────────┐     ┌──────────┐
  │ • Chat Widget JS │◄─────────►│ • WebSocket      │────►│ LangSmith│
  │ • PHP Controller │  WS/SSE   │ • LangGraph      │     │ (tracing │
  │ • JWT Issuer     │           │ • Unified Class. │     │  prompts │
  │ • Order API      │◄─────────►│ • Card Builder   │     │  evals)  │
  │ • Store API      │  REST     │ • Prompt Hub     │     └──────────┘
  │ • Compatibility  │           │ • Analytics      │     ┌──────────┐
  │   Filter (Onco)  │           │ • Dashboard      │     │ Anthropic│
  │ • CMS + Media    │           │ • KB/RAG (10K+   │     │ Haiku +  │
  │ • CheaperAd      │           │   vectors, OpenAI│     │ Sonnet   │
  └──────────────────┘           │   embeddings)    │     │ (smart   │
                                 │ • Semantic cache  │     │  routing)│
  MongoDB URI: mongodb://mongo:27017/?directConnection=true
  (directConnection bypasses replica set discovery — prevents RSGhost)

  ┌──────────────────┐           └────────┬─────────┘     └──────────┘
  │ MongoDB           │◄───────────────────┘               ┌──────────┐
  │ • chat_sessions   │                                    │ Zendesk  │
  │ • chat_messages   │                                    │ (tickets)│
  │ • logs            │                                    └──────────┘
  │ • knowledge_vectors│ (10K+ chunks, 3072-dim)           ┌──────────┐
  │ • qa_pairs        │                                    │ OpenAI   │
  │ • analytics_events│                                    │(embeddings│
  │ • admin_config    │                                    │  only)   │
  └──────────────────┘                                     └──────────┘

  Docker Containers:
  ┌────────────────────┬──────────┬─────────────────────────┐
  │ Container          │ Port     │ Purpose                 │
  ├────────────────────┼──────────┼─────────────────────────┤
  │ shopware-6.6.10.8  │ 8180     │ Shopware storefront     │
  │ shopware_db_66108  │ 3306     │ MariaDB (Shopware)      │
  │ redis-66108        │ 6379     │ Cache (Shopware)        │
  │ mongo              │ 27017    │ MongoDB (AI service)    │
  │ mongo-express      │ 8081     │ MongoDB UI              │
  │ n8n                │ 5678     │ Workflow automation      │
  │ rabbitmq           │ 5672     │ Message queue           │
  │ grafana            │ 3007     │ Monitoring dashboards   │
  │ prometheus         │ 9091     │ Metrics collection      │
  │ uptime-kuma        │ 3006     │ Uptime monitoring       │
  │ dozzle             │ 8085     │ Docker log viewer       │
  └────────────────────┴──────────┴─────────────────────────┘
```

## Zendesk Ticket Creation Flow

### Trigger Points

There are 3 ways a Zendesk ticket gets created:

```
  ┌─────────────────────────────────────────────────────────────┐
  │ TRIGGER 1: Customer clicks action button (verified order)   │
  │                                                             │
  │  "Return an item"    → card_action = return_ticket          │
  │  "Report a problem"  → card_action = problem_ticket         │
  │  "Escalate to support" → card_action = escalation_ticket    │
  ├─────────────────────────────────────────────────────────────┤
  │ TRIGGER 2: AI auto-detects frustration                      │
  │                                                             │
  │  Escalation detector score >= 0.75 (or 0.85 if verified)    │
  │  → Automatic confirmation card shown                        │
  ├─────────────────────────────────────────────────────────────┤
  │ TRIGGER 3: Customer sends msg.type = "create_ticket"        │
  │                                                             │
  │  Widget sends explicit ticket creation request               │
  └─────────────────────────────────────────────────────────────┘
```

### Full Flow: "Report a Problem" Example

```
  Customer has verified order #28418
         │
         ▼
  1. CUSTOMER ACTION
     Clicks "Report a problem" or types "I have a problem with my order"
         │
         ▼
  2. CARD ROUTER (LLM call, ~1s, ~540 tokens)
     LangSmith: groot-card-router
     Input:  message + session context (has_order=true, order=#28418)
     Output: {"action": "problem_ticket"}
         │
         ▼
  3. CONFIRMATION CARD sent to widget
     ┌─────────────────────────────────────────┐
     │  Report a Problem                       │
     │                                         │
     │  Name:    Max Mustermann     (locked)   │
     │  Email:   max@example.com    (locked)   │
     │  Subject: Groot Escalation —            │
     │           Problem — Order #28418        │
     │           (locked)                      │
     │                                         │
     │  Describe the problem:                  │
     │  [________________________________]     │
     │  [________________________________]     │
     │                                         │
     │  [Confirm]              [Cancel]        │
     └─────────────────────────────────────────┘
         │
         ├── Cancel ──► "No problem — the request has been cancelled."
         │              (conversation continues normally)
         │
         ▼ Confirm (msg.type = "confirm_action", action = "create_ticket")
  4. EscalationActions.create_ticket(session_id)
         │
         ▼
     ┌───────────────────────────────────────────────────────┐
     │ STEP A: AI SUMMARIZES CONVERSATION                    │
     │                                                       │
     │ LangSmith: groot-summarizer (~1-2s)                   │
     │ Input:  full chat history (all messages)               │
     │ Output: "Customer Fredi verified order #28418.         │
     │          Reported damaged item upon delivery.          │
     │          Requesting return/replacement."               │
     └───────────────────┬───────────────────────────────────┘
                         │
                         ▼
     ┌───────────────────────────────────────────────────────┐
     │ STEP B: BUILD FULL TRANSCRIPT                         │
     │                                                       │
     │ Customer: Hi                                          │
     │ Groot (AI): Hallo Fredi! Wie kann ich helfen?         │
     │ Customer: Report a problem                            │
     │ ... (all messages in session)                          │
     └───────────────────┬───────────────────────────────────┘
                         │
                         ▼
     ┌───────────────────────────────────────────────────────┐
     │ STEP C: CREATE ZENDESK TICKET                         │
     │                                                       │
     │ POST https://battrongmbh.zendesk.com/api/v2/tickets   │
     │                                                       │
     │ {                                                     │
     │   "ticket": {                                         │
     │     "subject": "Groot Escalation — Problem —          │
     │                 Order #28418",                         │
     │     "description": "AI Summary:\n...\n\n              │
     │                     --- Full Transcript ---\n...\n\n   │
     │                     --- Metadata ---\n                 │
     │                     session_id: 8e432b0a-...\n         │
     │                     topic: order_status\n              │
     │                     order_number: 28418",              │
     │     "requester": {                                    │
     │       "name": "Max Mustermann",                       │
     │       "email": "max@example.com"                      │
     │     },                                                │
     │     "tags": ["voltimax-chat", "ai-escalation"]        │
     │   }                                                   │
     │ }                                                     │
     │                                                       │
     │ Auth: marci@voltimax.de/token + API key               │
     │ Response: ticket_id = 16986                           │
     └───────────────────┬───────────────────────────────────┘
                         │
                         ▼
     ┌───────────────────────────────────────────────────────┐
     │ STEP D: MARK SESSION ESCALATED                        │
     │                                                       │
     │ MongoDB: chat_sessions.update(                         │
     │   { id: session_id },                                  │
     │   { escalation_reason: "ticket_created" }              │
     │ )                                                      │
     └───────────────────┬───────────────────────────────────┘
                         │
                         ▼
     ┌───────────────────────────────────────────────────────┐
     │ STEP E: SEND EMAILS (non-blocking, needs SMTP config) │
     │                                                       │
     │ Email 1 → support@voltimax.de                         │
     │   Subject: "Groot Escalation — order_status —          │
     │             Ticket #16986"                             │
     │   Body: Customer info + AI summary + full transcript   │
     │   Style: Red alert header, metadata table              │
     │                                                       │
     │ Email 2 → max@example.com (customer)                   │
     │   Subject: "Voltimax Support — Your request #16986"    │
     │   Body: Confirmation + ticket ID + summary             │
     │   Style: Purple branded header, reference info          │
     │                                                       │
     │ Note: If SMTP not configured, emails are skipped       │
     │       but ticket is still created in Zendesk.           │
     └───────────────────┬───────────────────────────────────┘
                         │
                         ▼
  5. RESPONSE SENT TO WIDGET
     ┌──────────────────────────────────────────────┐
     │ type: "ticket_created"                        │
     │ ticket_id: "16986"                            │
     └──────────────────────────────────────────────┘
     ┌──────────────────────────────────────────────┐
     │ Groot: Support ticket #16986 has been         │
     │ created. Our team will follow up shortly.     │
     │ Confirmation sent to max@example.com.         │
     └──────────────────────────────────────────────┘
```

### Ticket Subject Format

```
  All tickets from VoltimaxChat use the "Groot Escalation" prefix:

  ┌───────────────────┬──────────────────────────────────────────────┐
  │ Trigger            │ Subject                                      │
  ├───────────────────┼──────────────────────────────────────────────┤
  │ Return button      │ Groot Escalation — Return — Order #28418     │
  │ Problem button     │ Groot Escalation — Problem — Order #28418    │
  │ Escalate button    │ Groot Escalation — Support — Order #28418    │
  │ AI auto-detect     │ Groot Escalation — order_status               │
  │ Support email      │ Groot Escalation — order_status — Ticket #X   │
  │ Customer email     │ Voltimax Support — Your request #X            │
  └───────────────────┴──────────────────────────────────────────────┘
```

### Zendesk Configuration

```
  config.yaml:

  escalation:
    zendesk:
      subdomain: "battrongmbh"           # → battrongmbh.zendesk.com
      email: "marci@voltimax.de"          # agent email for API auth
      api_token: "Eoj...NLd"             # Zendesk API token
    support_email: "support@voltimax.de"  # receives escalation alerts
    smtp:                                 # for email notifications
      host: "smtp.gmail.com"
      port: 587
      username: ""                        # ← needs Gmail / SMTP credentials
      password: ""                        # ← needs App Password
      from_email: "noreply@voltimax.de"
      from_name: "Voltimax Support"
      use_tls: true

  Adapter selection (actions.py):
    n8n.enabled = true  → uses N8nWebhookAdapter (webhook to n8n)
    n8n.enabled = false → uses ZendeskAdapter (direct Zendesk API)
    Currently: ZendeskAdapter (n8n disabled)
```

### Code Files

```
  ┌──────────────────────────────────────────────┬────────────────────────────┐
  │ File                                         │ Responsibility              │
  ├──────────────────────────────────────────────┼────────────────────────────┤
  │ app/chat/connection.py                        │ Confirmation card + routing │
  │ app/escalation/actions.py                     │ Orchestrates all 5 steps    │
  │ app/escalation/ticket/zendesk_adapter.py      │ Zendesk REST API call       │
  │ app/escalation/ticket/n8n_webhook.py          │ n8n webhook (alternative)   │
  │ app/escalation/ticket/base.py                 │ Abstract adapter interface  │
  │ app/escalation/email_sender.py                │ SMTP emails (support+cust)  │
  │ app/ai/graph/nodes/summarizer.py              │ AI conversation summary     │
  │ app/ai/graph/nodes/escalation_detector.py     │ Frustration score 0.0-1.0   │
  └──────────────────────────────────────────────┴────────────────────────────┘
```

## Knowledge Base & RAG Embedding Flow

### Overview

The knowledge base stores CMS content, product info, and policies as vector
embeddings in MongoDB. When a customer asks a question, the RAG retriever
searches for relevant content using cosine similarity and injects it into
the AI's system prompt.

```
  ┌────────────────────────────────────────────────────────────────┐
  │ KNOWLEDGE BASE PIPELINE                                        │
  │                                                                │
  │  Content Sources          Embedding            Search          │
  │  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
  │  │ CMS Pages    │     │ OpenAI       │     │ MongoDB Atlas │   │
  │  │ Product Info │────►│ text-embed-  │────►│ Vector Search│   │
  │  │ Policies     │     │ ding-3-large │     │ (cosine)     │   │
  │  │ FAQ / Q&A    │     │ 3072 dims    │     │              │   │
  │  └──────────────┘     └──────────────┘     └──────┬───────┘   │
  │                                                    │           │
  │                                          Customer asks         │
  │                                          a question            │
  │                                                    │           │
  │                                                    ▼           │
  │                                           ┌──────────────┐    │
  │                                           │ Top-K docs   │    │
  │                                           │ injected as  │    │
  │                                           │ KNOWLEDGE    │    │
  │                                           │ BASE section │    │
  │                                           │ in system    │    │
  │                                           │ prompt       │    │
  │                                           └──────────────┘    │
  └────────────────────────────────────────────────────────────────┘
```

### How RAG Works in the AI Pipeline

```
  Customer message: "Was kostet der Versand?"
         │
         ▼
  1. Intent Classifier → intent=rag_query
         │
         ▼
  2. Data Fetcher → (no Shopware data needed for rag_query)
         │
         ▼
  3. RAG Retriever
     ┌─────────────────────────────────────────────────────┐
     │ a) Q&A exact match check (qa_pairs collection)      │
     │    → If match found (score >= 0.85): return answer   │
     │    → Skip LLM call entirely                         │
     │                                                     │
     │ b) Vector search (knowledge_vectors collection)     │
     │    → Embed query with OpenAI text-embedding-3-large │
     │    → $vectorSearch (cosine, top_k=4)                │
     │    → Return matching document chunks                │
     └─────────────────────────────────────────────────────┘
         │
         ▼
  4. Response Generator
     System prompt now includes:
     KNOWLEDGE BASE:
     "Kostenloser Versand ab 49 €. Blitzschneller Versand.
      30 Tage Rückgaberecht..."
         │
         ▼
  5. AI responds with accurate, KB-backed answer
```

### Embedding Configuration

```
  config.yaml:

  knowledge_base:
    embedding_provider: "openai"
    embedding_model: "text-embedding-3-large"    # 3072 dims, best quality
    chunk_size: 512                              # chars per chunk
    chunk_overlap: 100                           # overlap between chunks
```

### Re-Embedding Script

```
  When to re-embed:
  • After changing the embedding model (e.g. small → large)
  • After bulk content updates or data cleanup
  • NOT needed for new documents — they auto-embed on add

  Run:
    cd voltimax-ai-service

    # Preview (no changes)
    venv/bin/python scripts/reembed_knowledge.py --dry-run

    # Re-embed all documents
    venv/bin/python scripts/reembed_knowledge.py

  What it does:
  1. Reads embedding model from config.yaml
  2. Drops old vector_index
  3. Re-embeds all documents in batches of 50
  4. Recreates vector_index with correct dimensions
  5. ~30 seconds for 571 docs, ~$0.05 cost
```

### MongoDB Collections

```
  ┌──────────────────────┬──────────────────────────────────────────┐
  │ Collection           │ Purpose                                  │
  ├──────────────────────┼──────────────────────────────────────────┤
  │ knowledge_vectors    │ 10K+ embedded document chunks             │
  │                      │ Fields: content, embedding (3072 floats), │
  │                      │ source_id, source_type, metadata          │
  │                      │ Index: vector_index (cosine, knnVector)   │
  ├──────────────────────┼──────────────────────────────────────────┤
  │ qa_pairs             │ Exact Q&A pairs (highest priority)        │
  │                      │ Fields: question, answer,                 │
  │                      │ question_embedding (for similarity match) │
  ├──────────────────────┼──────────────────────────────────────────┤
  │ knowledge_sources    │ Source metadata (files, CMS pages, URLs)  │
  └──────────────────────┴──────────────────────────────────────────┘
```

### Code Files

```
  ┌────────────────────────────────────────────┬────────────────────────────────┐
  │ File                                       │ Purpose                        │
  ├────────────────────────────────────────────┼────────────────────────────────┤
  │ app/knowledge/vector_store.py              │ Search, add, delete vectors    │
  │ app/knowledge/embedder.py                  │ OpenAI/fake embedding provider │
  │ app/ai/graph/nodes/rag_retriever.py        │ LangGraph node: Q&A + RAG     │
  │ scripts/reembed_knowledge.py               │ Bulk re-embed script           │
  └────────────────────────────────────────────┴────────────────────────────────┘
```

## Ticket Lookup & Urgent Escalation Flow

### Overview

Customers can check the status of an existing Zendesk ticket and request urgent
follow-up — all from within the chat widget, without creating a new ticket.

```
  Entry points:
  ┌─────────────────────────────────────────────────────────────┐
  │ 1. Customer types "check my ticket status" / "ticket #123" │
  │    → Card router: "ticket_lookup"                          │
  │                                                             │
  │ 2. "Check ticket" button on no_order card                  │
  │                                                             │
  │ 3. "Check ticket status" option in error / post-ticket UI  │
  └─────────────────────────────────────────────────────────────┘
```

### Step 1: Ticket Lookup Form

```
  Customer triggers ticket lookup
         │
         ▼
  ┌─────────────────────────────────────────┐
  │ 🔍 Check Ticket Status                  │
  │                                         │
  │ Ticket number: [___________________]   │
  │ Email:         [___________________]   │
  │                                         │
  │ [Check Status →]                       │
  └─────────────────────────────────────────┘
```

### Step 2: Zendesk API Lookup

```
  Customer submits ticket # + email
         │
         ▼
  Zendesk API: GET /api/v2/tickets/{id}.json
  Auth: marci@voltimax.de/token + API key
         │
         ▼
  ┌─────────────────────────────────────────────┐
  │ SECURITY CHECK                               │
  │                                               │
  │ ticket.requester.email == submitted email?    │
  │                                               │
  │ YES → show status card                        │
  │ NO  → "Ticket not found or email doesn't     │
  │        match. Please check your details."     │
  └─────────────────────────────────────────────┘
```

### Step 3: Ticket Status Card

```
  Ticket found + email matches
         │
         ▼
  ┌─────────────────────────────────────────────────────┐
  │ 📋 Ticket #16985                                    │
  │                                                     │
  │ Status:      Open                    style=amber    │
  │ Priority:    Normal                                 │
  │ Subject:     Groot Escalation — Problem — #28418    │
  │ Created:     2026-04-24                             │
  │ Updated:     2026-04-24                             │
  │                                                     │
  │ Last reply:                                         │
  │ "We are reviewing your case and will respond..."    │
  │                                                     │
  │ 📋 Ticket #16985                      [Copy]        │
  │                                                     │
  │ [🚨 Mark as Urgent]              (only if open)     │
  └─────────────────────────────────────────────────────┘

  Status styles:
  ┌──────────┬─────────┬──────────────────────────────────┐
  │ Status   │ Style   │ Show "Mark as Urgent" button?    │
  ├──────────┼─────────┼──────────────────────────────────┤
  │ new      │ blue    │ yes                              │
  │ open     │ amber   │ yes                              │
  │ pending  │ amber   │ yes                              │
  │ hold     │ gray    │ no (already being handled)       │
  │ solved   │ green   │ no (resolved)                    │
  │ closed   │ gray    │ no (resolved)                    │
  └──────────┴─────────┴──────────────────────────────────┘
```

### Step 4: Urgent Escalation

```
  Customer clicks "Mark as Urgent"
         │
         ▼
  ┌─────────────────────────────────────────────────┐
  │ Confirm Urgent Escalation                        │
  │                                                  │
  │ This will:                                       │
  │ • Change ticket #16985 priority to URGENT        │
  │ • Notify our support team for faster response    │
  │                                                  │
  │ Reason for urgency (optional):                   │
  │ [____________________________________]          │
  │                                                  │
  │ [Confirm — Mark Urgent]          [Cancel]        │
  └─────────────────────────────────────────────────┘
         │
         ├── Cancel → "No problem — priority unchanged."
         │
         ▼ Confirm
  ┌───────────────────────────────────────────────────────┐
  │ STEP A: UPDATE ZENDESK TICKET                         │
  │                                                       │
  │ PUT /api/v2/tickets/{id}.json                          │
  │ {                                                     │
  │   "ticket": {                                         │
  │     "priority": "urgent",                             │
  │     "tags": [...existing, "groot-urgent"],            │
  │     "comment": {                                      │
  │       "body": "⚠️ URGENT: Customer requested          │
  │               immediate attention via Groot chat.\n    │
  │               Reason: {customer_reason}\n             │
  │               Time: 2026-04-24 14:30 UTC",            │
  │       "public": false  ← internal note only           │
  │     }                                                 │
  │   }                                                   │
  │ }                                                     │
  └───────────────────┬───────────────────────────────────┘
                      │
                      ▼
  ┌───────────────────────────────────────────────────────┐
  │ STEP B: SEND URGENT ALERT EMAIL                       │
  │                                                       │
  │ To: support@voltimax.de                               │
  │ Subject: "🚨 URGENT — Ticket #16985 requires          │
  │           immediate attention"                        │
  │                                                       │
  │ Body:                                                 │
  │ • Customer name + email                               │
  │ • Original ticket subject                             │
  │ • Customer's urgency reason                           │
  │ • Link to ticket in Zendesk                           │
  │ • Timestamp of escalation                             │
  └───────────────────┬───────────────────────────────────┘
                      │
                      ▼
  ┌───────────────────────────────────────────────────────┐
  │ STEP C: CONFIRMATION CARD                             │
  │                                                       │
  │ ┌─────────────────────────────────────────────────┐   │
  │ │ 🚨 Ticket #16985 — Marked as Urgent             │   │
  │ │                                                 │   │
  │ │ Priority:  Urgent              style=red        │   │
  │ │ Status:    Open                                 │   │
  │ │                                                 │   │
  │ │ Our team has been notified and will             │   │
  │ │ prioritize your request.                        │   │
  │ │                                                 │   │
  │ │ 📋 Ticket #16985                    [Copy]      │   │
  │ └─────────────────────────────────────────────────┘   │
  │                                                       │
  │ Session event logged:                                 │
  │   "ticket_urgent: #16985 escalated to urgent"         │
  └───────────────────────────────────────────────────────┘
```

### Guard Rails

```
  ┌──────────────────────────────────────────────────────────────┐
  │ SECURITY                                                      │
  │ • Email must match Zendesk ticket requester                   │
  │ • Customers cannot see other people's tickets                 │
  │ • No order verification required (ticket is its own auth)     │
  │                                                               │
  │ RATE LIMITING                                                 │
  │ • Cannot re-escalate the same ticket within the same session  │
  │ • Session event tracks which tickets were escalated           │
  │ • "Mark as Urgent" button hidden after escalation             │
  │                                                               │
  │ SCOPE                                                         │
  │ • Only show "Mark as Urgent" for new/open/pending tickets     │
  │ • Solved/closed tickets: show status only, no escalation      │
  │ • Hold tickets: show "being handled" message, no escalation   │
  └──────────────────────────────────────────────────────────────┘
```

### Card Router Integration

```
  New action added to groot-card-router prompt:

  If customer does NOT have a verified order:
    "ticket_lookup" — wants to check status of an existing support ticket

  Examples that trigger ticket_lookup:
    "What is the status of my ticket?"
    "I created a ticket last week, any update?"
    "Ticket number 16985"
    "Check my support request"
```

### Code Files (new + modified)

```
  ┌──────────────────────────────────────────────┬────────────────────────────┐
  │ File                                         │ Change                      │
  ├──────────────────────────────────────────────┼────────────────────────────┤
  │ app/ai/card_builder.py                        │ + build_ticket_lookup_card  │
  │                                              │ + build_ticket_status_card  │
  │                                              │ + build_ticket_urgent_card  │
  │ app/ai/card_router.py                         │ + "ticket_lookup" action    │
  │ app/escalation/ticket/zendesk_adapter.py      │ + get_ticket_status()       │
  │                                              │ + mark_ticket_urgent()      │
  │ app/escalation/email_sender.py                │ + send_urgent_alert_email() │
  │ app/chat/connection.py                        │ + ticket_lookup handler     │
  │                                              │ + urgent escalation handler │
  │ scripts/push_prompts_to_langsmith.py          │ + ticket_lookup in router   │
  └──────────────────────────────────────────────┴────────────────────────────┘
```

### Zendesk API Endpoints Used

```
  ┌────────────────────────────────────────┬──────────┬──────────────────────┐
  │ Endpoint                               │ Method   │ Purpose              │
  ├────────────────────────────────────────┼──────────┼──────────────────────┤
  │ /api/v2/tickets/{id}.json              │ GET      │ Fetch ticket status  │
  │ /api/v2/tickets/{id}.json              │ PUT      │ Update priority +    │
  │                                        │          │ add internal comment │
  │ /api/v2/tickets/{id}/comments.json     │ GET      │ Get latest reply     │
  └────────────────────────────────────────┴──────────┴──────────────────────┘

  Auth for all: {email}/token + api_token (same as ticket creation)
```

## Smart Model Routing

```
  Haiku (fast/cheap) for simple queries, Sonnet (capable) for complex.

  Detection layers:
  1. Classifier: complexity field ("simple" / "complex")
  2. Heuristics: msg_len > 150, 3+ topic switches, thumbs down, escalation intent
  3. Override: complex + ticket cards → AI pipeline (Sonnet) instead of card form

  For frustrated/complex + escalation intent: should_escalate only if complexity=complex.
  Pre-purchase + escalation_ticket + simple: AI responds conversationally first.
```

## Semantic Response Cache

```
  In-memory cache avoids repeated LLM calls for similar queries.

  Layer 1: Embedding cache (query text → vector, avoids OpenAI calls)
  Layer 2: Response cache (query embedding → cached response, avoids LLM calls)

  Only caches: rag_query, direct intents (no personal data)
  Threshold: 0.85 cosine similarity
  TTL: 24 hours
  Clear: POST /cache/clear (when policies change)
  Stats: visible in /health endpoint + dashboard
```

## Batteriepfand (Battery Deposit Return) Flow

```
  Customer: "Batteriepfand" or "Pfandrückgabe"
  → Classifier: action=batteriepfand (NEVER product_query)

  Step 1: Download card shown (ai_card bubble):
    - ℹ️ Info about §19 BattDG, 7.50€ deposit
    - Steps 1-3 with detailed instructions
    - ⚠️ Deadline warnings (2 weeks after disposal, 30 days after purchase)
    - 📄 PDF downloads (Entsorgungsnachweis + Rücksendung)
    - Actions: [Ich habe die Formulare ausgefüllt] [Noch Fragen]

  Step 2: Upload form (ai_card bubble):
    - Radio: ○ Entsorgungsnachweis / ○ Rücksendung Altbatterie
    - File upload (PDF only, required)
    - Name + Email (pre-filled)
    - Subject (read-only): "Groot Escalation — Batteriepfand"
    - Optional: Zusätzliche Informationen textarea
    - [Formular einreichen →]

  Step 3: Submission:
    - PDF uploaded to Zendesk as attachment
    - Ticket created: "Groot Escalation — Batteriepfand (Entsorgungsnachweis)"
    - Confirmation with ticket # and copy button

  Files: static/forms/Voltimax_Vorlage_Entsorgungsnachweis.pdf
         static/forms/Voltimax_Vorlage_Ruecksendung_Altbatterie.pdf

  Endpoint: POST /api/chat/batteriepfand-upload (multipart form)
```

## Cheaper Alternative (CheaperAd Plugin)

```
  When customer asks about specific products (≤6 results):
  1. For each product, call GET /store-api/cheaper-ad/{productId}
  2. CheaperAd plugin checks configured categories + matching properties
  3. Returns cheapest alternative with savings % + matched property names

  In product card: ⭐ Günstigere Alternative shown with green border below each product
  In AI context: alternatives listed with matched properties
  In session events: logged for follow-up awareness

  API response includes matchedProperties (e.g. "Batterietechnologie, Maße")
  so AI can say "both products match on these specs"
```

## End-of-Conversation & Review Collection

```
  Detection: customer says "danke", "thanks", "tschüss", etc. (after 4+ messages)

  → Close chat card shown:
    👋 Kann ich noch etwas für dich tun?
    [Chat schließen] [Neuen Chat starten]

  "Chat schließen" → triggers _close() → rating overlay (same as X button)
  "Neuen Chat starten" → triggers _resetChat() → fresh session

  Both paths collect star ratings (1-5) → stored in MongoDB + LangSmith
```

## Agent & Prompt Architecture

### How Agents, Prompts, and Config Work Together

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                    THREE CONFIGURATION LAYERS                    │
  │                                                                 │
  │  ┌───────────────────────────────────────────────────────────┐  │
  │  │ LAYER 1: LangSmith Prompt Hub (edit from browser)        │  │
  │  │                                                           │  │
  │  │ What it controls:                                         │  │
  │  │   • AI personality, tone, style                           │  │
  │  │   • Response rules (word limit, format, confirmation)     │  │
  │  │   • Security rules (no data fabrication)                  │  │
  │  │   • Language detection rules                              │  │
  │  │   • Template structure (where context is injected)        │  │
  │  │                                                           │  │
  │  │ 8 prompts — editable at eu.smith.langchain.com            │  │
  │  │ Changes take effect in 5 minutes (cache TTL)              │  │
  │  │ No deploy needed                                          │  │
  │  └───────────────────────────────────────────────────────────┘  │
  │                          │                                      │
  │                          ▼                                      │
  │  ┌───────────────────────────────────────────────────────────┐  │
  │  │ LAYER 2: Agent Definitions (edit in code)                 │  │
  │  │                                                           │  │
  │  │ What it controls:                                         │  │
  │  │   • Domain expertise per topic (19 agents)                │  │
  │  │   • Verification tiers (0 = open, 1 = name, 2 = order)   │  │
  │  │   • Intent → agent mapping                                │  │
  │  │   • Greeting hints                                        │  │
  │  │                                                           │  │
  │  │ File: app/ai/agents.py                                    │  │
  │  │ Version controlled in git                                 │  │
  │  │ Requires restart to apply                                 │  │
  │  └───────────────────────────────────────────────────────────┘  │
  │                          │                                      │
  │                          ▼                                      │
  │  ┌───────────────────────────────────────────────────────────┐  │
  │  │ LAYER 3: Runtime Config (config.yaml + MongoDB)           │  │
  │  │                                                           │  │
  │  │ config.yaml (sensitive, not editable from browser):       │  │
  │  │   • API keys (OpenAI, Anthropic, Zendesk, Shopware)       │  │
  │  │   • SMTP credentials                                      │  │
  │  │   • Embedding model selection                              │  │
  │  │   • Rate limits, thresholds                                │  │
  │  │                                                           │  │
  │  │ MongoDB admin_config (editable from dashboard):            │  │
  │  │   • LLM provider routing (which model per topic)          │  │
  │  │   • Topic card visibility                                  │  │
  │  │                                                           │  │
  │  │ MongoDB runtime (automatic):                               │  │
  │  │   • Session data, events, messages                         │  │
  │  │   • Knowledge base vectors                                 │  │
  │  │   • Analytics events                                       │  │
  │  └───────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────┘
```

### How the System Prompt is Assembled

```
  Customer sends a message
         │
         ▼
  Intent Classifier detects: product_query
         │
         ▼
  topic_map: product_query → "product_help"
         │
         ▼
  agents.py: AGENTS["product_help"]
  → system_prefix = "You are a Product Expert for an
     automotive battery and energy storage shop..."
         │
         ▼
  response_generator.py assembles mustache variables:
  ┌───────────────────────────────────────────────────────────┐
  │ agent_prefix         = system_prefix from agents.py       │
  │ customer_name        = "Fredi" (from JWT)                 │
  │ customer_email       = "fredi@test.com"                   │
  │ topic_id             = "product_help"                     │
  │ shop_data            = "Varta AGM 60Ah — €116.75"        │
  │ rag_context          = "Kostenloser Versand ab 49€"       │
  │ session_activity     = "[11:18] card_action: ..."         │
  │ instructions         = "Lead with matching products"      │
  │ conversation_summary = rolling summary of chat            │
  │ customer_phase       = "pre-purchase" / "post-purchase"   │
  └───────────────────────────────────────────────────────────┘
         │
         ▼
  LangSmith: pull "groot-system-prompt" template
         │
         ▼
  Chevron renders mustache → final system prompt:

  ┌─────────────────────────────────────────────────┐
  │ You are Groot, a specialised AI customer        │
  │ support assistant for Voltimax (voltimax.de).    │
  │ When customers ask your name, say "I'm Groot".  │
  │                                                 │
  │ You are a Product Expert for an automotive      │  ← from agents.py
  │ battery and energy storage shop. You have deep  │
  │ knowledge of battery types (starter, deep-cycle │
  │ AGM, EFB, gel, lithium)...                      │
  │                                                 │
  │ LANGUAGE: Respond in the SAME language...       │  ← from LangSmith
  │ STYLE: Keep responses under 150 words...        │
  │ ORDER SECURITY: Never fabricate order data...   │
  │                                                 │
  │ CUSTOMER: Fredi (fredi@test.com)                │  ← from JWT
  │ TOPIC: product_help                             │
  │                                                 │
  │ SHOP DATA:                                      │  ← from Shopware
  │ Varta A8 Silver Dynamic AGM 60Ah — €116.75      │
  │ Varta E23 Blue Dynamic 70Ah — €81.99            │
  │                                                 │
  │ KNOWLEDGE BASE:                                 │  ← from RAG
  │ Kostenloser Versand ab 49€...                   │
  │                                                 │
  │ SESSION ACTIVITY:                               │  ← from MongoDB
  │ [11:18] card_action: order_lookup               │
  │ [11:20] verification_failed: #99999             │
  │                                                 │
  │ INSTRUCTIONS: Lead immediately with matching    │  ← from intent
  │ products. Max 3-4 products...                   │
  └─────────────────────────────────────────────────┘
         │
         ▼
  Sent to Claude Haiku as system prompt
  + chat history as messages
  → Streamed response to customer
```

### The 19 Agents

```
  ┌─────────────────────┬──────────────────────────────┬──────┬──────────────┐
  │ Agent ID            │ Name                         │ Tier │ Mapped from  │
  ├─────────────────────┼──────────────────────────────┼──────┼──────────────┤
  │ order_status        │ Order Tracking Specialist    │  2   │ order_query  │
  │ returns             │ Returns & Refunds Agent      │  2   │ return_query │
  │ order_issue         │ Order Problem Resolver       │  2   │ —            │
  │ product_help        │ Product Expert               │  0   │ product_query│
  │ stock               │ Inventory Specialist         │  0   │ —            │
  │ compatibility       │ Vehicle Compatibility Expert │  0   │ —            │
  │ delivery_time       │ Delivery Time Advisor        │  0   │ —            │
  │ shipping_costs      │ Shipping Cost Calculator     │  0   │ —            │
  │ express_delivery    │ Express Delivery Specialist  │  0   │ —            │
  │ installation        │ Installation Guide Expert    │  0   │ —            │
  │ compatibility_check │ Technical Compatibility      │  0   │ —            │
  │ tech_specs          │ Technical Specs Expert       │  0   │ —            │
  │ payment             │ Payment Methods Advisor      │  1   │ —            │
  │ address             │ Address Management Helper    │  1   │ —            │
  │ invoice             │ Invoice & Receipts Agent     │  1   │ —            │
  │ faq                 │ FAQ & Policy Expert          │  0   │ —            │
  │ complaint           │ Complaint Resolution         │  1   │ —            │
  │ general             │ General Support Assistant    │  1   │ fallback     │
  └─────────────────────┴──────────────────────────────┴──────┴──────────────┘

  Tier 0 = No verification needed (open)
  Tier 1 = Name + email recommended
  Tier 2 = Order number + postcode required

  Auto-mapping (intent_classifier.py → topic_map):
    product_query  → product_help
    order_query    → order_status
    return_query   → returns
    customer_query → general
    direct / rag   → stays on current topic
```

### Why This Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │ "Why not put everything in LangSmith?"                      │
  │                                                             │
  │ LangSmith excels at:          Agents.py excels at:          │
  │ • Prompt iteration            • Structural config           │
  │ • A/B testing tone/style      • Version control (git)       │
  │ • No-deploy edits             • Type safety (Python)        │
  │ • Non-engineer editing        • One file, 19 agents         │
  │                               • Code review before deploy   │
  │                                                             │
  │ Agent personas define WHAT the agent knows — stable.        │
  │ Prompts define HOW the agent talks — iterable.              │
  │                                                             │
  │ You change the prompt weekly. You change agents yearly.     │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ "Why not put everything in MongoDB?"                        │
  │                                                             │
  │ API keys and credentials must NOT be in the database.       │
  │ config.yaml is gitignored, not exposed via API, and         │
  │ requires server access to edit — that's the right place     │
  │ for secrets.                                                │
  │                                                             │
  │ MongoDB stores runtime state that changes per session.      │
  │ config.yaml stores deployment config that changes per env.  │
  │ agents.py stores domain config that changes per release.    │
  └─────────────────────────────────────────────────────────────┘
```

### Code Files

```
  ┌──────────────────────────────────────────────┬──────────────────────────────┐
  │ File                                         │ Role                          │
  ├──────────────────────────────────────────────┼──────────────────────────────┤
  │ app/ai/agents.py                             │ 19 agent definitions          │
  │ app/ai/prompt_hub.py                         │ LangSmith pull + cache        │
  │ app/ai/graph/nodes/intent_classifier.py      │ Intent → agent mapping        │
  │ app/ai/graph/nodes/response_generator.py     │ Assembles final system prompt │
  │ config.yaml                                  │ API keys, thresholds, models  │
  │ scripts/push_prompts_to_langsmith.py         │ Seed/update LangSmith prompts │
  └──────────────────────────────────────────────┴──────────────────────────────┘
```

## Product Card & Document Download Flow

### Product Search Flow

```
  Customer: "Varta AGM Batterie"
         │
         ▼
  Card Router → "none" (general product question)
         │
         ▼
  AI Pipeline runs:
    1. Intent Classifier → product_query, search_query="Varta AGM"
    2. Data Fetcher → Store API search (with properties + sortedProperties)
    3. Card Context built → "PRODUCT CARD shown with: Varta A7 €131.85..."
    4. Response Generator → short intro (knows card is shown)
    5. Engine yields product_results
         │
         ▼
  Connection Handler:
    1. Detects _product_results → builds product card
    2. Replaces verbose AI response with short intro:
       "Ich habe 3 passende Produkte für dich gefunden:"
    3. Sends ai_card message (intro text + card in one bubble)
         │
         ▼
  Widget renders as ONE message:
  ┌─────────────────────────────────────────────┐
  │ Groot                                        │
  │ 🌿 Ich habe 3 passende Produkte für dich    │
  │    gefunden:                                 │
  │    ┌─────────────────────────────────────┐   │
  │    │ 🔍 3 passende Produkte              │   │
  │    │ Varta A7 AGM 70Ah                   │   │
  │    │ €131.85 ✅                           │   │
  │    │ 70Ah • 760 A • 12V                  │   │
  │    │ 🛒 Zum Produkt →                    │   │
  │    └─────────────────────────────────────┘   │
  └─────────────────────────────────────────────┘
```

### Product Document Flow

```
  Customer: "PDF für Varta A7"
         │
         ▼
  Card Router → "none" → AI Pipeline
         │
         ▼
  Intent Classifier → product_doc_query, search_query="Varta A7"
    (LLM strips "PDF" from search query, classifies as doc request)
         │
         ▼
  Data Fetcher → Store API finds Varta A7 product
         │
         ▼
  Connection Handler:
    1. Detects _intent == "product_doc_query"
    2. Finds best matching product by scoring name vs message
    3. Fetches product documents via Admin API:
       → product custom field mill_product_download_1 → media ID
       → media entity → file URL
    4. Sends ai_card with document card
         │
         ▼
  ┌─────────────────────────────────────────────┐
  │ Groot                                        │
  │ 🌿 Hier ist das Dokument für die Varta A7:  │
  │    ┌─────────────────────────────────────┐   │
  │    │ 📁 Produktdokumente                 │   │
  │    │ 📄 Datenblatt-Varta-A7 (147KB)      │   │
  │    └─────────────────────────────────────┘   │
  └─────────────────────────────────────────────┘
```

### Follow-Up Context Awareness

```
  Intent Classifier receives last 10 messages of history.

  Customer: "PDF für Varta A7"     → product_doc_query, q="Varta A7"
  Customer: "what about ea770?"    → product_doc_query, q="EA770"
                                     (maintains intent from context)
  Customer: "Danke"                → direct (switches back)

  FOLLOW-UP RULES in classifier prompt:
  - Previous doc request + "what about X?" → still product_doc_query
  - Previous order query + "when will it arrive?" → still order_query
  - Previous product discussion + "i want the manual" → product_doc_query
```

### Product URL Tracking & GA4 Attribution

```
  Every product link includes attribution parameters:

  https://voltimax.de/detail/{product_id}
    ?groot_ref=chat                    ← source: chat widget
    &groot_session={hash}              ← links to chat session
    &groot_campaign=product_recommendation

  For compatibility results:
    ?groot_ref=compatibility           ← source: vehicle finder
    &groot_session={hash}

  Why not UTM: UTM params override Google Ads attribution.
  Custom groot_* params coexist with existing UTM tracking.
```

### GA4 Ecommerce Tracking

```
  GA4 Measurement ID: G-SH7LY32R6E (via DIScoGA4 plugin)
  All events pushed to window.dataLayer

  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ Event                │ When / Data                                  │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ groot_chat_started   │ WebSocket auth_success + chat_id linked      │
  │                      │ params: groot_session, topic                 │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ view_item_list       │ Product card rendered in chat                │
  │                      │ item_list_id: groot_chat                     │
  │                      │ items[]: id, name, price, brand, variant     │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ select_item          │ Customer clicks product link in chat         │
  │                      │ items[]: same as view_item_list              │
  │                      │ Also sets groot_attribution cookie (30min)   │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ groot_conversion     │ Checkout finish page (if groot_attribution   │
  │                      │ cookie exists and is < 30min old)            │
  │                      │ params: order_number, order_total, currency, │
  │                      │ items_count, groot_session, groot_campaign   │
  └──────────────────────┴──────────────────────────────────────────────┘

  Funnel in GA4 Explore:
    view_item_list (groot_chat) → select_item (groot_chat) → groot_conversion

  Custom dimensions to register in GA4 Admin:
    groot_session, groot_ref, order_number (event scope)
    order_total (custom metric, event scope)
```

### Purchase Attribution Flow

```
  Customer sees product in chat
         │
         ▼ (widget fires view_item_list)
  Customer clicks product link
         │
         ▼ (widget fires select_item + sets groot_attribution cookie)
  Customer lands on product page
         │
         ▼ (base.html.twig detects groot_ref param, persists to cookie)
  Customer adds to cart → proceeds to checkout
         │
         ▼
  Checkout finish page:
    1. Reads groot_attribution cookie
    2. Validates < 30 min old
    3. Pushes groot_conversion to GA4 dataLayer
    4. POSTs to /api/webhooks/conversion (AI service dashboard)
    5. Clears cookie (prevent double-counting)

  Deduplication: conversions collection uses order_number as unique key.
  Dual tracking: GA4 (analytics) + MongoDB (dashboard) independently.
```

## Vehicle Compatibility Check Flow

```
  Customer: "Welche Batterie passt in meinen BMW?"
         │
         ▼
  Card Router → "compatibility_check"
         │
         ▼
  Connection Handler:
    1. Fetches Level 1 options from Shopware OncoCompatibilityFilter
       GET /onco-compatibility-get-children → [Auto, Motorrad]
    2. Sends ai_card with compatibility form
         │
         ▼
  ┌──────────────────────────────────────────────┐
  │ Groot                                         │
  │ 🌿 Lass uns die passende Batterie finden!    │
  │    ┌──────────────────────────────────────┐   │
  │    │ 🚗 Fahrzeug-Kompatibilitätscheck     │   │
  │    │                                      │   │
  │    │ Fahrzeugtyp:  [Auto            ▼]   │   │
  │    │ Hersteller:   [BMW             ▼]   │   │
  │    │ Modell:       [3er E90         ▼]   │   │
  │    │ Motor:        [2.0d 177PS      ▼]   │   │
  │    │                                      │   │
  │    │ [Passende Batterie finden →]         │   │
  │    └──────────────────────────────────────┘   │
  └──────────────────────────────────────────────┘

  Cascading dropdowns:
    Widget JS → fetch /api/compatibility/children?parent_id=X
    → Server B proxies to Shopware /onco-compatibility-get-children
    → Returns child options → populates next dropdown

  On submit:
    1. Server B → Admin API: query onco_compatibility_filter_link table
       → gets product IDs linked to the vehicle object
    2. Server B → Store API: fetch products by IDs with properties
    3. Shows product card with ⚠️ compatibility warning:
       "Bitte vergleichen Sie: Abmessungen, Polanordnung,
        Batterietechnologie, Bodenbefestigungsleiste"
```

## AI Card System (Unified Message + Card)

### How Cards Are Embedded in AI Messages

```
  All cards are delivered as type "ai_card" — intro text + card in one message.

  Server sends:
  {
    "type": "ai_card",
    "content": "Ich habe 3 passende Produkte...",
    "message_id": "abc-123",
    "info_card": { card_type: "dynamic", ... }
  }

  Widget renders as ONE bubble:
    voltimax-chat-ai-row
      ├── avatar (Groot tree icon, green/brown gradient)
      └── rowBody
           ├── "Groot" name label (olive green)
           ├── message bubble (voltimax-chat-message--ai)
           │    ├── intro text
           │    ├── card (embedded, no border overlap)
           │    └── timestamp
           └── feedback (thumbs up/down)
```

### When AI Pipeline Streams + Card Follows

```
  Problem: AI streams verbose tokens, but card needs short intro.

  Solution:
    1. AI pipeline streams tokens → widget buffers in _streamingRaw
    2. Server detects card_to_send → replaces full_response with short intro
    3. Server sends stream_end WITHOUT message_id → widget discards buffer
    4. Server sends ai_card message → widget renders intro + card
```

### Card Types and Their Intros

```
  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ Card                 │ Groot says                                    │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ Product card         │ "Ich habe X passende Produkte gefunden:"     │
  │ Document card        │ "Hier ist das Dokument für die [product]:"   │
  │ Tracking card        │ "Hier ist der Lieferstatus für #28418:"      │
  │ Payment card         │ "Hier ist der Zahlungsstatus für #28418:"    │
  │ Invoice card         │ "Hier sind die Dokumente für #28418:"        │
  │ Warranty card        │ "Hier sind die Garantieinformationen:"       │
  │ Order lookup form    │ "Ich brauche deine Bestelldaten:"            │
  │ No order card        │ "Ich kann dir auch ohne Bestellung helfen:"  │
  │ Another order        │ "Gib die Daten der anderen Bestellung ein:"  │
  │ Ticket lookup form   │ "Gerne prüfe ich den Status deines Tickets:" │
  │ Compatibility form   │ "Lass uns die passende Batterie finden:"     │
  │ Escalation form      │ "Ich erstelle ein Support-Ticket für dich:"  │
  │ Return/Problem form  │ "Bitte fülle das Formular aus:"              │
  └──────────────────────┴──────────────────────────────────────────────┘
```

### Card Context in AI System Prompt

```
  The AI knows what cards are shown via two mechanisms:

  1. CARD CONTEXT (current response):
     Built by data_fetcher after Shopware data is fetched.
     Injected into system prompt as:

     CARDS SHOWN WITH THIS RESPONSE:
     PRODUCT CARD shown with:
     - Varta A7 AGM 70Ah | €131.85 | available | 70Ah, 760 A, 12V
     - Exide EA770 77Ah | €75.10 | available | 77Ah, 760 A
     Each product has a 'Zum Produkt' link. Keep your response short.

  2. SESSION ACTIVITY (past events):
     From MongoDB session events array.
     Shows what happened before in the conversation.
```

## Chat Widget UX

### Groot Branding

```
  AI messages:
    🌿  Groot                          ← avatar + name
        ┌─────────────────────────┐
        │ Message text + card     │    ← full width bubble
        └─────────────────────────┘
        👍 👎                          ← feedback

  Typing indicator:
    🌿  ┌──────────────────────────┐
        │ Groot is typing ● ● ●   │   ← animated dots
        └──────────────────────────┘

  Customer messages:
                              Meet    ← customer first name
        ┌─────────────────────────┐
        │ Customer message        │   ← right aligned, indigo
        └─────────────────────────┘
```

### Smart Suggestions

```
  Suggestion chips shown above input:
  ▼ [Wo ist mein Paket?] [Produktfrage] [Retoure] [Versandkosten] [Rechnung] [Ticket] →

  - 6 card-backed topics (each maps to a card or AI action)
  - Horizontal scrollable, single row
  - Collapsible with ▼/▲ toggle
  - Sent by server based on customer profile (has_orders, is_b2b)
```

## Shopware CMS Sync & Knowledge Base

### What Gets Synced

```
  CMS sync fetches from the CONFIGURED sales channel only:

  Plugin config: VoltimaxChat → Sales Channel → [Voltimax]

  Sources synced:
  ┌─────────────────────────┬──────────┬──────────────────────────────┐
  │ Source                  │ Count    │ How                          │
  ├─────────────────────────┼──────────┼──────────────────────────────┤
  │ CMS pages               │ ~50      │ sections.blocks.slots text   │
  │ Product descriptions    │ ~50      │ product name + description   │
  │ Main navigation cats    │ ~100     │ category CMS page content    │
  │ Service navigation cats │ ~15      │ Batteriepfand, Widerruf etc. │
  │ Footer navigation cats  │ ~10      │ Impressum, Datenschutz etc.  │
  │ PDF documents           │ ~200+    │ Datasheets, forms, manuals   │
  ├─────────────────────────┼──────────┼──────────────────────────────┤
  │ Total                   │ ~10000+  │ chunks (text-embedding-3-large, │
  │                         │          │ overlap=100)                    │
  └─────────────────────────┴──────────┴──────────────────────────────┘

  PDF sync keywords: pfand, formular, widerruf, retoure, rueckgabe,
                     agb, Datenblatt, datenblatt, Data-Sheet, datasheet, anleitung
```

### Service/Footer Page Discovery

```
  Problem: Shopware 6 has 3 separate navigation trees.
  Service pages (Batteriepfand) were invisible to the old sync.

  Fix: CmsDataService.php now:
    1. Queries sales_channel.repository for serviceCategoryId + footerCategoryId
    2. Fetches categories from ALL trees (main + service + footer)
    3. Loads CMS page content via cmsPage.sections.blocks.slots association
    4. Extracts text + strips HTML tags

  sales_channel "Voltimax":
    navigationCategoryId  → main product categories
    serviceCategoryId     → Batteriepfand, Widerrufsrecht, Zahlung
    footerCategoryId      → Impressum, Datenschutz, AGB
```

### Product Document Downloads

```
  Documents linked to products via MillProductDownloadsTab plugin:

  product.customFields.mill_product_download_1 = media_id
    → Admin API: search media by ID
    → Get fileName, url, fileSize
    → Proxy download through Server B (/api/media/download)

  Two sync approaches:
    Bulk sync: Keywords search → embed PDF text into KB (for RAG answers)
    Dynamic fetch: Per-product lookup → show download card (for downloads)

  Download proxy:
    GET /api/media/download?url={shopware_internal_url}
    → Server B downloads from Docker Shopware
    → Streams to customer browser as PDF attachment
```

## Dashboard Pages

```
  ┌───────────────────┬────────────────────────────────────────────┐
  │ Page              │ Features                                    │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Overview          │ 9 KPI cards (clickable → /analytics/X),    │
  │                   │ Combined activity chart (6 toggleable       │
  │                   │ metrics), escalation reasons, star ratings  │
  │                   │ Active Now: real WebSocket count (10s poll) │
  │                   │ Cache Hit Rate KPI                          │
  │                   │ Session Close Reasons breakdown:            │
  │                   │   completed, idle_timeout, disconnected,    │
  │                   │   error, escalated                          │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Metric Detail     │ Line + bar charts, daily/monthly toggle,   │
  │ (/analytics/:id)  │ 7/30/90/365d periods, min/max/avg/total   │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Conversations     │ Session list, search, transcript viewer,   │
  │                   │ session events timeline, topic tags,        │
  │                   │ close_reason shown per session,             │
  │                   │ Event badges: Ticket/Verified/Failed/Switch │
  │                   │ Quick filters: status, has_ticket, tag      │
  │                   │ Clickable tags + status to filter           │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Products          │ Product recommendation analytics,           │
  │                   │ Conversion funnel: Shown → Purchased → €    │
  │                   │ Top recommended products table,             │
  │                   │ Recent purchases from chat table,           │
  │                   │ GA4 integration info banner                 │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Agents Config     │ 19 agent cards with test capability,       │
  │                   │ tier badges, search/filter, typing anim    │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Knowledge         │ KB stats, CMS sync, file upload, re-embed  │
  │                   │ button, Q&A pairs CRUD, embedding model     │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Prompts           │ 8 LangSmith prompts, cache status,         │
  │                   │ refresh button, Open LangSmith link         │
  ├───────────────────┼────────────────────────────────────────────┤
  │ Tickets           │ Zendesk tickets from Groot, customer info,  │
  │                   │ link to Zendesk dashboard                   │
  └───────────────────┴────────────────────────────────────────────┘
```

## Account Info Action

```
  Customer: "I want to know about my account" / "Mein Konto"
         │
         ▼
  Classifier → action=account_info
  (Safety: customer_query + escalation/none → forced to account_info)
  (No Shopware data fetched, no RAG retrieval)
         │
         ▼
  Direct response with login links:
  👉 Zum Kundenkonto (https://<SHOP>/account)
  - Adresse und persönliche Daten ändern
  - Passwort zurücksetzen
  - Bestellungen einsehen
  - Zahlungsmethoden verwalten
  👉 Passwort zurücksetzen (https://<SHOP>/account/recover/password)
```

## Clarify Action (Ambiguous Messages)

```
  Customer: "status" / "hilfe" / vague single word
         │
         ▼
  Classifier → action=clarify (too ambiguous to route)
         │
         ▼
  AI Pipeline runs with ASK_CLARIFICATION context:
  - Asks friendly follow-up with 2-3 concrete options
  - Example: "Meinst du den Status deiner Bestellung, eines
    Tickets, oder deines Kontos?"
  - Customer's next message re-classifies with full context
```

## GDPR Consent Logging

```
  Consent is logged in TWO databases for safety:

  1. Shopware MySQL (voltimax_chat_consent_log):
     - customer_name, customer_email (empty if anonymous)
     - ip_address, consented_at, sales_channel_id

  2. MongoDB (consent_log collection):
     - session_id, chat_id, customer_name, customer_email
     - consented_at

  Email handling:
  - Home screen: no email collected (anonymous start)
  - Session: customer_email = "" until provided
  - Ticket creation: form email updates session before creating ticket
  - Order verification: order's billing email stored on session
```

## Chat Widget UI (Glassmorphic Design)

```
  Floating bubble:
  - Dynamic Island style: expands on hover (56px → pill)
  - Hides when widget is open, shows on minimize/close
  - Morph animation: widget opens FROM bubble position

  Dynamic Island header:
  - Collapsed: compact pill (50% width), dot + title
  - Hover: expands to full width with actions
  - Gradient background with frosted glass overlay
  - Buttons: [expand] [three-dots menu] [minimize] [close]
  - Three-dots menu: new chat, copy transcript (body-mounted dropdown)

  Widget body:
  - Glassmorphic: rgba(255,255,255,0.78) + blur(20px)
  - 2px themed outline border
  - Expand/collapse between 370×600 and 480×85vh
  - Scroll containment (overscroll-behavior: contain)

  Messages:
  - Delivery status: Gesendet → Zugestellt → Gelesen
  - Groot avatar: 20px, no background, brand gradient
  - AI bubbles: semi-transparent (rgba 0.75)

  Input:
  - Pill shape with indigo border, gold on focus
  - Gradient circular send button
  - No double border, transparent background

  Rating:
  - Compact floating bubble (not full overlay)
  - Morphs from widget → rating pill → thank you → collapses into bubble

  Home screen:
  - Name only (no email)
  - 14 suggestion chips covering all card actions
  - Matching pill input with gradient send button
  - Flying message animation on send

  Dev mode:
  - Cookie-based: ?groot_dev=SECRET sets 30-day cookie
  - ?groot_dev=off clears cookie, hides widget
  - Config: devModeEnabled + devModeSecret in plugin config
  - No IP whitelist (avoids IPv6 rotation issues)

  Session persistence:
  - sessionStorage saves after every message
  - Restores on page navigation
  - Auto-resends interrupted messages
  - Bubble always rendered (even after session restore)

  Auth error handling:
  - 401/token expired → silently resets to home screen
  - Stops reconnect loop, clears stale session
```

## MongoDB Collections (Complete)

```
  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ Collection           │ Purpose                                      │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ chat_sessions        │ Active/closed sessions with customer info,   │
  │                      │ topic, events, order data, chat_id           │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ chat_messages        │ Full message history per session             │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ knowledge_vectors    │ Embedded document chunks for RAG             │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ knowledge_sources    │ Source metadata (files, CMS pages)           │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ qa_pairs             │ Exact Q&A pairs (highest priority match)     │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ analytics_events     │ Session metrics, response times, tokens      │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ admin_config         │ Dashboard-editable settings (LLM routing)    │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ consent_log          │ GDPR consent records (mirrors Shopware DB)   │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ conversions          │ Purchase conversions attributed to chat      │
  │                      │ Fields: order_number, order_total, currency, │
  │                      │ groot_session, groot_campaign, created_at    │
  │                      │ Deduped by order_number                     │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ logs                 │ Application logs                             │
  └──────────────────────┴──────────────────────────────────────────────┘
```

## Vector Search Fallback

```
  Primary: MongoDB $vectorSearch (atlas-local only)
  Fallback: Python-side cosine similarity (any MongoDB)

  Search flow:
  1. Try $vectorSearch → if results, return
  2. If $vectorSearch fails (mongo:7, no index):
     → Fetch all embeddings from MongoDB
     → Compute cosine similarity in Python
     → Sort by score, return top_k
  
  Ensures RAG works on both local (atlas-local) and
  production (standard mongo:7 or atlas-local).
```

## MongoDB atlas-local Docker Config

```
  IMPORTANT: atlas-local generates a random replica set name from
  its container ID on each start. This causes RSGhost errors if the
  data volume has a stale replica set config from a previous container.

  Prevention:
  1. Always use directConnection=true in the MongoDB URI
  2. Use Docker volumes (not bind mounts) for /data/db
  3. /data/configdb uses a named volume (atlas-local writes its keyfile here)
  4. privileged: true required for keyfile permissions on Linux
  5. Backup with mongodump (NOT volume tar) — volume backups include
     the replica set config and will fail on restore to a new container

  Backup (safe — logical dump, portable):
    docker compose exec -T mongo mongodump --db voltimax_chat --archive > backup.archive

  Restore:
    docker compose exec -T mongo mongorestore --archive < backup.archive

  DO NOT backup via:
    tar czf backup.tar.gz /data/db   ← includes replica set config = breaks on restore
```
