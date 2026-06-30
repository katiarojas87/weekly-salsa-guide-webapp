import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL;
const COLD_START_THRESHOLD_MS = 6000;

export function useEvents(coords, radiusKm = 30) {
  const [state, setState] = useState({
    events: [],
    loading: false,
    slowWakeup: false,   // true after threshold — server is cold-starting
    error: null,
    lastFetchedCoords: null,
  });

  const abortRef = useRef(null);
  const slowTimerRef = useRef(null);

  const fetch_ = useCallback(async (lat, lng, radius) => {
    if (abortRef.current) abortRef.current.abort();
    clearTimeout(slowTimerRef.current);

    const controller = new AbortController();
    abortRef.current = controller;

    setState(s => ({ ...s, loading: true, slowWakeup: false, error: null }));

    slowTimerRef.current = setTimeout(() => {
      setState(s => (s.loading ? { ...s, slowWakeup: true } : s));
    }, COLD_START_THRESHOLD_MS);

    try {
      const url = `${API_BASE}/events?lat=${lat}&lng=${lng}&radius_km=${radius}`;
      const res = await window.fetch(url, { signal: controller.signal });

      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();

      clearTimeout(slowTimerRef.current);
      setState({
        events: data.events ?? [],
        loading: false,
        slowWakeup: false,
        error: null,
        lastFetchedCoords: { lat, lng },
      });
    } catch (err) {
      clearTimeout(slowTimerRef.current);
      if (err.name === 'AbortError') return;
      setState(s => ({
        ...s,
        loading: false,
        slowWakeup: false,
        error: 'Could not load events. Check your connection or try again.',
      }));
    }
  }, []);

  useEffect(() => {
    if (!coords) return;
    fetch_(coords.lat, coords.lng, radiusKm);
    return () => {
      abortRef.current?.abort();
      clearTimeout(slowTimerRef.current);
    };
  }, [coords?.lat, coords?.lng, radiusKm, fetch_]);

  const refetch = useCallback(() => {
    if (coords) fetch_(coords.lat, coords.lng, radiusKm);
  }, [coords, radiusKm, fetch_]);

  return { ...state, refetch };
}
