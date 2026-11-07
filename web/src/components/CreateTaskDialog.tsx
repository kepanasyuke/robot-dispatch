import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import type { CreateTaskInput, Task } from "../api/types";

export interface CreateTaskDialogProps {
  onClose: () => void;
  onSubmit: (input: CreateTaskInput, idempotencyKey: string) => Promise<Task>;
}

interface FormState {
  type: string;
  priority: string;
  payload: string;
  maxAttempts: string;
  timeoutSeconds: string;
  idempotencyKey: string;
}

function newIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (cryptoApi?.randomUUID) {
    return cryptoApi.randomUUID();
  }
  return `ui-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export function CreateTaskDialog({ onClose, onSubmit }: CreateTaskDialogProps) {
  const [form, setForm] = useState<FormState>({
    type: "",
    priority: "100",
    payload: "{}",
    maxAttempts: "3",
    timeoutSeconds: "120",
    idempotencyKey: newIdempotencyKey(),
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const typeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    typeRef.current?.focus();
  }, []);

  const payloadError = useMemo(() => {
    const text = form.payload.trim();
    if (text === "") {
      return null;
    }
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        return "Payload должен быть JSON-объектом";
      }
      return null;
    } catch {
      return "Payload не является валидным JSON";
    }
  }, [form.payload]);

  const typeError = form.type.trim() === "" ? "Укажите тип задачи" : null;
  const canSubmit = !busy && !typeError && !payloadError;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const input: CreateTaskInput = {
        type: form.type.trim(),
        priority: Number(form.priority) || 0,
        max_attempts: Number(form.maxAttempts) || undefined,
        timeout_seconds: Number(form.timeoutSeconds) || undefined,
        payload: form.payload.trim() === "" ? {} : (JSON.parse(form.payload) as Record<string, unknown>),
      };
      await onSubmit(input, form.idempotencyKey.trim());
      onClose();
    } catch (caught) {
      const message =
        caught instanceof ApiError
          ? `${caught.message}${caught.status ? ` (код ${caught.status})` : ""}`
          : caught instanceof Error
            ? caught.message
            : String(caught);
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Новая задача">
      <form className="modal__card" onSubmit={submit}>
        <header className="modal__head">
          <h2>Новая задача</h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Закрыть">
            Закрыть
          </button>
        </header>

        <label className="field">
          <span>Тип</span>
          <input
            ref={typeRef}
            value={form.type}
            placeholder="delivery"
            onChange={(event) => setForm({ ...form, type: event.target.value })}
          />
        </label>
        {typeError ? <p className="error-text">{typeError}</p> : null}

        <div className="modal__row">
          <label className="field">
            <span>Приоритет (0–1000)</span>
            <input
              type="number"
              min={0}
              max={1000}
              value={form.priority}
              onChange={(event) => setForm({ ...form, priority: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Попыток</span>
            <input
              type="number"
              min={1}
              max={10}
              value={form.maxAttempts}
              onChange={(event) => setForm({ ...form, maxAttempts: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Лимит, сек</span>
            <input
              type="number"
              min={1}
              max={86_400}
              value={form.timeoutSeconds}
              onChange={(event) => setForm({ ...form, timeoutSeconds: event.target.value })}
            />
          </label>
        </div>

        <label className="field">
          <span>Payload (JSON)</span>
          <textarea
            rows={4}
            value={form.payload}
            onChange={(event) => setForm({ ...form, payload: event.target.value })}
          />
        </label>
        {payloadError ? <p className="error-text">{payloadError}</p> : null}

        <label className="field">
          <span>Idempotency-Key</span>
          <input
            value={form.idempotencyKey}
            onChange={(event) => setForm({ ...form, idempotencyKey: event.target.value })}
          />
        </label>

        {error ? (
          <p className="error-text" role="alert">
            {error}
          </p>
        ) : null}

        <footer className="modal__foot">
          <button type="button" className="button button--ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="button button--primary" disabled={!canSubmit}>
            {busy ? "Создаём…" : "Создать"}
          </button>
        </footer>
      </form>
    </div>
  );
}
