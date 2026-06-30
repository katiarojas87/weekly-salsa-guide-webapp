import { useState } from 'react';
import './LocationGate.css';

const PRESET_CITIES = [
  { label: 'Antwerp',   lat: 51.2213, lng: 4.4051 },
  { label: 'Brussels',  lat: 50.8503, lng: 4.3517 },
  { label: 'Amsterdam', lat: 52.3676, lng: 4.9041 },
  { label: 'Rotterdam', lat: 51.9244, lng: 4.4777 },
  { label: 'Ghent',     lat: 51.0543, lng: 3.7174 },
];

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

export function LocationGate({ status, error, onRequestLocation, onSelectCoords }) {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState([]);

  async function handleSearch(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json?access_token=${MAPBOX_TOKEN}&country=BE,NL,FR,DE&types=place,locality&limit=4`;
      const res = await fetch(url);
      const data = await res.json();
      setResults((data.features ?? []).map(f => ({
        label: f.place_name,
        lat: f.center[1],
        lng: f.center[0],
      })));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="gate">
      <div className="gate-card">
        <div className="gate-brand">Weekly Salsa Guide</div>
        <h1 className="gate-heading">Find salsa &amp; bachata<br />events near you</h1>
        <p className="gate-sub">
          {error ?? 'Share your location to discover events on the map.'}
        </p>

        {status !== 'denied' && status !== 'unavailable' && (
          <button className="gate-btn-primary" onClick={onRequestLocation} disabled={status === 'requesting'}>
            {status === 'requesting' ? 'Requesting…' : 'Use my location'}
          </button>
        )}

        <div className="gate-divider">
          <span>or choose a city</span>
        </div>

        <div className="gate-presets">
          {PRESET_CITIES.map(c => (
            <button
              key={c.label}
              className="gate-city-btn"
              onClick={() => onSelectCoords({ lat: c.lat, lng: c.lng })}
            >
              {c.label}
            </button>
          ))}
        </div>

        <form className="gate-search" onSubmit={handleSearch}>
          <input
            type="text"
            className="gate-input"
            placeholder="Search another city…"
            value={query}
            onChange={e => { setQuery(e.target.value); setResults([]); }}
          />
          <button type="submit" className="gate-search-btn" disabled={searching}>
            {searching ? '…' : '→'}
          </button>
        </form>

        {results.length > 0 && (
          <ul className="gate-results">
            {results.map((r, i) => (
              <li key={i}>
                <button className="gate-result-item" onClick={() => onSelectCoords({ lat: r.lat, lng: r.lng })}>
                  {r.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
