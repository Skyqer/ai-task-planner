# 🤖 AI Task Planner — Telegram Bot

> Personal AI task planner in Telegram with voice input, intelligent scheduling, automatic descriptions, and weather forecast.

Send the bot a text or voice message — it will extract tasks, generate descriptions, set priorities, build a daily schedule, and remind you of deadlines on time. All business logic (priorities, deadlines, dependencies) works deterministically — the LLM is used only for natural language understanding.

---

## ✨ Features

### 🧠 AI Core (Natural Language Understanding)
- **Natural language understanding** — write however you like: *"Submit math assignment tomorrow by 16:00"*, *"Need to buy milk"* — the bot will extract the task, deadline, priority, and category itself.
- **Auto-generated task descriptions** — if you don't provide a description, the AI will generate a concise 1–2 sentence description based on context. If you describe the task, that description is used as-is.
- **Three LLM providers to choose from**: Google AI Studio (Gemini — **recommended**, fastest), OpenRouter (cloud, dozens of models), or Ollama (local, full privacy).
- **Structured JSON output** — LLM returns a strictly typed response parsed via Pydantic schemas. Robust parsing handles `<thought>` blocks and markdown fences that some models emit.
- **Contextual memory** — the bot remembers previous messages and automatically compresses history to avoid overloading the context window. Three-tier architecture: recent messages → summarized context → active tasks.
- **Two operational modes** — `task_input` (adding/editing tasks) and `morning_brief` (daily plan with weather and priorities) — detected automatically from user input.

### 🎙 Voice Input (Whisper STT)
- **Voice recognition** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — an optimized CTranslate2 implementation of the OpenAI Whisper model.
- Automatic language detection (Russian, Ukrainian, English).
- If recognition confidence is low, the bot asks for confirmation with inline buttons before processing.
- **Lazy model loading** — the Whisper model is loaded only on the first voice message, not at startup.
- **Auto-unload** — model is evicted from RAM after configurable idle timeout (`WHISPER_UNLOAD_SECONDS`, default 120s) to free memory. Set to `0` to keep model loaded permanently.
- **Memory tracking** — detailed logging of RAM usage during model loading, inference, and unloading. Peak memory tracker runs on a background thread.
- **Toggleable** — disable voice entirely via `WHISPER_ENABLED=false` to skip loading the Whisper dependency.

### 📋 Task Management
- **CRUD** — create, view, complete, cancel, delete tasks.
- **Task descriptions** — every task has a description (max 250 words). The AI auto-generates one if you don't provide it.
- **Edit descriptions** — use `/describe <number> <text>` to add or update a task's description at any time.
- **Inline buttons** — ✅ Complete / 🗑 Delete right under the task list.
- **Task categories**: `study`, `home`, `health`, `errand`, `sport`, `work`, `other`.
- **Priorities 1–5** with color indication (⚪🟢🟡🟠🔴).
- **Deadlines** (hard / soft) and **fixed time** for strict events.
- **Soft delete** — tasks are not erased from the DB but marked as deleted.

### 🔄 Recurring Tasks
- Patterns: `daily`, `workdays`, `weekly:mon,wed,fri`, `monthly:15`.
- Automatic creation of instances on schedule (APScheduler).
- Management via `/recurring` with inline buttons.

### 📅 Intelligent Scheduling (Timeline Engine)
- **Hard constraints** — sleep, school/work, focus, etc. The bot knows when you are unavailable and doesn't schedule tasks during blocked time.
- **Voice management of constraints** — say *"I no longer go to school"* or *"I sleep from 12 to 9"*, and the bot will update the schedule. The LLM returns `deleted_constraints` / `added_constraints` in JSON, and the planner applies them deterministically.
- **Free windows** — automatic calculation of available time visualized with the `/timeline` command.
- **Energy profile** — accounting for biological rhythms (early bird / night owl). Important tasks are placed during peak activity hours. Customizable per-user profile with hourly energy levels (1–5).
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
- Command `/stats sys` — system diagnostics: uptime, RAM usage, user count, task count, Whisper status.

### ⏰ Reminders and Automation
- Automatic reminder creation 2 hours before a deadline / fixed time.
- Inline button **"✅ Got it"** for acknowledgment.
- **Smart reminder suppression** — reminders are automatically skipped and acknowledged if the task was already completed, cancelled, or deleted.
- **Deduplication** — reminders are marked as sent in the DB *before* delivery, preventing duplicate Telegram messages even if multiple scheduler ticks overlap.
- **Retry with cooldown** — non-acknowledged reminders are resent every 30 minutes.
- Background jobs (APScheduler):
  - Checking upcoming deadlines (every 15 min)
  - Sending pending reminders (every minute)
  - Creating recurring task instances (every hour)
  - Task rescheduling suggestions (every 2 hours)
  - Old messages cleanup (daily at 03:00)

