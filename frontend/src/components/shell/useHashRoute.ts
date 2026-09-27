"use client";

import { useCallback, useEffect, useState } from "react";
import { hashFor, parseHash, type Space } from "@/features/shell/space";

/** The current space, kept in the URL hash so it survives reloads and can be shared. */
export function useHashRoute(): {
  space: Space;
  param: string | null;
  go(space: Space, param?: string | null): void;
} {
  const [route, setRoute] = useState(() =>
    typeof window === "undefined" ? parseHash("") : parseHash(window.location.hash),
  );
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const go = useCallback((space: Space, param: string | null = null) => {
    const hash = hashFor(space, param);
    const url = `${window.location.pathname}${window.location.search}${hash}`;
    window.history.pushState(null, "", url);
    setRoute({ space, param });
  }, []);
  return { ...route, go };
}
