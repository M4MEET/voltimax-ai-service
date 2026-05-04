# VoltimaxChat AI Service (Groot)

AI-powered customer support chatbot for [voltimax.de](https://voltimax.de) — a German battery, solar, and electronics shop.

## Architecture

```
Shopware 6 (Plugin)          AI Service (FastAPI)         External
┌──────────────────┐         ┌──────────────────┐        ┌──────────┐
│ Chat Widget (JS) │◄───────►│ WebSocket Server │───────►│ LangSmith│
│ PHP Controllers  │  WS     │ Unified Classifier│       │ Anthropic│
│ JWT Issuer       │         │ LangGraph Pipeline│       │ OpenAI   │
│ Store API        │◄───────►│ RAG (MongoDB)     │       │ Zendesk  │
│ CheaperAd Plugin │  REST   │ React Dashboard   │       └──────────┘
└──────────────────┘         └────────┬──────────┘
                                      │
                             ┌────────▼──────────┐
                             │ MongoDB            │
                             │ (sessions, vectors,│
                             │  analytics, logs)  │
                             └───────────────────┘
```

## Features

- **Real-time chat** via WebSocket with streaming AI responses
- **Unified LLM classifier** — single call for intent, card action, search query, and complexity
- **Smart model routing** — Haiku for simple queries, Sonnet for complex/frustrated customers
- **Product search** with Shopware Store API integration, delivery times, and cheaper alternative suggestions
- **Vehicle compatibility check** via OncoCompatibilityFilter plugin
- **Order verification** with postcode matching
- **RAG knowledge base** — 10K+ vectors from CMS, PDFs, and policies (OpenAI embeddings)
- **Semantic response cache** — avoids repeated LLM calls for similar questions
- **Conversation summarization** for long chats
- **Batteriepfand flow** — form download, upload, and Zendesk ticket creation with attachments
- **Zendesk integration** — ticket creation, lookup, urgent escalation
- **LangSmith tracing** with `@traceable` on all pipeline functions
- **Online evaluators** — conciseness, language match, hallucination detection
- **React analytics dashboard** with KPIs, charts, conversation viewer

## Prerequisites

- Python 3.11+
- MongoDB 6.0+ (with Atlas Vector Search index)
- Node.js 18+ (for dashboard build)
- Shopware 6.6+ with VoltimaxChat plugin installed

## Quick Start (Local Development)

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd voltimax-ai-service

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env           # Edit with your API keys
cp config.example.yaml config.yaml  # Edit with your credentials

# 5. Start MongoDB (if not using Docker)
mongod --dbpath /data/db

# 6. Build the dashboard
cd dashboard-react && npm install && npm run build && cd ..

# 7. Start the service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The service is now available at:
- **API**: http://localhost:8000
- **Health**: http://localhost:8000/health
- **Dashboard**: http://localhost:8000/dashboard
- **WebSocket**: ws://localhost:8000/ws/chat

## Docker Deployment

```bash
# 1. Configure environment
cp .env.example .env
cp config.example.yaml config.yaml
# Edit both files with your production values

# 2. Build and start
docker compose up -d --build

# 3. Verify
curl http://localhost:8000/health
```

### Services

| Service | Port | Purpose |
|---------|------|---------|
| voltimax-ai | 8000 | FastAPI + Dashboard |
| mongo | 27017 | MongoDB |
| mongo-express | 8081 | MongoDB UI |

## Configuration

### Environment Variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URI` | Yes | MongoDB connection string |
| `CONFIG_PATH` | Yes | Path to config.yaml |
| `LANGCHAIN_API_KEY` | Yes | LangSmith API key for tracing |
| `LANGSMITH_TRACING` | Yes | Set to `true` to enable tracing |
| `LANGCHAIN_PROJECT` | Yes | LangSmith project name |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key (for LangGraph Studio) |
| `OPENAI_API_KEY` | Yes | OpenAI API key (for embeddings) |

### Config File (config.yaml)

See `config.example.yaml` for all options. Key sections:

- **shopware** — Shopware API connection (admin + store API keys)
- **llm_providers** — LLM API keys and model selection (Haiku + Sonnet)
- **knowledge_base** — Embedding model and chunk settings
- **escalation** — Zendesk credentials and SMTP config
- **jwt** — Secret must match Shopware plugin

## Knowledge Base

### Initial Sync

```bash
# Sync CMS content from Shopware (categories, pages, PDFs)
curl -X POST http://localhost:8000/api/knowledge/sync-cms

# Re-embed all vectors (after changing embedding model or chunk settings)
venv/bin/python scripts/reembed_knowledge.py
```

### Push Prompts to LangSmith

```bash
venv/bin/python scripts/push_prompts_to_langsmith.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check + cache stats |
| WS | `/ws/chat` | WebSocket chat endpoint |
| POST | `/api/knowledge/sync-cms` | Sync CMS content |
| POST | `/api/chat/batteriepfand-upload` | Batteriepfand form upload |
| POST | `/cache/clear` | Clear semantic cache |
| GET | `/api/analytics/overview` | Dashboard overview data |
| GET | `/api/admin/llm-config` | LLM provider config |

## Dashboard

The React dashboard is served at `/dashboard` by FastAPI.

```bash
# Development (hot reload)
cd dashboard-react
npm install
npm run dev -- --port 3001

# Production build
npm run build    # Output → ../dashboard-build/
```

## Project Structure

```
app/
  ai/                  # AI pipeline
    unified_classifier.py   # Single LLM call: intent + action + complexity
    semantic_cache.py       # Response caching by embedding similarity
    conversation_summarizer.py
    suggestion_engine.py    # Context-aware follow-up suggestions
    card_builder.py         # Dynamic card schemas
    graph/                  # LangGraph pipeline nodes
      nodes/
        intent_classifier.py
        data_fetcher.py
        rag_retriever.py
        response_generator.py
  api/routes/          # REST API endpoints
  chat/                # WebSocket connection handler
  escalation/          # Zendesk ticket creation
  knowledge/           # RAG vector store + embeddings
  shopware/            # Shopware API client
dashboard-react/       # React analytics dashboard
scripts/               # Utility scripts
static/forms/          # Batteriepfand PDF forms
docs/                  # Architecture documentation
```

## Post-Deployment Checklist

- [ ] Rotate all API keys if they were ever committed to git
- [ ] Configure MongoDB Atlas Vector Search index (`vector_index` on `knowledge_vectors.embedding`)
- [ ] Run CMS sync (`POST /api/knowledge/sync-cms`)
- [ ] Push prompts to LangSmith (`scripts/push_prompts_to_langsmith.py`)
- [ ] Verify Shopware plugin JWT secret matches `config.yaml`
- [ ] Test WebSocket connection from Shopware storefront
- [ ] Configure Zendesk credentials for ticket creation
- [ ] Set up SMTP for email notifications (optional)

## License

Proprietary - Meet Joshi
