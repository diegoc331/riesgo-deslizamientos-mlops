import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Navbar from './components/layout/Navbar';
import MapaRiesgo from './pages/MapaRiesgo';
import Prediccion from './pages/Prediccion';
import Prioridades from './pages/Prioridades';
import ImpactoEconomico from './pages/ImpactoEconomico';
import Monitoring from './pages/Monitoring';
import Modelo from './pages/Modelo';

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Routes>
          <Route path="/" element={<MapaRiesgo />} />
          <Route path="/prioridades" element={<Prioridades />} />
          <Route path="/prediccion/:hybasId?" element={<Prediccion />} />
          <Route path="/impacto" element={<ImpactoEconomico />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/modelo" element={<Modelo />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
