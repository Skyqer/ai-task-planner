# 🤖 AI Task Planner — Telegram Bot

> Personal AI task planner in Telegram with voice input, intelligent scheduling, and weather forecast.

Send the bot a text or voice message — it will extract tasks, set priorities, build a daily schedule, and remind you of deadlines on time. All business logic (priorities, deadlines, dependencies) works deterministically — the LLM is used only for natural language understanding.

---

## ✨ Features

### 🧠 AI Core (Natural Language Understanding)
- **Natural language understanding** — write however you like: *"Submit math assignment tomorrow by 16:00"*, *"Need to buy milk"* — the bot will extract the task, deadline, priority, and category itself.
- **Three LLM providers to choose from**: Google AI Studio (Gemini — **recommended**, as it works significantly faster), OpenRouter (cloud, dozens of models), or Ollama (local, full privacy).
- **Structured JSON output** — LLM returns a strictly typed response parsed via Pydantic schemas.
- **Contextual memory** — the bot remembers previous messages and automatically compresses history to avoid overloading the context window.

### 🎙 Voice Input (Whisper STT)
- **Voice recognition** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (SYSTRAN/faster-whisper) — an optimized CTranslate2 implementation of the OpenAI Whisper model.
- Automatic language detection (Russian, Ukrainian, English).
- If recognition confidence is low, the bot asks for confirmation before processing.
- Audio conversion from OGG to WAV via **ffmpeg**.

### 📋 Task Management
- **CRUD** — create, view, complete, cancel, delete tasks.
- **Inline buttons** — ✅ Complete / 🗑 Delete right under the task list.
- **Task categories**: `study`, `home`, `health`, `errand`, `sport`, `work`, `other`.
- **Priorities 1–5** with color indication (⚪🟢🟡🟠🔴).
- **Deadlines** (hard / soft) and **fixed time** for strict events.
- **Soft delete** — tasks are not erased from the DB but marked as deleted.

### 🔄 Recurring Tasks
- Patterns: `daily`, `weekly:mon,wed,fri`, `monthly:15`.
- Automatic creation of instances on schedule (APScheduler).
- Management via `/recurring` with inline buttons.

### 📅 Intelligent Scheduling (Timeline Engine)
- **Hard constraints** — sleep, school/work, focus, etc. The bot knows when you are unavailable and doesn't schedule tasks during blocked time.
- **Voice management of constraints** — say *"I no longer go to school"* or *"I sleep from 12 to 9"*, and the bot will update the schedule.
- **Free windows** — automatic calculation of available time visualized with the `/timeline` command.
- **Energy profile** — accounting for biological rhythms (early bird / night owl). Important tasks are placed during peak activity hours.
- **Greedy placement algorithm** — tasks are placed in free windows considering priority, duration, and energy.

### ⚡ Smart Priority Engine
- **Deterministic rules** (without LLM):
  - Fixed time today → minimum priority 4
  - Deadline in the next 2 hours → priority 5
  - Deadline today → 4–5
  - Keywords like "urgent", "must" → priority boost
- **Conflict detection** — if two tasks overlap in time, the bot will warn you.
- **Auto-detection of overdue tasks** — tasks with expired deadlines are marked as overdue.

### 🔗 Task Dependencies
- Creating chains: *"Task B depends on Task A"*.
- **Cycle protection** — DFS graph traversal prevents impossible loops.
- **Completion blocking** — a task cannot be marked as completed until its dependencies are finished.

### 🌦 Weather Integration
- **OpenWeatherMap API** — up-to-date forecast with caching (30 min TTL).
- **Morning brief** — temperature, precipitation, wind upon requesting the daily plan.
- **Weather-sensitive tasks** — if a task is marked as `weather_sensitive` (running, walking) and the forecast predicts rain, the bot will warn and suggest rescheduling.

### 📊 Statistics and Analytics
- Command `/stats` — complete summary:
  - ✅ Completed / ❌ Cancelled / ⏳ Overdue
  - 🔥 Streak (consecutive days with completed tasks)
  - ⏱ Average time per task
  - 🗂 Breakdown by categories
- Filtering: `today`, `week`, `month`, `all_time`.

### ⏰ Reminders and Automation
- Automatic reminder creation 2 hours before a deadline / fixed time.
- Inline button **"✅ Got it"** for acknowledgment.
- Background jobs (APScheduler):
  - Checking upcoming deadlines (every 15 min)
  - Sending pending reminders (every minute)
  - Creating recurring task instances (every hour)
  - Task rescheduling suggestions (every 30 min)
  - Old messages cleanup (daily)