### 🔀 Auto-Rescheduling
- `ReschedulerService` analyzes the schedule and suggests rescheduling overdue tasks to the nearest free window (today or tomorrow).
- The suggestion is sent to Telegram with buttons **"✅ Agree"** / **"❌ Leave as is"**.
- Greedy algorithm maps overdue tasks to available free windows considering estimated duration.

### 🚨 Error Notifications
- **Telegram Error Handler** — all `ERROR` and `CRITICAL` log events are forwarded to an admin chat in Telegram.
- **Deduplication** — identical errors are suppressed for 5 minutes to prevent notification storms.
- **Rate limiting** — maximum 10 messages per minute to the admin chat.
- **Formatted reports** — each error message includes module, function, error text, truncated traceback, and timestamp.
- Configured via `TELEGRAM_ADMIN_CHAT_ID` in `.env`.

### 📝 Structured Logging
- Clean, compact log format with timestamps and level labels.
- **LoggingMiddleware** logs every incoming message/voice/button press with username, content preview, and end-to-end processing time in milliseconds.
- Noisy third-party logs (APScheduler, aiogram.event, httpx, watchfiles) are silenced so only meaningful events appear.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Transport Layer                       │
│  ┌─────────────────┐        ┌────────────────────────┐  │
│  │   Telegram Bot   │        │     REST API (FastAPI)  │  │
│  │  (aiogram 3.x)   │        │  /api/v1/message       │  │
│  │  polling/webhook  │        │  /api/v1/tasks         │  │
│  └────────┬─────────┘        └──────────┬─────────────┘  │
│           │  LoggingMiddleware            │                │
│           │  DatabaseMiddleware           │                │
│           │  DependencyMiddleware         │                │
│           └──────────┬───────────────────┘                │
│                      ▼                                    │
│  ┌───────────────────────────────────────────────────┐   │
│  │              Core Planner (Orchestrator)           │   │
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
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  ▼                                                   ▼    │
│ Error Notifier              Voice (Whisper STT)           │
│ (TelegramErrorHandler)      (lazy load + auto-unload)     │
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
- **Dependency Injection.** Uses `aiogram.BaseMiddleware` (`LoggingMiddleware`, `DependencyMiddleware`, `DatabaseMiddleware`) for safely injecting services and DB sessions into handlers without global variables.
- **Dual start mode.** `uv run python main.py` starts FastAPI + Telegram polling + APScheduler in one process (with `--reload`). `bot_polling.py` is a lightweight alternative for standalone bot-only mode.
- **Webhook support.** Set `BOT_MODE=webhook` and `WEBHOOK_URL` to use Telegram webhooks instead of long-polling.

---

## 📂 Project Structure

```
.
├── main.py                          # Entry point (uvicorn + reload)
├── bot_polling.py                   # Standalone polling script (alternative)
├── app/
│   ├── main.py                      # FastAPI app + lifespan (DI, middleware, scheduler)
│   ├── config.py                    # pydantic-settings config
│   ├── db/
│   │   ├── engine.py                # SQLAlchemy async engine
│   │   └── repository.py           # All DB CRUD operations
│   ├── llm/
│   │   ├── base.py                  # Abstract BaseLLMProvider + robust JSON parser
│   │   ├── google.py                # Google AI Studio (Gemini, OpenAI-compatible)
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
│   │   ├── planner.py              # PlannerResponseSchema (main LLM output)
│   │   ├── task.py                 # Task-related schemas
│   │   ├── constraint.py           # Constraint schemas
│   │   ├── timeline.py             # DayTimelineSchema
│   │   ├── rescheduler.py          # RescheduleSuggestion
│   │   ├── statistics.py           # UserStats
│   │   ├── weather.py              # WeatherData
│   │   ├── voice.py                # TranscriptionResult
│   │   └── reminder.py             # Reminder schemas
│   ├── services/
│   │   ├── planner.py              # CorePlanner — main orchestrator
│   │   ├── priority.py             # PriorityEngine (deterministic)
│   │   ├── timeline.py             # TimelineEngine (daily schedule)
│   │   ├── constraints.py          # Constraints management
│   │   ├── dependencies.py         # Task dependencies + cycle detection
│   │   ├── energy.py               # Biorhythms / energy profile
│   │   ├── weather.py              # OpenWeatherMap integration
│   │   ├── voice.py                # Whisper STT (lazy load + auto-unload)
│   │   ├── memory.py               # Context memory (3-tier)
│   │   ├── scheduler.py            # APScheduler (background jobs)
│   │   ├── reminder.py             # Reminder scheduling per task
│   │   ├── statistics.py           # Analytics and metrics
│   │   ├── rescheduler.py          # Auto-rescheduling overdue tasks
│   │   └── routine.py              # Routine learning
│   ├── utils/
│   │   ├── time_parser.py          # Safe time string parsing
│   │   └── timezone.py             # Timezone helpers (now_local, get_local_timezone)
│   └── transport/
│       ├── api/routes.py            # REST endpoints (/api/v1/*)
│       └── telegram/
│           ├── bot.py               # Bot + Dispatcher creation
│           ├── middlewares.py       # LoggingMiddleware, DatabaseMiddleware, DependencyMiddleware
│           ├── states.py            # FSM states (VoiceInputState)
│           ├── handlers.py          # All command and message handlers
│           ├── formatter.py         # Telegram formatting + keyboard builders
│           ├── callbacks.py         # CallbackData schemas for inline buttons
│           └── error_notifier.py   # ERROR/CRITICAL → admin Telegram chat
├── tests/                           # Unit tests (pytest + pytest-asyncio)
├── alembic/                         # Database migrations
├── Dockerfile                       # Production image (python:3.14-slim + uv)
├── docker-compose.yml               # App + PostgreSQL + Whisper cache volume
├── pyproject.toml                   # Dependencies (uv)
└── .env.example                     # Example configuration
```

