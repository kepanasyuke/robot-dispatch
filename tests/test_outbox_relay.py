from __future__ import annotations

from robot_dispatch.db.models import OutboxMessage
from robot_dispatch.messaging.messages import COMMANDS_EXCHANGE
from robot_dispatch.messaging.outbox_relay import OutboxRelay


async def seed_outbox(uow_factory, *, available_at=None, **kwargs):
    message = OutboxMessage.new(
        exchange=COMMANDS_EXCHANGE,
        routing_key="command.abc",
        payload={"task_id": "t-1"},
        message_id="m-1",
        headers={"attempt": 1},
        **kwargs,
    )
    if available_at is not None:
        message.available_at = available_at
    async with uow_factory() as uow:
        await uow.outbox.add(message)
        await uow.commit()
    return message


async def test_relay_publishes_pending_messages(uow_factory, settings, clock, publisher) -> None:
    await seed_outbox(uow_factory, available_at=clock.moment)
    relay = OutboxRelay(uow_factory, publisher, settings, clock=clock)

    published = await relay.relay_once()

    assert published == 1
    assert publisher.count == 1
    assert publisher.published[0]["message_id"] == "m-1"
    assert publisher.published[0]["payload"] == {"task_id": "t-1"}
    assert publisher.published[0]["headers"] == {"attempt": 1}

    async with uow_factory() as uow:
        stored = list(uow._store.outbox)
    assert stored[0].sent_at is not None
    assert stored[0].attempts == 1


async def test_relay_does_not_republish_sent_messages(uow_factory, settings, clock, publisher) -> None:
    await seed_outbox(uow_factory, available_at=clock.moment)
    relay = OutboxRelay(uow_factory, publisher, settings, clock=clock)
    await relay.relay_once()

    assert await relay.relay_once() == 0
    assert publisher.count == 1


async def test_relay_schedules_retry_on_publish_failure(uow_factory, settings, clock, publisher) -> None:
    message = await seed_outbox(uow_factory, available_at=clock.moment)
    publisher.fail_with = RuntimeError("broker is down")
    relay = OutboxRelay(uow_factory, publisher, settings, clock=clock)

    published = await relay.relay_once()

    assert published == 0
    async with uow_factory() as uow:
        stored = [item for item in uow._store.outbox if item.id == message.id][0]
    assert stored.sent_at is None
    assert stored.attempts == 1
    assert "broker is down" in stored.last_error
    assert stored.available_at > clock.moment


async def test_relay_publishes_after_backoff(uow_factory, settings, clock, publisher) -> None:
    await seed_outbox(uow_factory, available_at=clock.moment)
    publisher.fail_with = RuntimeError("broker is down")
    relay = OutboxRelay(uow_factory, publisher, settings, clock=clock)
    await relay.relay_once()

    publisher.fail_with = None
    assert await relay.relay_once() == 0

    clock.advance(5)
    assert await relay.relay_once() == 1
    assert publisher.count == 1
