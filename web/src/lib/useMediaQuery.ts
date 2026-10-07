"use client";
import { useCallback, useSyncExternalStore } from "react";

/** `window.matchMedia(q).matches`, reactivo. En el server (y durante la hidratación) devuelve `enServer`. */
export function useMediaQuery(q: string, enServer = true): boolean {
  const subscribe = useCallback((cb: () => void) => {
    const mq = window.matchMedia(q);
    mq.addEventListener("change", cb);
    return () => mq.removeEventListener("change", cb);
  }, [q]);
  return useSyncExternalStore(subscribe, () => window.matchMedia(q).matches, () => enServer);
}
