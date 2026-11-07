import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  updatedAt: Date | null;
}

export function useResource<T>(loader: () => Promise<T>, deps: unknown[], intervalMs = 0): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [nonce, setNonce] = useState(0);
  const alive = useRef(true);

  const reload = useCallback(() => {
    setNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    alive.current = true;
    let cancelled = false;

    async function run() {
      setLoading(true);
      try {
        const result = await loader();
        if (cancelled) {
          return;
        }
        setData(result);
        setError(null);
        setUpdatedAt(new Date());
      } catch (caught) {
        if (cancelled) {
          return;
        }
        const message =
          caught instanceof ApiError
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : String(caught);
        setError(message);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void run();

    if (intervalMs <= 0) {
      return () => {
        cancelled = true;
        alive.current = false;
      };
    }

    const timer = setInterval(() => {
      if (alive.current) {
        void run();
      }
    }, intervalMs);

    return () => {
      cancelled = true;
      alive.current = false;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs, nonce]);

  return { data, error, loading, reload, updatedAt };
}
