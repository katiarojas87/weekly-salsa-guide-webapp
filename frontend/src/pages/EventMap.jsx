import { useState, useCallback, useEffect, useRef } from 'react';
import Map, { Marker, Source, Layer, NavigationControl } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';

import { useGeolocation } from '../hooks/useGeolocation';
import { useEvents } from '../hooks/useEvents';
import { filterEventsByDate } from '../utils/dateFilters';
import { DateFilterBar } from '../components/DateFilterBar';
import { EventDetailSheet } from '../components/EventDetailSheet';
import { LocationGate } from '../components/LocationGate';
import './EventMap.css';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const DEFAULT_RADIUS = 30;

// Center of Belgium/Netherlands as fallback view
const DEFAULT_VIEWPORT = { longitude: 4.3517, latitude: 50.85, zoom: 8 };

export default function EventMap() {
  const geo = useGeolocation();
  const [manualCoords, setManualCoords] = useState(null);
  const [activeFilter, setActiveFilter] = useState('this_week');
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT);
  const mapRef = useRef(null);

  const coords = geo.coords ?? manualCoords;
  const { events, loading, slowWakeup, error, refetch } = useEvents(coords, DEFAULT_RADIUS);

  // Request geolocation on mount
  useEffect(() => { geo.request(); }, []);

  // Fly to user location when granted
  useEffect(() => {
    if (geo.status === 'granted' && geo.coords) {
      setViewport(v => ({ ...v, longitude: geo.coords.lng, latitude: geo.coords.lat, zoom: 11 }));
    }
  }, [geo.status]);

  // Fly to manually selected city
  const handleSelectCoords = useCallback((c) => {
    setManualCoords(c);
    setViewport(v => ({ ...v, longitude: c.lng, latitude: c.lat, zoom: 11 }));
  }, []);

  const filteredEvents = filterEventsByDate(events, activeFilter);

  // GeoJSON for clustering
  const geojson = {
    type: 'FeatureCollection',
    features: filteredEvents.map(ev => ({
      type: 'Feature',
      properties: { id: `${ev.event_name}-${ev.date}-${ev.lat}-${ev.lng}`, event: JSON.stringify(ev) },
      geometry: { type: 'Point', coordinates: [ev.lng, ev.lat] },
    })),
  };

  const handleMapClick = useCallback((e) => {
    const features = e.features ?? [];
    const cluster = features.find(f => f.layer?.id === 'clusters');
    const point = features.find(f => f.layer?.id === 'unclustered-point');

    if (cluster) {
      const map = mapRef.current?.getMap();
      const source = map?.getSource('events');
      source?.getClusterExpansionZoom(cluster.properties.cluster_id, (err, zoom) => {
        if (!err) {
          map.easeTo({
            center: cluster.geometry.coordinates,
            zoom: zoom + 1,
            duration: 400,
          });
        }
      });
    } else if (point) {
      try {
        const ev = JSON.parse(point.properties.event);
        setSelectedEvent(ev);
      } catch { /* ignore */ }
    } else {
      setSelectedEvent(null);
    }
  }, []);

  const showGate = geo.status === 'idle' || geo.status === 'requesting' || geo.status === 'denied' || geo.status === 'unavailable';
  // Only show gate if we also have no manual coords
  const needsGate = showGate && !manualCoords;

  return (
    <div className="map-root">
      {/* Full-bleed map */}
      <Map
        ref={mapRef}
        {...viewport}
        onMove={e => setViewport(e.viewState)}
        mapboxAccessToken={MAPBOX_TOKEN}
        mapStyle="mapbox://styles/mapbox/light-v11"
        style={{ width: '100%', height: '100%' }}
        interactiveLayerIds={['clusters', 'unclustered-point']}
        onClick={handleMapClick}
        cursor="auto"
      >
        <NavigationControl position="bottom-right" showCompass={false} />

        {/* Event clusters + dots */}
        <Source
          id="events"
          type="geojson"
          data={geojson}
          cluster={true}
          clusterMaxZoom={14}
          clusterRadius={40}
        >
          {/* Cluster circles */}
          <Layer
            id="clusters"
            type="circle"
            filter={['has', 'point_count']}
            paint={{
              'circle-color': '#C4622D',
              'circle-opacity': 0.88,
              'circle-radius': [
                'step', ['get', 'point_count'],
                18, 5, 24, 20, 30
              ],
            }}
          />
          {/* Cluster count labels */}
          <Layer
            id="cluster-count"
            type="symbol"
            filter={['has', 'point_count']}
            layout={{
              'text-field': '{point_count_abbreviated}',
              'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
              'text-size': 12,
            }}
            paint={{ 'text-color': '#FFFDF9' }}
          />
          {/* Individual event dots */}
          <Layer
            id="unclustered-point"
            type="circle"
            filter={['!', ['has', 'point_count']]}
            paint={{
              'circle-color': '#C4622D',
              'circle-radius': 8,
              'circle-opacity': 0.9,
              'circle-stroke-width': 2,
              'circle-stroke-color': '#FFFDF9',
            }}
          />
        </Source>

        {/* User location marker */}
        {coords && (
          <Marker longitude={coords.lng} latitude={coords.lat} anchor="center">
            <div className="user-marker">
              <div className="user-marker-dot" />
              <div className="user-marker-ring" />
            </div>
          </Marker>
        )}
      </Map>

      {/* Floating header strip */}
      {!needsGate && (
        <div className="map-header">
          <div className="map-wordmark">Weekly Salsa Guide</div>
          <DateFilterBar activeFilter={activeFilter} onChange={setActiveFilter} />
        </div>
      )}

      {/* Status toasts */}
      {!needsGate && loading && (
        <div className="map-toast">
          {slowWakeup
            ? 'The server is waking up — hang tight, this can take up to a minute…'
            : 'Loading events…'}
        </div>
      )}

      {!needsGate && error && !loading && (
        <div className="map-toast map-toast--error">
          {error}{' '}
          <button className="toast-retry" onClick={refetch}>Retry</button>
        </div>
      )}

      {!needsGate && !loading && !error && filteredEvents.length === 0 && events.length > 0 && (
        <div className="map-empty">
          No events for this date range — try a different filter
        </div>
      )}

      {!needsGate && !loading && !error && events.length === 0 && coords && (
        <div className="map-empty">
          No events found within {DEFAULT_RADIUS} km for this area
        </div>
      )}

      {/* Location gate overlay */}
      {needsGate && (
        <LocationGate
          status={geo.status}
          error={geo.error}
          onRequestLocation={geo.request}
          onSelectCoords={handleSelectCoords}
        />
      )}

      {/* Event detail sheet */}
      {selectedEvent && (
        <EventDetailSheet
          event={selectedEvent}
          userCoords={coords}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  );
}
