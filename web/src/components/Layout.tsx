import { Link, NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { ServiceHealthPill } from "./ServiceHealthPill";
import type { HealthSummary } from "../lib/health";
import { roleLabel, type Session } from "../auth/session";

export function Layout({
  health,
  session,
  onLogout,
  children,
}: {
  health: HealthSummary;
  session: Session;
  onLogout: () => void;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <header className="shell__header">
        <Link to="/" className="brand">
          <span className="brand__mark">RD</span>
          <span>
            <strong>Robot Dispatch</strong>
            <small>консоль флота</small>
          </span>
        </Link>
        <div className="shell__session">
          <span className={`role-chip role-chip--${session.role}`}>{roleLabel(session.role)}</span>
          <ServiceHealthPill health={health} />
          <button type="button" className="button button--ghost" onClick={onLogout}>
            Выйти
          </button>
        </div>
      </header>
      <nav className="tabs" aria-label="Разделы">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "tabs__link tabs__link--active" : "tabs__link")}>
          Обзор
        </NavLink>
        <NavLink to="/tasks" className={({ isActive }) => (isActive ? "tabs__link tabs__link--active" : "tabs__link")}>
          Задачи
        </NavLink>
        <NavLink to="/robots" className={({ isActive }) => (isActive ? "tabs__link tabs__link--active" : "tabs__link")}>
          Роботы
        </NavLink>
      </nav>
      <main className="shell__main">{children}</main>
      <footer className="shell__footer">
        <span>FastAPI · PostgreSQL · RabbitMQ</span>
        <span>данные обновляются каждые 3 секунды</span>
      </footer>
    </div>
  );
}