### 🔀 Auto-Rescheduling
- `ReschedulerService` analyzes the schedule and suggests rescheduling tasks if a window becomes unavailable.
- The suggestion is sent to Telegram with buttons **"✅ Agree"** / **"❌ Leave as is"**.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Transport Layer                       │
│  ┌─────────────────┐        ┌────────────────────────┐  │
│  │   Telegram Bot   │        │     REST API (FastAPI)  │  │
│  │  (aiogram 3.x)   │        │  POST /api/plan         │  │
│  └────────┬─────────┘        └──────────┬─────────────┘  │
│           │                              │                │
│           └──────────┬───────────────────┘                │
│                      ▼                                    │
│  ┌───────────────────────────────────────────────────┐   │
│  │              Core Planner (Orchestrator)            │   │
│  │  LLM → Parse → PriorityEngine → Save → Respond    │   │
│  └──────────────────────┬────────────────────────────┘   │
│                          │                                │
│  ┌───────────┬───────────┼───────────┬──────────────┐    │
│  ▼           ▼           ▼           ▼              ▼    │
│ Memory   Timeline   Constraints  Weather   Statistics    │
│ Manager   Engine     Service     Service    Service       │
│                                                           │
│  ┌──────────┬──────────┬──────────┬──────────────────┐   │
│  ▼          ▼          ▼          ▼                   ▼   │
│ Energy   Dependency  Rescheduler  Routine   Scheduler    │
│ Service   Service     Service    Learner    Service       │
└──────────────────────┬──────────────────────────────────┘
                       ▼
              ┌─────────────────┐
              │   PostgreSQL    │
              │  (SQLAlchemy    │
              │   + asyncpg)    │
              └─────────────────┘
```

**Key Principles:**
- **LLM is strictly for NLU.** All business logic (priorities, deadlines, conflicts, dependencies) is deterministic.
- **Layer Separation.** Transport knows nothing about Storage. Core Services know nothing about Telegram.
- **Dependency Injection.** Uses `aiogram.BaseMiddleware` (`DependencyMiddleware`, `DatabaseMiddleware`) for safely injecting services and DB sessions into handlers without global variables.

---

## 📂 Project Structure

```
.
├── main.py                          # Entry point (uvicorn runner)
├── bot_polling.py                   # Dedicated local bot polling script
├── app/
│   ├── main.py                      # FastAPI app + lifespan (DI)
│   ├── config.py                    # pydantic-settings config
│   ├── db/
│   │   ├── engine.py                # SQLAlchemy async engine
│   │   └── repository.py           # All DB CRUD operations
│   ├── llm/
│   │   ├── base.py                  # Abstract BaseLLMProvider
│   │   ├── openrouter.py            # OpenRouter (OpenAI-compatible API)
│   │   ├── ollama.py                # Ollama (local LLM)
│   │   ├── factory.py               # Provider factory
│   │   └── prompts.py               # System prompt for LLM
│   ├── models/
│   │   ├── task.py                  # TaskORM, RecurrenceORM
│   │   ├── user.py                  # UserORM (with energy_profile)
│   │   ├── message.py              # MessageORM, MemorySummaryORM
│   │   ├── constraint.py           # UserConstraintORM
│   │   ├── dependency.py           # TaskDependencyORM
│   │   ├── reminder.py             # ReminderORM
│   │   └── routine.py              # TaskCompletionLogORM
│   ├── schemas/                     # Pydantic models (I/O validation)
│   ├── services/
│   │   ├── planner.py              # CorePlanner — main orchestrator
│   │   ├── priority.py             # PriorityEngine (deterministic)
│   │   ├── timeline.py             # TimelineEngine (daily schedule)
│   │   ├── constraints.py          # Constraints management
│   │   ├── dependencies.py         # Task dependencies + cycle detection
│   │   ├── energy.py               # Biorhythms / energy profile
│   │   ├── weather.py              # OpenWeatherMap integration
│   │   ├── voice.py                # Whisper STT
│   │   ├── memory.py               # Context memory (3-tier)
│   │   ├── scheduler.py            # APScheduler (background jobs)
│   │   ├── statistics.py           # Analytics and metrics
│   │   ├── rescheduler.py          # Auto-rescheduling tasks
│   │   └── routine.py              # Routine learning
│   └── transport/
│       ├── api/routes.py            # REST endpoints
│       └── telegram/
│           ├── bot.py               # Bot + Dispatcher creation
│           ├── middlewares.py       # Aiogram DI middlewares
│           ├── states.py            # FSM states
│           ├── handlers.py          # All command and message handlers
│           ├── formatter.py         # Telegram formatting
│           └── callbacks.py         # Callback data for inline buttons
├── tests/                           # 40 unit tests (pytest + pytest-asyncio)
├── alembic/                         # Database migrations
├── Dockerfile                       # Production image
├── docker-compose.yml               # App + PostgreSQL
├── pyproject.toml                   # Dependencies (uv)
└── .env.example                     # Example configuration
```

---

## 🚀 Quick Start

### Requirements

- Python **3.14+**
- PostgreSQL **16+**
- [uv](https://docs.astral.sh/uv/) — package manager
- [ffmpeg](https://ffmpeg.org/) — for voice messages

### 1. Clone and Setup

```bash
git clone https://github.com/Skyqer/ai-task-planner.git
cd ai-task-planner

