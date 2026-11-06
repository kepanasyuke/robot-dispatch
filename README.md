# robot-dispatch

Сервис диспетчеризации задач для флота ROS2-роботов: постановка задач, назначение на свободных роботов,
контроль исполнения, восстановление после отказов и интеграция с внешними системами через RabbitMQ и HTTP.

Проект собран под вакансию backend-разработчика в команду роботов: серверная часть диспетчеризации,
надёжная постановка задач с таймаутами/повторами/переназначением, хранение состояния, мониторинг,
проектирование REST API и протокола обмена с ROS2-стеком.

```
Заказчик / WMS ──HTTP──▶ API (FastAPI) ──▶ PostgreSQL
                                            │
                                   outbox (одна транзакция с задачей)
                                            │
                                  OutboxRelay ──▶ RabbitMQ ──command.<robot_id>──▶ робот (ROS2)
                                                     ▲                               │
                                                     └──── result.<robot_id> ◀────────┘
                                                     ▲
                                            Consumer ──▶ статусы, ретраи, DLQ
```

## Соответствие требованиям вакансии

| Требование | Где реализовано |
|---|---|
| Сервер на Python (FastAPI) | `src/robot_dispatch/main.py`, `api/routers/*` |
| Брокеры сообщений (RabbitMQ) | `messaging/broker.py` — exchanges, per-robot очереди, DLQ, retry-очередь |
| Распределённые и event-driven системы | outbox, lease-модель, идемпотентность, `SKIP LOCKED` |
| Надёжная постановка задач (таймауты, повторы, переназначение) | `services/dispatcher.py` (LeaseReaper), `domain/policies.py` |
| Хранение состояния и мониторинг | `db/models.py` (task + event log), `GET /api/v1/stats`, `GET /health/ready` |
| Интеграции через RabbitMQ и HTTP | `messaging/*`, REST API с идемпотентным созданием |
| Проектирование интерфейса сервер ↔ ROS2 | `messaging/messages.py` (контракт команд/результатов), `mock_ros2/robot_sim.py` |
| REST/gRPC API | REST + OpenAPI (`/docs`); gRPC — см. «Что дальше» |
| PostgreSQL, Redis, Docker, Git, Linux | PostgreSQL в compose, Redis-leader-lock, `docker-compose.yml`, CI |
| Паттерны отказоустойчивости | таблица ниже |

## Жизненный цикл задачи

```
pending ──▶ assigned ──▶ running ──▶ succeeded
   │            │            │
   │            │            └──▶ failed          (попытки исчерпаны)
   │            └──▶ retrying ──▶ assigned        (робот не ответил / вернул ошибку)
   └──▶ cancelled
```

Переходы валидируются в одном месте — `domain/state_machine.py`. Любая попытка «воскресить»
завершённую задачу падает с `InvalidTransition`, а не портит данные.

## Паттерны отказоустойчивости

| Отказ | Механизм | Код |
|---|---|---|
| Два диспетчера взяли одну задачу | `SELECT ... FOR UPDATE SKIP LOCKED`, батч кандидатов | `repositories/sql.py: lock_ready` |
| Падение между «назначили» и «опубликовали команду» | транзакционный outbox: задача, состояние робота и сообщение коммитятся вместе | `services/dispatcher.py`, `messaging/outbox_relay.py` |
| Брокер недоступен | outbox хранит сообщение и повторяет публикацию с backoff | `messaging/outbox_relay.py` |
| Робот молча умер | lease `lease_expires_at` на попытку, reaper возвращает задачу в очередь | `services/dispatcher.py: LeaseReaper` |
| Робот вернул ошибку | повтор с экспоненциальной задержкой и потолком, затем `failed` | `domain/policies.py` |
| Дубликат результата / опоздавший результат прошлой попытки | проверка `command_id`, терминальные статусы игнорируются | `services/results.py` |
| Повторный POST от заказчика | `external_id` / `Idempotency-Key` + уникальный индекс, ответ 200 вместо 201 | `services/task_service.py`, `api/routers/tasks.py` |
| Битое сообщение от робота | немедленный dead-letter (реплей не поможет) | `messaging/consumer.py` |
| Сбой обработчика | доставка в retry-очередь с per-message TTL, затем DLQ | `messaging/consumer.py` |
| Двойная доставка команды роботу | `command_id` в сообщении, робот дедуплицирует | `mock_ros2/robot_sim.py` |
| Робот перестал слать heartbeat | watchdog переводит в `offline`, диспетчер его не выбирает | `messaging/outbox_relay.py: HeartbeatWatchdog` |

