# robot-dispatch

Монорепозиторий backend-проектов для команды разработки роботов: диспетчеризация задач,
телеметрия, мост к ROS2, gRPC-плоскость управления, мониторинг флота и интеграция с WMS заказчика.

Каждый проект самостоятелен, но они складываются в одну систему: робот шлёт телеметрию →
монитор поднимает алерты → диспетчер ставит задачи → мост отдаёт команды в ROS2 → результаты
возвращаются в диспетчер → WMS получает статусы.

```
WMS ──HTTP──▶ wms-integration ──▶ robot-dispatch ──command──▶ ros2-bridge ──▶ ROS2
                                       ▲   │
                                       │   └──outbox──▶ RabbitMQ
                                       │
telemetry-hub ◀──MQTT── роботы    fleet-monitor ──▶ Prometheus
                                       ▲
                          grpc-fleet-api (fleet control plane)
```

## Проекты

| Проект | Что демонстрирует | Стек | Тесты |
|---|---|---|---|
| [robot-dispatch](src/robot_dispatch) | диспетчеризация: очередь задач, lease-восстановление, транзакционный outbox, REST API | FastAPI, PostgreSQL, RabbitMQ, Redis | 70 |
| [telemetry-hub](projects/telemetry-hub) | ingest MQTT с дедупликацией, порядком и backpressure, rolling-агрегаты | FastAPI, pydantic, aio-pika (MQTT) | 23 |
| [ros2-bridge](projects/ros2-bridge) | контракт сервер ↔ ROS2: топики, нормализация единиц, дедуп команд, таймауты фидбэка | pydantic, asyncio | 22 |
| [grpc-fleet-api](projects/grpc-fleet-api) | gRPC-плоскость: канонические статус-коды, идемпотентный `DispatchTask`, интерцептор метрик | grpcio, protobuf | 15 |
| [fleet-monitor](projects/fleet-monitor) | правила алертов с гистерезисом, жизненный цикл open/acked/resolved, Prometheus | FastAPI, Prometheus text | 21 |
| [wms-integration](projects/wms-integration) | устойчивый HTTP-клиент (retry, circuit breaker), идемпотентный синк заказов, подписанные вебхуки | httpx, HMAC | 22 |

Суммарно: **165 тестов**, `ruff` и `mypy` без замечаний, CI на каждый push.

## Быстрый старт

```bash
make install     # или: python scripts/dev.py install
make check       # ruff + mypy + pytest
make up          # docker compose: postgres, rabbitmq, redis, api, dispatcher, consumer, 2 робота
```

`make` — тонкая обёртка над `python scripts/dev.py`; на Windows без GNU make используйте второй вариант,
команды идентичны.

| Команда | Что делает |
|---|---|
| `install` | установить пакет с dev-зависимостями |
| `lint` / `format` | ruff check / autofix + format |
| `typecheck` | mypy (73 файла) |
| `test [путь]` | pytest: всё или конкретный проект |
| `check` | lint + typecheck + test |
| `proto` | перегенерация gRPC-стабов (включая `.pyi`) |
| `projects` | список проектов репозитория |
| `up` / `down` / `logs` / `migrate` / `sim` | docker-compose и локальный симулятор флота |

```bash
python scripts/dev.py test projects/ros2-bridge
python scripts/dev.py projects
```

## robot-dispatch: ключевые решения

| Отказ | Механизм |
|---|---|
| Два диспетчера взяли одну задачу | `SELECT ... FOR UPDATE SKIP LOCKED` |
| Падение между назначением и публикацией | транзакционный outbox: задача + состояние робота + команда в одной транзакции |
| Брокер недоступен | outbox повторяет публикацию с backoff |
| Робот молча умер | lease на попытку, `LeaseReaper` возвращает задачу в очередь |
| Робот вернул ошибку | экспоненциальный backoff с потолком, затем `failed` |
| Дубликат/опоздавший результат | проверка `command_id`, терминальные статусы игнорируются |
| Повторный POST заказчика | `external_id` / `Idempotency-Key` + уникальный индекс → 200 вместо 201 |
| Битое сообщение от робота | немедленный dead-letter |
| Сбой обработчика | retry-очередь с TTL, затем DLQ |

Подробности — в разделе «Паттерны отказоустойчивости» [основного README-описания](#) и в коде:
`src/robot_dispatch/services/dispatcher.py`, `src/robot_dispatch/messaging/outbox_relay.py`.

## Структура

```
src/robot_dispatch/        основной сервис диспетчеризации
  api/  db/  domain/  repositories/  services/  messaging/  workers/  infra/
mock_ros2/                 симулятор флота (регистрация, команды, прогресс, heartbeat)
projects/
  telemetry-hub/           ingest и агрегаты телеметрии
  ros2-bridge/             мост к ROS2-топикам
  grpc-fleet-api/          gRPC-контракт и сервер
  fleet-monitor/           алерты и метрики
  wms-integration/         клиент и вебхуки WMS
migrations/                Alembic
scripts/dev.py             кросс-платформенный раннер (он же — цели Makefile)
tests/                     тесты основного сервиса
```

У каждого проекта в `projects/` есть свой README с деталями контракта и решениями.

## Инженерные принципы репозитория

* **Домен отделён от I/O**: статусы и переходы — `domain/`, транспорт — `messaging/`, хранилище — `repositories/`.
* **Один контракт, две реализации**: SQL и in-memory Unit of Work; тесты не требуют PostgreSQL и RabbitMQ.
* **Валидация на границе**: pydantic-схемы на входе любого внешнего канала (HTTP, MQTT, gRPC, webhook).
* **Честная типизация**: `mypy` проходит по 73 файлам, включая сгенерированные gRPC-стабы через `.pyi`.
* **Тесты как документация отказов**: каждый сценарий (stale lease, replay вебхука, half-open breaker)
  воспроизводится детерминированно.

## Что дальше

* gRPC-адаптер для `robot-dispatch` поверх тех же сервисов (транспорт уже отделён).
* Prometheus-экспорт метрик диспетчера (сейчас `/api/v1/stats`).
* Пул слотов на робота вместо `current_task_id`.
* Интеграционные тесты с testcontainers на PostgreSQL и RabbitMQ.