---

## 🚀 Quick Start

### Requirements

- Python **3.14+**
- PostgreSQL **16+**
- [uv](https://docs.astral.sh/uv/) — package manager

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

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# === Telegram ===
TELEGRAM_ADMIN_CHAT_ID=123456789             # Your chat ID for ERROR/CRITICAL notifications
BOT_MODE=polling                              # "polling" or "webhook"
# WEBHOOK_URL=https://your-domain.com         # Required if BOT_MODE=webhook
# WEBHOOK_SECRET=your_secret                  # Optional webhook security token

# === Weather (optional) ===
OPENWEATHER_API_KEY=your_key                 # https://openweathermap.org/api
WEATHER_CITY=Kyiv
WEATHER_COUNTRY=UA

# === General ===
TIMEZONE=Europe/Kyiv

# === Voice ===
WHISPER_ENABLED=true                          # false to disable voice completely
WHISPER_MODEL_SIZE=base                       # tiny, base, small, medium, large-v3
WHISPER_UNLOAD_SECONDS=120                    # 0 = keep model in memory forever

# === Memory ===
MEMORY_MAX_MESSAGES=20                        # Recent messages to keep per user
MEMORY_SUMMARY_THRESHOLD=15                   # Trigger summarization after N messages

# === LLM Timeouts ===
LLM_TIMEOUT_SECONDS=60
LLM_MAX_RETRIES=3
```

### 3. Start Database

```bash
docker compose up -d postgres
```

### 4. Start Application

Everything in one command — FastAPI + Telegram bot polling + background scheduler:
```bash
uv run python main.py
```

Or standalone bot-only mode (without FastAPI / REST API):
```bash
uv run python bot_polling.py
```

### 5. Start via Docker (production)

```bash
docker compose up -d --build
```

The Docker setup includes:
- **PostgreSQL 16** with persistent volume and health check
- **App container** with `uv` for dependency management
- **Whisper cache volume** — model files persist across container restarts

---

## 🤖 Bot Commands

| Command | Description |
|---------|------------|
| `/start` | Registration + welcome |
| `/tasks` | Active tasks list with inline buttons and descriptions |
| `/done <number>` | Mark task as completed |
| `/cancel <number>` | Cancel task |
| `/delete <number>` | Delete task |
| `/describe <number> <text>` | Add or update a task description (max 250 words) |
| `/morning` | Morning brief (weather + day plan) |
| `/timeline` | Day schedule (constraints + free windows) |
| `/recurring` | Manage recurring tasks |
| `/stats` | Statistics (today / week / month / all_time) |
| `/stats sys` | System statistics (uptime, RAM, users, tasks, Whisper) |
| `/help` | Show full list of commands |

**Quick Action Buttons (Main Menu):**
- 📋 **My tasks** → `/tasks`
- 🌅 **My day** → `/morning`
- 📅 **Schedule** → `/timeline`
- 🔄 **Recurring** → `/recurring`
- 📊 **Statistics** → `/stats`
- ❓ **Help** → `/help`

---

## 🔌 REST API

The application exposes a REST API at `/api/v1/` for integration with web or mobile clients:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/health` | API health check |
| `POST` | `/api/v1/message` | Send text to planner, get structured response |
| `GET` | `/api/v1/tasks/{user_id}` | List active tasks for a user |
| `PATCH` | `/api/v1/tasks/{task_id}` | Update task (title, priority, status) |
| `DELETE` | `/api/v1/tasks/{task_id}` | Soft-delete a task |

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

**Coverage**: constraints, dependencies, energy, LLM-parsing, memory, priority (v1 + v2), recurring, rescheduler, routine, schemas, statistics, weather-planning.

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | FastAPI + Uvicorn |
| **Telegram** | aiogram 3.x (polling + webhook) |
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
| **Monitoring** | psutil (RAM / process stats) |

---

## 📝 License

MIT