Отдельно про Redis: он используется только как best-effort leader-lock для диспетчера
(`infra/redis_lock.py`). Корректность от него не зависит — при недоступном Redis сервис работает
без блокировки, а уникальность назначения обеспечивает `SKIP LOCKED`.

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build      # postgres, rabbitmq, redis, миграции, api, dispatcher, consumer, 2 симулятора роботов
open http://localhost:8000/docs    # OpenAPI
open http://localhost:15672        # RabbitMQ UI: dispatch / dispatch
```

Поставить задачу и посмотреть, как её исполняет симулированный робот:

```bash
curl -s -X POST localhost:8000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"type":"delivery","payload":{"to":"warehouse-a","order":"A-100"},"priority":200,"external_id":"order-A-100"}'

curl -s localhost:8000/api/v1/tasks | jq
curl -s localhost:8000/api/v1/stats | jq
```

Повторный запрос с тем же `external_id` (или с заголовком `Idempotency-Key`) вернёт **ту же** задачу
со статусом 200 и заголовком `Idempotent-Replay: true` — без второй задачи в очереди.

### Локально без Docker

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
pytest -q
uvicorn robot_dispatch.main:app --reload     # нужен PostgreSQL по DISPATCH_DATABASE_URL
```

## API

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v1/tasks` | создать задачу (идемпотентно по `external_id` / `Idempotency-Key`) |
| `GET` | `/api/v1/tasks` | список с фильтрами `status`, `type`, `robot_id`, `limit`, `offset` |
| `GET` | `/api/v1/tasks/{id}` | карточка задачи |
| `GET` | `/api/v1/tasks/{id}/events` | журнал переходов и отказов (аудит) |
| `POST` | `/api/v1/tasks/{id}/cancel` | отмена; `runniing`-задачи отменяет только робот → 409 |
| `POST` | `/api/v1/robots` | регистрация/обновление робота по имени |
| `GET` | `/api/v1/robots`, `/api/v1/robots/{id}` | состояние флота |
| `GET` | `/api/v1/stats` | счётчики задач/роботов и глубины очередей |
| `GET` | `/health/live`, `/health/ready` | liveness / readiness (БД, брокер) |

Если задан `DISPATCH_API_KEY`, все `/api/v1/*` требуют заголовок `X-API-Key`.

## Протокол сервер ↔ ROS2

Обмен идёт через RabbitMQ, контракт описан pydantic-моделями в `messaging/messages.py`.

* `robot.commands` (direct) → очередь `cmd.<robot_id>`, ключ `command.<robot_id>`;
  тело `CommandMessage`: `command_id`, `task_id`, `task_type`, `attempt`, `timeout_seconds`, `payload`.
  Сообщение публикуется с TTL, равным таймауту попытки.
* `robot.events` (topic) ← `result.<robot_id>` и `heartbeat.<robot_id>`;
  `TaskResultMessage` c `event ∈ {progress, succeeded, failed}`. `progress` продлевает lease,
  поэтому длинная операция не считается зависшей.
* `dispatch.results` — очередь сервиса; ошибки уходят в `dispatch.results.retry` (TTL),
  после исчерпания попыток — в `dispatch.results.dlq`.

Симулятор `mock_ros2/robot_sim.py` реализует ровно эту сторону контракта: регистрируется через API,
слушает свою очередь, шлёт прогресс, результат и heartbeat, дедуплицирует команды по `command_id`.

## Тесты

```bash
pytest -q      # 70 тестов, ~2 секунды, без внешних сервисов
ruff check src tests mock_ros2
```

Домен, диспетчер, reaper, обработка результатов, outbox-релей, консьюмер и API тестируются
на in-memory реализации Unit of Work (`repositories/memory.py`), поэтому тесты не требуют
PostgreSQL и RabbitMQ. SQL-репозитории повторяют тот же контракт (`repositories/protocols.py`).

## Структура

```
src/robot_dispatch/
  api/            FastAPI-роутеры, схемы, зависимости
  db/             модели SQLAlchemy, сессия, Unit of Work
  domain/         статусы, машина состояний, политика ретраев (без I/O)
  repositories/   SQL- и in-memory-реализации одного контракта
  services/       TaskService, DispatcherService, LeaseReaper, ResultService
  messaging/      топология RabbitMQ, публикация, outbox-релей, консьюмер
  workers/        процессы dispatcher и consumer
mock_ros2/        симулятор флота роботов
migrations/       Alembic
tests/            unit + API тесты
```

## Осознанные ограничения

* Один робот исполняет одну задачу: `robots.current_task_id`. Пул слотов — расширяемая точка.
* gRPC-контракт не включён, чтобы не тащить protobuf-генерацию в демо; интерфейс сервисов
  (`services/*`) от транспорта не зависит — gRPC-адаптер добавляется поверх.
* Отмена `running`-задачи требует команды `cancel` роботу; в демо API возвращает 409 и просит
  отменять через робота.
* Метрики отдаются JSON-эндпоинтом `/api/v1/stats`; Prometheus-экспорт — следующий шаг.
