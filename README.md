# 🤖 AI Task Planner — Telegram Bot

> Персональный AI-планировщик задач в Telegram с голосовым вводом, интеллектуальным расписанием и прогнозом погоды.

Отправьте боту текстовое или голосовое сообщение — он разберёт задачи, расставит приоритеты, составит расписание на день и вовремя напомнит о дедлайнах. Вся бизнес-логика (приоритеты, дедлайны, зависимости) работает детерминистически — LLM используется только для понимания естественного языка.

---

## ✨ Возможности

### 🧠 AI-ядро (Natural Language Understanding)
- **Понимание естественного языка** — пишите как удобно: *"Завтра сдать курсач по матану до 16:00"*, *"Надо купить молоко"* — бот сам извлечёт задачу, дедлайн, приоритет и категорию.
- **Два LLM-провайдера на выбор**: OpenRouter (облако, десятки моделей) или Ollama (локально, полная приватность).
- **Structured JSON output** — LLM возвращает строго типизированный ответ, который парсится через Pydantic-схемы.
- **Контекстная память** — бот помнит предыдущие сообщения и автоматически сжимает историю, чтобы не перегружать контекстное окно.

### 🎙 Голосовой ввод (Whisper STT)
- **Распознавание голоса** через [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (SYSTRAN/faster-whisper) — оптимизированная CTranslate2-реализация модели OpenAI Whisper.
- Автоматическое определение языка (русский, украинский, английский).
- При низкой уверенности распознавания бот просит подтверждение перед обработкой.
- Конвертация аудио из OGG в WAV через **ffmpeg**.

### 📋 Управление задачами
- **CRUD** — создание, просмотр, завершение, отмена, удаление задач.
- **Inline-кнопки** — ✅ Выполнить / 🗑 Удалить прямо под списком задач.
- **Категории задач**: `study`, `home`, `health`, `errand`, `sport`, `work`, `other`.
- **Приоритеты 1–5** с цветовой индикацией (⚪🟢🟡🟠🔴).
- **Дедлайны** (hard / soft) и **фиксированное время** для жёстких событий.
- **Мягкое удаление** — задачи не стираются из БД, а помечаются как удалённые.

### 🔄 Повторяющиеся задачи
- Паттерны: `daily`, `weekly:mon,wed,fri`, `monthly:15`.
- Автоматическое создание экземпляров по расписанию (APScheduler).
- Управление через `/recurring` с inline-кнопками.

### 📅 Интеллектуальное расписание (Timeline Engine)
- **Жёсткие блокировки** (constraints) — сон, школа/работа, фокус и другие. Бот знает, когда вы недоступны, и не ставит задачи на заблокированное время.
- **Управление блокировками голосом** — скажите *"Я больше не хожу в школу"* или *"Я сплю с 12 до 9"*, и бот обновит расписание.
- **Свободные окна** — автоматический расчёт доступного времени с визуализацией в команде `/timeline`.
- **Энергетический профиль** — учёт биологических ритмов (жаворонок/сова). Важные задачи ставятся на часы пиковой активности.
- **Greedy-алгоритм размещения** — задачи расставляются по свободным окнам с учётом приоритета, длительности и энергии.

### ⚡ Умный движок приоритетов
- **Детерминистические правила** (без LLM):
  - Фиксированное время сегодня → минимум приоритет 4
  - Дедлайн в ближайшие 2 часа → приоритет 5
  - Дедлайн сегодня → 4–5
  - Ключевые слова «срочно», «обязательно» → повышение приоритета
- **Обнаружение конфликтов** — если две задачи пересекаются по времени, бот предупредит.
- **Авто-определение просроченных** — задачи с истекшим дедлайном помечаются как overdue.

### 🔗 Зависимости задач
- Создание цепочек: *"Задача B зависит от задачи A"*.
- **Защита от циклов** — DFS-обход графа предотвращает невозможные петли.
- **Блокировка завершения** — нельзя отметить задачу как выполненную, пока не завершены её зависимости.

### 🌦 Интеграция с погодой
- **OpenWeatherMap API** — актуальный прогноз с кэшированием (30 мин TTL).
- **Утренняя сводка** — температура, осадки, ветер при запросе плана дня.
- **Погодочувствительные задачи** — если задача помечена как `weather_sensitive` (пробежка, прогулка), а прогноз обещает дождь, бот предупредит и предложит перенести.

### 📊 Статистика и аналитика
- Команда `/stats` — полная сводка:
  - ✅ Выполнено / ❌ Отменено / ⏳ Просрочено
  - 🔥 Серия (дней подряд с выполненными задачами)
  - ⏱ Среднее время на задачу
  - 🗂 Разбивка по категориям
- Фильтрация: `today`, `week`, `month`, `all_time`.

### ⏰ Напоминания и автоматизация
- Автоматическое создание напоминаний за 2 часа до дедлайна/фиксированного времени.
- Inline-кнопка **"✅ Понял"** для подтверждения.
- Фоновые джобы (APScheduler):
  - Проверка приближающихся дедлайнов (каждые 15 мин)
  - Отправка pending-напоминаний (каждую минуту)
  - Создание экземпляров регулярных задач (каждый час)
  - Предложения по переносу задач (каждые 30 мин)
  - Очистка старых сообщений (ежедневно)

### 🔀 Авто-перенос задач
- `ReschedulerService` анализирует расписание и предлагает перенести задачи, если окно стало недоступно.
- Предложение приходит в Telegram с кнопками **"✅ Согласен"** / **"❌ Оставить как есть"**.

---

## 🏗 Архитектура

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

**Ключевые принципы:**
- **LLM — только NLU.** Вся бизнес-логика (приоритеты, дедлайны, конфликты, зависимости) — детерминистическая.
- **Разделение слоёв.** Transport ничего не знает о Storage. Core Services не знают о Telegram.
- **Dependency Injection.** Все сервисы инжектятся через `lifespan` в `app/main.py`.

---

## 📂 Структура проекта

```
.
├── main.py                          # Точка входа (uvicorn runner)
├── app/
│   ├── main.py                      # FastAPI app + lifespan (DI)
│   ├── config.py                    # pydantic-settings конфигурация
│   ├── db/
│   │   ├── engine.py                # SQLAlchemy async engine
│   │   └── repository.py           # Все CRUD-операции с БД
│   ├── llm/
│   │   ├── base.py                  # Абстрактный BaseLLMProvider
│   │   ├── openrouter.py            # OpenRouter (OpenAI-compatible API)
│   │   ├── ollama.py                # Ollama (локальный LLM)
│   │   ├── factory.py               # Фабрика провайдеров
│   │   └── prompts.py               # Системный промпт для LLM
│   ├── models/
│   │   ├── task.py                  # TaskORM, RecurrenceORM
│   │   ├── user.py                  # UserORM (с energy_profile)
│   │   ├── message.py              # MessageORM, MemorySummaryORM
│   │   ├── constraint.py           # UserConstraintORM
│   │   ├── dependency.py           # TaskDependencyORM
│   │   ├── reminder.py             # ReminderORM
│   │   └── routine.py              # TaskCompletionLogORM
│   ├── schemas/                     # Pydantic-модели (валидация I/O)
│   ├── services/
│   │   ├── planner.py              # CorePlanner — главный оркестратор
│   │   ├── priority.py             # PriorityEngine (детерминистический)
│   │   ├── timeline.py             # TimelineEngine (расписание дня)
│   │   ├── constraints.py          # Управление блокировками
│   │   ├── dependencies.py         # Зависимости задач + cycle detection
│   │   ├── energy.py               # Биоритмы / energy profile
│   │   ├── weather.py              # OpenWeatherMap интеграция
│   │   ├── voice.py                # Whisper STT
│   │   ├── memory.py               # Контекстная память (3-tier)
│   │   ├── scheduler.py            # APScheduler (фоновые джобы)
│   │   ├── statistics.py           # Аналитика и метрики
│   │   ├── rescheduler.py          # Авто-перенос задач
│   │   └── routine.py              # Обучение привычкам
│   └── transport/
│       ├── api/routes.py            # REST-эндпоинты
│       └── telegram/
│           ├── bot.py               # Создание Bot + Dispatcher
│           ├── handlers.py          # Все хендлеры команд и сообщений
│           ├── formatter.py         # Форматирование для Telegram
│           └── callbacks.py         # Callback-данные для inline-кнопок
├── tests/                           # 40 unit-тестов (pytest + pytest-asyncio)
├── alembic/                         # Миграции базы данных
├── Dockerfile                       # Production-образ
├── docker-compose.yml               # App + PostgreSQL
├── pyproject.toml                   # Зависимости (uv)
└── .env.example                     # Пример конфигурации
```

---

## 🚀 Быстрый старт

### Требования

- Python **3.14+**
- PostgreSQL **16+**
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов
- [ffmpeg](https://ffmpeg.org/) — для голосовых сообщений

### 1. Клонирование и настройка

```bash
git clone https://github.com/<your-username>/ai-task-planner.git
cd ai-task-planner

# Установка зависимостей
uv sync

# Создание .env
cp .env.example .env
```

### 2. Конфигурация `.env`

```env
# === Обязательные ===
TELEGRAM_BOT_TOKEN=123456789:ABCdef...      # @BotFather
DATABASE_URL=postgresql+asyncpg://planner:planner_secret@127.0.0.1:55432/planner

# === LLM (выберите один) ===
LLM_PROVIDER=openrouter                      # или "ollama"
OPENROUTER_API_KEY=sk-or-v1-...              # https://openrouter.ai/keys
OPENROUTER_MODEL=deepseek/deepseek-r1:free   # или любая другая модель

# === Погода (опционально) ===
OPENWEATHER_API_KEY=your_key                 # https://openweathermap.org/api
WEATHER_CITY=Kyiv
WEATHER_COUNTRY=UA

# === Голос ===
WHISPER_MODEL_SIZE=base                       # tiny, base, small, medium, large
```

### 3. Запуск базы данных

```bash
docker compose up -d postgres
```

### 4. Запуск бота

```bash
# Режим разработки (hot-reload)
uv run python main.py

# Или напрямую
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Запуск через Docker (production)

```bash
docker compose up -d --build
```

---

## 🤖 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация + приветствие |
| `/tasks` | Список активных задач с inline-кнопками |
| `/done <номер>` | Отметить задачу как выполненную |
| `/cancel <номер>` | Отменить задачу |
| `/delete <номер>` | Удалить задачу |
| `/morning` | Утренняя сводка (погода + план дня) |
| `/timeline` | Расписание дня (блокировки + свободные окна) |
| `/recurring` | Управление регулярными задачами |
| `/stats` | Статистика (today / week / month / all_time) |

**Кнопки-быстрые действия:**
- 📋 **Мои задачи** → `/tasks`
- 🌅 **Мой день** → `/morning`
- 📅 **Расписание** → `/timeline`

---

## 🧪 Тестирование

```bash
# Все тесты
uv run pytest

# С подробным выводом
uv run pytest -v

# Конкретный модуль
uv run pytest tests/test_priority.py -v
```

**Покрытие**: 40 тестов — constraints, dependencies, energy, LLM-парсинг, memory, priority, recurring, rescheduler, routine, schemas, statistics, weather.

---

## 🛠 Технологический стек

| Компонент | Технология |
|-----------|-----------|
| **Фреймворк** | FastAPI + Uvicorn |
| **Telegram** | aiogram 3.x |
| **LLM** | OpenAI SDK (OpenRouter / Ollama) |
| **Speech-to-Text** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI Whisper, CTranslate2) |
| **База данных** | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| **Миграции** | Alembic |
| **Планировщик** | APScheduler (AsyncIOScheduler) |
| **Погода** | OpenWeatherMap API |
| **HTTP-клиент** | httpx |
| **Валидация** | Pydantic v2 |
| **Конфигурация** | pydantic-settings + .env |
| **Пакетный менеджер** | uv |
| **Линтер** | Ruff |
| **Тесты** | pytest + pytest-asyncio |
| **Контейнеризация** | Docker + Docker Compose |

---

## 📝 Лицензия

MIT
