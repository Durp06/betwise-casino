/**
 * usePrevious — returns the value from the previous render.
 *
 * The building block for snapshot diffing (useTableActionFeed): compare the prior
 * polled table state against the current one to detect what changed.
 */
import { useEffect, useRef } from "react";

export function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined);
  useEffect(() => {
    ref.current = value;
  }, [value]);
  return ref.current;
}
