import { useCallback, useEffect, useRef, useState } from "react";

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: (silent?: boolean) => void;
}

/** Minimal data hook: fetch on mount/dep change, manual refetch (optionally
 * silent so live updates don't flash loading states). */
export function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[]): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const generation = useRef(0);

  const load = useCallback((silent = false) => {
    const ticket = ++generation.current;
    if (!silent) setLoading(true);
    fetcherRef
      .current()
      .then((result) => {
        if (ticket !== generation.current) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (ticket !== generation.current) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (ticket === generation.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, refetch: load };
}
