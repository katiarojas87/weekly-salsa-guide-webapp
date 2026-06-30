import { useState, useCallback } from 'react';

export function useGeolocation() {
  const [state, setState] = useState({
    coords: null,       // { lat, lng }
    status: 'idle',     // 'idle' | 'requesting' | 'granted' | 'denied' | 'unavailable'
    error: null,
  });

  const request = useCallback(() => {
    if (!navigator.geolocation) {
      setState(s => ({ ...s, status: 'unavailable', error: 'Geolocation is not supported by your browser.' }));
      return;
    }

    setState(s => ({ ...s, status: 'requesting', error: null }));

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setState({
          coords: { lat: position.coords.latitude, lng: position.coords.longitude },
          status: 'granted',
          error: null,
        });
      },
      (err) => {
        const isDenied = err.code === err.PERMISSION_DENIED;
        setState({
          coords: null,
          status: isDenied ? 'denied' : 'unavailable',
          error: isDenied
            ? 'Location access was denied. Choose a city below to continue.'
            : 'Could not determine your location. Choose a city below.',
        });
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 }
    );
  }, []);

  return { ...state, request };
}
