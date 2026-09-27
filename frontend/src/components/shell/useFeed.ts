"use client";

import { useMemo } from "react";
import { PollingResource, type ResourceState } from "@/features/intel/resource";
import { useResource } from "@/features/intel/useResource";

/**
 * Poll `load` every `intervalMs` while mounted. `load` must be stable
 * (module-level or memoised): a new function starts a new resource.
 */
export function useFeed<T>(
  load: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
): ResourceState<T> {
  const resource = useMemo(() => new PollingResource<T>(load, intervalMs), [load, intervalMs]);
  return useResource(resource);
}
