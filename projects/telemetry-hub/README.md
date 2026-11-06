# telemetry-hub

Приём телеметрии флота: MQTT-поток от роботов → валидация → дедупликация по `(robot_id, seq)` →
rolling-агрегаты → REST для мониторинга.

## Зачем

Роботы публикуют телеметрию в MQTT с QoS 1: сообщения дублируются, приходят не по порядку и пачками
после восстановления связи. Сервис изолирует эту грязь от остальной системы: наружу отдаётся
предсказуемый снимок состояния робота (`GET /api/v1/robots/{id}`).

## Политики

| Ситуация | Поведение |
|---|---|
| Повтор `(robot_id, seq)` | отбрасывается, инкремент `duplicates` |
| Опоздавшее сообщение (`seq` меньше текущего) | попадает в историю, но не откатывает состояние |
| Будущий `ts` (> 30 c) | `invalid`, в состояние не пишется |
| Очередь переполнена | выбрасывается самое старое сообщение (`dropped`), новые не теряются |
| Нет сообщений `> 15 c` | робот помечается `online=false` |

## API

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v1/telemetry` | батч до 500 сэмплов, отчёт по каждому |
| `GET` | `/api/v1/robots` | снимки всех роботов |
| `GET` | `/api/v1/robots/{id}` | снимок: состояние, заряд, позиция, пробег, средний заряд |
| `GET` | `/api/v1/robots/{id}/samples` | последние сырые сэмплы |
| `GET` | `/api/v1/stats` | счётчики: accepted/duplicate/out_of_order/dropped, очередь |
| `GET` | `/health` | liveness |

```bash
uvicorn telemetry_hub.api:app --reload
curl -X POST localhost:8000/api/v1/telemetry -H 'Content-Type: application/json' -d '{
  "samples": [{"robot_id":"robot-1","seq":1,"ts":"2026-01-01T12:00:00+00:00","battery":88,"state":"idle"}]
}'
```

## MQTT-адаптер

`telemetry_hub/mqtt.py` — тонкий мост `paho-mqtt` → asyncio-очередь (paho опционален):

```bash
pip install -e ".[mqtt]"
python -c "from telemetry_hub.mqtt import PahoMqttSource; print(PahoMqttSource(topic='fleet/+/telemetry'))"
```

Политики ingest от транспорта не зависят: тесты подают сэмплы напрямую в `TelemetryIngestor.offer`.

## Проверка

```bash
python scripts/dev.py test projects/telemetry-hub
python scripts/dev.py lint
```
