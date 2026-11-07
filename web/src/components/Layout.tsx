import { Link, NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { ServiceHealthPill } from "./ServiceHealthPill";
import type { HealthSummary } from "../lib/health";

export function Layout({ health, children }: { health: HealthSummary; children: ReactNode }) {
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
        <ServiceHealthPill health={health} />
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
