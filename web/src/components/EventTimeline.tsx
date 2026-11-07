import type { TaskEvent } from "../api/types";
import { formatDateTime, formatRelative } from "../lib/format";
import { buildTimeline } from "../lib/timeline";
import { EmptyState } from "./EmptyState";
import { StatusBadge } from "./StatusBadge";

export function EventTimeline({ events, now }: { events: TaskEvent[]; now?: Date }) {
  const reference = now ?? new Date();
  const entries = buildTimeline(events);

  if (entries.length === 0) {
    return <EmptyState title="Событий пока нет" hint="События появятся после первых переходов статуса." />;
  }

  return (
    <ol className="timeline">
      {entries.map((entry) => (
        <li key={entry.id} className="timeline__item" data-testid="timeline-item">
          <span className={`timeline__dot timeline__dot--${entry.tone}`} aria-hidden="true" />
          <div className="timeline__body">
            <div className="timeline__head">
              <StatusBadge tone={entry.tone}>{entry.label}</StatusBadge>
              <time dateTime={entry.createdAt} title={formatDateTime(entry.createdAt)}>
                {formatRelative(entry.createdAt, reference)}
              </time>
            </div>
            {entry.message ? <p className="timeline__message">{entry.message}</p> : null}
            {entry.fromStatus || entry.toStatus ? (
              <small className="mono">
                {entry.fromStatus ?? "—"} → {entry.toStatus ?? "—"}
              </small>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
