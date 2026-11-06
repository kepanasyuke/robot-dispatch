# fleet-monitor

Мониторинг здоровья флота: heartbeat-SLA, правила алертов с гистерезисом, жизненный цикл алертов
(`open → acked → resolved`) и экспорт метрик для Prometheus.

## Зачем

Диспетчер знает, куда ставить задачу, но не отвечает на вопрос «что сейчас не так с флотом».
Монитор превращает поток health-сэмплов в конечный набор алертов: один алерт на пару
`(робот, тип проблемы)`, автоматическое закрытие при восстановлении, ручной ack оператором.

## Правила

| Правило | Условие | Severity | Снятие |
|---|---|---|---|
| `offline` | нет heartbeat дольше 30 c | critical | пришёл свежий heartbeat |
| `low_battery` | заряд < 20 % | warning | заряд ≥ 25 % (гистерезис 5 %) |
| `stuck_task` | задача выполняется > 15 мин | warning | задача завершилась |
| `error_rate` | доля ошибок > 20 % | critical | доля ≤ 15 % |

`None` в результате правила означает «данных недостаточно» — алерт не трогаем, чтобы отсутствие
показателя не закрывало реальную проблему.

## Поведение

* **Дедупликация**: повторные наблюдения обновляют `last_seen` и `count`, но не создают новые алерты.
* **Debounce**: внутри 60-секундного окна `count` не растёт — частый опрос не раздувает статистику.
* **Авторезолв**: восстановление робота закрывает алерт без участия оператора.
* **Ack**: `POST /alerts/{id}/ack` фиксирует автора; закрытый алерт повторно не подтверждается (409).

## API и метрики

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v1/health` | health-сэмпл робота, возвращает затронутые алерты |
| `GET` | `/api/v1/alerts` | алерты, фильтры `status`, `robot_id` |
| `POST` | `/api/v1/alerts/{id}/ack` | подтвердить (`{"by": "oncall"}`) |
| `POST` | `/api/v1/alerts/{id}/resolve` | закрыть вручную |
| `GET` | `/api/v1/robots` | последние health-сэмплы |
| `GET` | `/metrics` | Prometheus text format |

```
fleet_robots_known 6
fleet_robots_online 5
fleet_alerts_active 2
fleet_alerts_active_by_severity{severity="critical"} 1
fleet_alerts_active_by_type{type="offline"} 1
fleet_alert_instances_total 14
```

```bash
uvicorn fleet_monitor.api:app --reload
curl -X POST localhost:8000/api/v1/health -H 'Content-Type: application/json' \
  -d '{"robot_id":"robot-1","battery_percent":12,"error_rate":0.3}'
```

## Проверка

```bash
python scripts/dev.py test projects/fleet-monitor
python scripts/dev.py lint
```
