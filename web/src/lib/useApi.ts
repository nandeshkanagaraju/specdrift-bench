import { useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** One small data hook: abortable, and it never leaves a stale error on screen. */
export function useApi<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    const controller = new AbortController();
    let live = true;
    setState((previous) => ({ ...previous, loading: true, error: null }));

    load(controller.signal)
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error: unknown) => {
        if (controller.signal.aborted || !live) return;
        setState({
          data: null,
          error: error instanceof Error ? error.message : String(error),
          loading: false,
        });
      });

    return () => {
      live = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
