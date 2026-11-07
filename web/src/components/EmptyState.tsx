export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty" role="status">
      <strong>{title}</strong>
      {hint ? <p>{hint}</p> : null}
    </div>
  );
}
