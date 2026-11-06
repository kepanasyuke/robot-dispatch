# robot-dispatch

<p align="center">
  <img src="docs/animation/dispatch-flow.gif" width="880" alt="Сценарий диспетчеризации: задача, замолчавший робот и повтор на другом роботе">
</p>

*Восемь кадров одного сценария: задача создаётся, робот её берёт и замолкает — lease истекает,
задача возвращается в очередь, второй робот доводит её до успеха. GIF собирается командой `make docs`.*

## Простыми словами

Это диспетчерская для парка роботов: складская система присылает задачи, диспетчер раздаёт их роботам, собирает телеметрию и показывает, что происходит с флотом. Если робот потерял связь, его задача возвращается в очередь и достаётся другому — работа не встаёт.

Внутри несколько самостоятельных сервисов на Python: диспетчер задач, приём телеметрии, мост к ROS2, мониторинг и интеграция с WMS заказчика. Они общаются через RabbitMQ и HTTP, состояние хранят в PostgreSQL.

Монорепозиторий backend-проектов для команды разработки роботов: диспетчеризация задач,
телеметрия, мост к ROS2, gRPC-плоскость управления, мониторинг флота и интеграция с WMS заказчика.

Каждый проект самостоятелен, но они складываются в одну систему: робот шлёт телеметрию →
монитор поднимает алерты → диспетчер ставит задачи → мост отдаёт команды в ROS2 → результаты
возвращаются в диспетчер → WMS получает статусы.

![Архитектура robot-dispatch: API, PostgreSQL, outbox, RabbitMQ и флот ROS2](docs/diagrams/architecture.svg)

## Проекты

![Карта проектов: диспетчеризация и пять соседних сервисов](docs/diagrams/projects.svg)

| Проект | Что демонстрирует | Стек | Тесты |
|---|---|---|---|
| [robot-dispatch](src/robot_dispatch) | диспетчеризация: очередь задач, lease-восстановление, транзакционный outbox, REST API | FastAPI, PostgreSQL, RabbitMQ, Redis | 70 |
| [telemetry-hub](projects/telemetry-hub) | ingest MQTT с дедупликацией, порядком и backpressure, rolling-агрегаты | FastAPI, pydantic, aio-pika (MQTT) | 23 |
| [ros2-bridge](projects/ros2-bridge) | контракт сервер ↔ ROS2: топики, нормализация единиц, дедуп команд, таймауты фидбэка | pydantic, asyncio | 22 |
| [grpc-fleet-api](projects/grpc-fleet-api) | gRPC-плоскость: канонические статус-коды, идемпотентный `DispatchTask`, интерцептор метрик | grpcio, protobuf | 15 |
| [fleet-monitor](projects/fleet-monitor) | правила алертов с гистерезисом, жизненный цикл open/acked/resolved, Prometheus | FastAPI, Prometheus text | 21 |
| [wms-integration](projects/wms-integration) | устойчивый HTTP-клиент (retry, circuit breaker), идемпотентный синк заказов, подписанные вебхуки | httpx, HMAC | 22 |

Суммарно: **165 тестов**, `ruff` и `mypy` без замечаний, CI на каждый push.

## Игра

<p align="center">
  <a href="https://kepanasyuke.github.io/robot-dispatch/game/">
    <img src="docs/game/gameplay.gif" width="880" alt="Геймплей «Диспетчера роботов»: роботы везут кубики-заказы, кольца показывают дедлайн">
  </a>
</p>

«Диспетчер роботов» — мини-игра на ту же тему: заказы-кубики появляются на складе, нужно назначать
свободных роботов, следить за зарядом и не давать заказам просрочиться.

Правило повторной постановки взято из сервиса: если робот не довёз заказ (разрядился или истёк
дедлайн), задача возвращается в очередь с новой попыткой — до трёх, после чего теряется жизнь.
Заказ, который никто не взял, сгорает сразу.

Играть: [kepanasyuke.github.io/robot-dispatch/game](https://kepanasyuke.github.io/robot-dispatch/game/) ·
исходник: `docs/game/index.html` — один файл, без зависимостей, сети и сборки.

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
| `docs` | пересборка GIF-анимации и проверка SVG-схем |
| `projects` | список проектов репозитория |
| `up` / `down` / `logs` / `migrate` / `sim` | docker-compose и локальный симулятор флота |

```bash
python scripts/dev.py test projects/ros2-bridge
python scripts/dev.py projects
```

## robot-dispatch: ключевые решения

![Жизненный цикл задачи: pending, assigned, running, retrying, succeeded, failed, cancelled](docs/diagrams/lifecycle.svg)

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

Подробности — в коде: `src/robot_dispatch/services/dispatcher.py`,
`src/robot_dispatch/messaging/outbox_relay.py`, `src/robot_dispatch/domain/state_machine.py`.

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