# Install dependencies
uv sync

# Create .env
cp .env.example .env
```

### 2. Configure `.env`

```env
# === Required ===
TELEGRAM_BOT_TOKEN=123456789:ABCdef...      # @BotFather
DATABASE_URL=postgresql+asyncpg://planner:planner_secret@127.0.0.1:55432/planner

# === LLM (choose one) ===
LLM_PROVIDER=google                          # "google", "openrouter" or "ollama"

# Google (Recommended — works the fastest)
GOOGLE_API_KEY=AIzaSy...                     # https://aistudio.google.com/
GOOGLE_MODEL=gemini-3.1-flash-lite-preview

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...              # https://openrouter.ai/keys
OPENROUTER_MODEL=deepseek/deepseek-r1:free   # or any other model

# === Weather (optional) ===
OPENWEATHER_API_KEY=your_key                 # https://openweathermap.org/api
WEATHER_CITY=Kyiv
WEATHER_COUNTRY=UA

# === Voice ===
WHISPER_MODEL_SIZE=base                       # tiny, base, small, medium, large
```

### 3. Start Database

```bash
docker compose up -d postgres
```

### 4. Start Application

If you use the Telegram Bot in webhook mode alongside FastAPI:
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

For local development (in long-polling mode), run the bot using the standalone script:
```bash
uv run python bot_polling.py
```

### 5. Start via Docker (production)

```bash
docker compose up -d --build
```

---

## 🤖 Bot Commands

| Command | Description |
|---------|----------|
| `/start` | Registration + welcome |
| `/tasks` | Active tasks list with inline buttons |
| `/done <number>` | Mark task as completed |
| `/cancel <number>` | Cancel task |
| `/delete <number>` | Delete task |
| `/morning` | Morning brief (weather + day plan) |
| `/timeline` | Day schedule (constraints + free windows) |
| `/recurring` | Manage recurring tasks |
| `/stats` | Statistics (today / week / month / all_time) |
| `/help` | Show full list of commands |

**Quick Action Buttons (Main Menu):**
- 📋 **My tasks** → `/tasks`
- 🌅 **My day** → `/morning`
- 📅 **Schedule** → `/timeline`
- 🔄 **Recurring** → `/recurring`
- 📊 **Statistics** → `/stats`
- ❓ **Help** → `/help`

---

## 🧪 Testing

```bash
# All tests
uv run pytest

# With detailed output
uv run pytest -v

# Specific module
uv run pytest tests/test_priority.py -v
```

**Coverage**: 40 tests — constraints, dependencies, energy, LLM-parsing, memory, priority, recurring, rescheduler, routine, schemas, statistics, weather.

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | FastAPI + Uvicorn |
| **Telegram** | aiogram 3.x |
| **LLM** | OpenAI SDK (Google AI Studio / OpenRouter / Ollama) |
| **Speech-to-Text** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI Whisper, CTranslate2) |
| **Database** | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| **Migrations** | Alembic |
| **Scheduler** | APScheduler (AsyncIOScheduler) |
| **Weather** | OpenWeatherMap API |
| **HTTP client** | httpx |
| **Validation** | Pydantic v2 |
| **Configuration** | pydantic-settings + .env |
| **Package Manager** | uv |
| **Linter** | Ruff |
| **Tests** | pytest + pytest-asyncio |
| **Containerization** | Docker + Docker Compose |

---

## 📝 License

MIT
