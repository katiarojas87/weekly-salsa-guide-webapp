import { useRef, useEffect, useState, useCallback } from 'react';
import { DATE_FILTERS } from '../utils/dateFilters';
import './DateFilterBar.css';

export function DateFilterBar({ activeFilter, onChange }) {
  const containerRef = useRef(null);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  const measure = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const idx = DATE_FILTERS.findIndex(f => f.id === activeFilter);
    const btn = container.querySelectorAll('[data-filter]')[idx];
    if (!btn) return;
    const cRect = container.getBoundingClientRect();
    const bRect = btn.getBoundingClientRect();
    setIndicator({ left: bRect.left - cRect.left, width: bRect.width });
  }, [activeFilter]);

  useEffect(() => {
    measure();
    // Re-measure once fonts settle
    document.fonts.ready.then(measure);
    const ro = new ResizeObserver(measure);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [measure]);

  return (
    <div className="filter-bar" ref={containerRef} role="group" aria-label="Date filter">
      <div
        className="filter-indicator"
        style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width }}
      />
      {DATE_FILTERS.map(f => (
        <button
          key={f.id}
          data-filter={f.id}
          className={`filter-btn${activeFilter === f.id ? ' active' : ''}`}
          onClick={() => onChange(f.id)}
          aria-pressed={activeFilter === f.id}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
