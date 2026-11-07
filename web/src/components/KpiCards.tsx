import type { ReactNode } from "react";

export interface Kpi {
  label: string;
  value: string;
  hint?: string;
  tone?: string;
}

export function KpiCards({ items }: { items: Kpi[] }) {
  return (
    <div className="kpi-grid">
      {items.map((item) => (
        <article key={item.label} className={`kpi kpi--${item.tone ?? "neutral"}`}>
          <span className="kpi__label">{item.label}</span>
          <strong className="kpi__value">{item.value}</strong>
          {item.hint ? <span className="kpi__hint">{item.hint}</span> : null}
        </article>
      ))}
    </div>
  );
}

export function Panel({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      <header className="panel__header">
        <h2>{title}</h2>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
