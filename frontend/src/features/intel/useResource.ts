"use client";

import { useEffect, useState } from "react";
import type { PollingResource, ResourceState } from "./resource";

/** Subscribe a component to a PollingResource while it is mounted. */
export function useResource<T>(resource: PollingResource<T>): ResourceState<T> {
  const [state, setState] = useState(resource.snapshot);
  useEffect(() => {
    const off = resource.subscribe(setState);
    resource.start();
    setState(resource.snapshot);
    return () => {
      off();
      resource.stop();
    };
  }, [resource]);
  return state;
}
