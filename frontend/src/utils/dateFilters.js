export const DATE_FILTERS = [
  { id: 'today',     label: 'Today' },
  { id: 'tomorrow',  label: 'Tomorrow' },
  { id: 'this_week', label: 'This Week' },
  { id: 'next_week', label: 'Next Week' },
];

function parseEventDate(dateStr) {
  // Handles YYYY-MM-DD or ISO strings — parse as local date
  if (!dateStr) return null;
  const parts = dateStr.slice(0, 10).split('-').map(Number);
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function startOfDay(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function getMondayOfWeek(d) {
  const day = d.getDay(); // 0 Sun, 1 Mon...
  const diff = (day === 0 ? -6 : 1 - day);
  const monday = new Date(d);
  monday.setDate(d.getDate() + diff);
  return startOfDay(monday);
}

export function filterEventsByDate(events, filterId) {
  const now = startOfDay(new Date());
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1);

  const thisMonday = getMondayOfWeek(now);
  const thisSunday = new Date(thisMonday); thisSunday.setDate(thisMonday.getDate() + 6);
  const nextMonday = new Date(thisMonday); nextMonday.setDate(thisMonday.getDate() + 7);
  const nextSunday = new Date(nextMonday); nextSunday.setDate(nextMonday.getDate() + 6);

  return events.filter(event => {
    const d = parseEventDate(event.date);
    if (!d) return false;

    switch (filterId) {
      case 'today':
        return d.getTime() === now.getTime();
      case 'tomorrow':
        return d.getTime() === tomorrow.getTime();
      case 'this_week':
        return d >= now && d <= thisSunday;
      case 'next_week':
        return d >= nextMonday && d <= nextSunday;
      default:
        return true;
    }
  });
}

export function formatEventDate(dateStr) {
  const d = parseEventDate(dateStr);
  if (!d) return dateStr ?? '';
  return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
}

export function formatDistance(distanceKm) {
  if (distanceKm == null) return null;
  if (distanceKm < 1) return `${Math.round(distanceKm * 1000)} m away`;
  return `${distanceKm.toFixed(1)} km away`;
}
