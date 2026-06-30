import { useEffect, useRef } from 'react';
import { formatEventDate, formatDistance } from '../utils/dateFilters';
import './EventDetailSheet.css';

function MetaRow({ label, value }) {
  if (!value) return null;
  return (
    <div className="meta-row">
      <span className="meta-label">{label}</span>
      <span className="meta-value">{value}</span>
    </div>
  );
}

export function EventDetailSheet({ event, userCoords, onClose }) {
  const sheetRef = useRef(null);

  // Close on backdrop click
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  if (!event) return null;

  const distance = event.distance_km != null
    ? formatDistance(event.distance_km)
    : null;

  const price = event.price?.trim() ? event.price : 'Free';
  const hasSocial = event.facebook_url || event.instagram_url;

  return (
    <div className="sheet-backdrop" onClick={onClose} aria-modal="true" role="dialog">
      <div
        className="sheet"
        ref={sheetRef}
        onClick={e => e.stopPropagation()}
      >
        <div className="sheet-handle" />

        <div className="sheet-scroll">
          {/* Event name */}
          <h2 className="sheet-event-name">{event.event_name}</h2>

          {/* Distance badge */}
          {distance && (
            <span className="sheet-distance">{distance}</span>
          )}

          <div className="sheet-divider" />

          {/* Meta rows */}
          <div className="sheet-meta">
            <MetaRow label="Date" value={formatEventDate(event.date)} />
            <MetaRow label="Time" value={event.time} />
            <MetaRow label="Venue" value={event.venue} />
            <MetaRow label="City" value={event.city} />
            <MetaRow label="Organiser" value={event.organizer} />
            <MetaRow label="Price" value={price} />
          </div>

          {/* Description */}
          {event.description && (
            <p className="sheet-description">{event.description}</p>
          )}

          {/* Social links */}
          {hasSocial && (
            <div className="sheet-social">
              {event.facebook_url && (
                <a href={event.facebook_url} target="_blank" rel="noopener noreferrer" className="social-link">
                  Facebook
                </a>
              )}
              {event.instagram_url && (
                <a href={event.instagram_url} target="_blank" rel="noopener noreferrer" className="social-link">
                  Instagram
                </a>
              )}
            </div>
          )}

          {/* CTA */}
          {event.source_url && (
            <a
              href={event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="sheet-cta"
            >
              View event →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
