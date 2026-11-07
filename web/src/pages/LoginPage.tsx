import { useState } from "react";
import type { Role, Session } from "../auth/session";

export function LoginPage({ onLogin }: { onLogin: (session: Session) => void }) {
  const [role, setRole] = useState<Role>("operator");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = apiKey.trim();
    if (trimmed.length > 0 && trimmed.length < 4) {
      setError("Ключ доступа слишком короткий");
      return;
    }
    setError(null);
    onLogin({ role, apiKey: trimmed });
  }

  return (
    <div className="login">
      <form className="login__card" onSubmit={submit} aria-label="Вход в консоль">
        <header className="login__head">
          <span className="brand__mark">RD</span>
          <div>
            <h1>Robot Dispatch</h1>
            <p>Консоль флота: задачи, роботы, состояние сервиса</p>
          </div>
        </header>

        <fieldset className="login__roles">
          <legend>Роль</legend>
          <div className={role === "operator" ? "role role--active" : "role"}>
            <input
              id="role-operator"
              type="radio"
              name="role"
              value="operator"
              checked={role === "operator"}
              onChange={() => setRole("operator")}
            />
            <label htmlFor="role-operator">
              <strong>Оператор</strong>
              <small>создавать и отменять задачи</small>
            </label>
          </div>
          <div className={role === "viewer" ? "role role--active" : "role"}>
            <input
              id="role-viewer"
              type="radio"
              name="role"
              value="viewer"
              checked={role === "viewer"}
              onChange={() => setRole("viewer")}
            />
            <label htmlFor="role-viewer">
              <strong>Наблюдатель</strong>
              <small>только просмотр</small>
            </label>
          </div>
        </fieldset>

        <label className="field" htmlFor="api-key">
          <span>Ключ доступа (X-API-Key)</span>
          <input
            id="api-key"
            type="password"
            autoComplete="off"
            placeholder="оставьте пустым, если сервер без ключа"
            value={apiKey}
            onChange={(event) => {
              setApiKey(event.target.value);
              setError(null);
            }}
          />
        </label>

        {error ? (
          <p className="error-text" role="alert">
            {error}
          </p>
        ) : null}

        <button type="submit" className="button button--primary">
          Войти
        </button>

        <p className="login__hint">
          Ключ хранится в sessionStorage вкладки и не отправляется никуда, кроме API.
        </p>
      </form>
    </div>
  );
}
