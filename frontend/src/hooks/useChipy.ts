/**
 * useChipy.ts — wraps streamAdvice and pipes chunks into gameStore.
 * Returns { ask, loading, error } for ChipyPanel consumers.
 */
import { useState, useCallback } from "react";
import type { Action, AdviceResult } from "../types";
import { streamAdvice } from "../api/client";
import { useGameStore } from "../store/gameStore";

interface UseChipyResult {
  ask: (handId: string, guess: Action) => void;
  loading: boolean;
  error: string | null;
  result: AdviceResult | null;
}

export function useChipy(): UseChipyResult {
  const { setChipyMessage, setChipyLoading } = useGameStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdviceResult | null>(null);

  const ask = useCallback(
    (handId: string, guess: Action) => {
      setLoading(true);
      setError(null);
      setResult(null);
      setChipyLoading(true);
      setChipyMessage("");

      streamAdvice(
        handId,
        guess,
        (chunk: string) => {
          setChipyMessage(chunk);
        },
        (finalResult: AdviceResult) => {
          setResult(finalResult);
          setLoading(false);
          setChipyLoading(false);
        },
        (errMsg: string) => {
          setError(errMsg);
          setLoading(false);
          setChipyLoading(false);
        },
      );
    },
    [setChipyMessage, setChipyLoading],
  );

  return { ask, loading, error, result };
}
