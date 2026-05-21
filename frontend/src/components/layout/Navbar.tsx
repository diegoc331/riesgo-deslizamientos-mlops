import { NavLink } from 'react-router-dom';
import { useHealth } from '../../api/health';

const navItems = [
  { to: '/', label: 'Mapa', exact: true },
  { to: '/prioridades', label: 'Prioridades' },
  { to: '/prediccion', label: 'Cuenca' },
  { to: '/impacto', label: 'Impacto' },
  { to: '/monitoring', label: 'Monitoring' },
  { to: '/modelo', label: 'Modelo' },
];

export default function Navbar() {
  const { data: health, isError } = useHealth();
  const ok = !isError && health?.modelo_cargado;

  return (
    <nav style={{
      background: 'var(--color-navy)',
      display: 'flex',
      alignItems: 'center',
      gap: 0,
      padding: '0 24px',
      height: 52,
      boxShadow: '0 2px 4px rgba(0,0,0,0.25)',
      position: 'sticky',
      top: 0,
      zIndex: 1000,
    }}>
      <span style={{ color: '#fff', fontWeight: 700, fontSize: 16, marginRight: 32, letterSpacing: '-0.3px' }}>
        TerraAlert
      </span>

      <div style={{ display: 'flex', gap: 4, flex: 1 }}>
        {navItems.map(({ to, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            style={({ isActive }) => ({
              color: isActive ? '#fff' : 'rgba(255,255,255,0.65)',
              background: isActive ? 'rgba(255,255,255,0.12)' : 'transparent',
              borderRadius: 6,
              padding: '6px 14px',
              fontSize: 13,
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.15s',
            })}
          >
            {label}
          </NavLink>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          width: 8, height: 8,
          borderRadius: '50%',
          background: ok ? '#22c55e' : '#ef4444',
          display: 'inline-block',
          boxShadow: ok ? '0 0 6px #22c55e' : '0 0 6px #ef4444',
        }} />
        <span style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>
          {ok ? `v${health?.modelo_version ?? '—'} OK` : 'Sin modelo'}
        </span>
      </div>
    </nav>
  );
}
