import type { ReactNode } from "react";

export function ErrorBanner({
  message,
  onRetry,
  children,
}: {
  message: string;
  onRetry?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="banner banner--error" role="alert">
      <div>
        <strong>Не удалось загрузить данные</strong>
        <p>{message}</p>
        {children}
      </div>
      {onRetry ? (
        <button type="button" className="button" onClick={onRetry}>
          Повторить
        </button>
      ) : null}
    </div>
  );
}
