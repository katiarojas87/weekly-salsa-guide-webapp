import { BrowserRouter, Routes, Route } from 'react-router-dom';
import EventMap from './pages/EventMap';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<EventMap />} />
        {/* Future routes: /teachers, /profile, /marketplace */}
      </Routes>
    </BrowserRouter>
  );
}
