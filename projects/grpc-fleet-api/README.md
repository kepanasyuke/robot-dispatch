# grpc-fleet-api

gRPC-плоскость управления флотом: состояние роботов, heartbeat-ы и выдача команд.
Второй транспорт к той же предметной области, что и REST-диспетчер — требование вакансии «REST/gRPC».

## Контракт (`proto/fleet.proto`)

| RPC | Назначение | Ошибки |
|---|---|---|
| `GetRobot` | карточка робота | `NOT_FOUND`, `INVALID_ARGUMENT`, `DEADLINE_EXCEEDED` |
| `ListRobots` | список с фильтром по статусу | `INVALID_ARGUMENT` (статус, лимит) |
| `ReportHeartbeat` | заряд и статус от робота | `NOT_FOUND`, `INVALID_ARGUMENT` (заряд, будущий `ts`) |
| `DispatchTask` | выдать команду | `FAILED_PRECONDITION`, `INVALID_ARGUMENT` |

`DispatchTask` идемпотентен по `command_id`: повторный вызов возвращает `duplicate=true` и того же
робота, а не вторую команду. Это важно, потому что клиент может повторить вызов после таймаута,
не зная, дошёл ли первый.

## Что показательно в реализации

* **Канонические коды статусов**, а не «500 на всё»: `NOT_FOUND`, `INVALID_ARGUMENT`,
  `FAILED_PRECONDITION`, `DEADLINE_EXCEEDED`.
* **Валидация входа в сервисе**: пустые идентификаторы, заряд вне `0..100`, `timeout` вне `1..86400`,
  heartbeat «из будущего» (> 30 c) отклоняются.
* **Liveness выводится, а не хранится**: робот без heartbeat дольше 30 c отдаётся как `offline`,
  даже если сам писал `idle` — иначе планировщик ждёт мёртвого робота.
* **Интерцептор наблюдаемости**: доступ-лог и метрики по методам (`calls/ok/error/avg_ms`),
  медленные вызовы (> 500 мс) логируются отдельно.
* **Порт 0 в тестах**: сервер поднимается на свободном порту, тесты работают через настоящий
  gRPC-канал, без моков транспорта.

## Запуск

```bash
python -m grpc_fleet_api.server           # слушает 0.0.0.0:50051
```

Перегенерация стабов после правки `.proto`:

```bash
python scripts/dev.py proto
```

## Проверка

```bash
python scripts/dev.py test projects/grpc-fleet-api
python scripts/dev.py lint
```
