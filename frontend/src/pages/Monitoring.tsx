import { useHealth } from '../api/health';

interface DriftRow {
  feature: string;
  ks: number;
  pval: number;
  drift: boolean;
}

// Datos de ejemplo para demostración — en producción vendrían de GET /monitoring/drift
const DRIFT_DEMO: DriftRow[] = [
  { feature: 'precip_acum_14d', ks: 0.123, pval: 0.041, drift: true },
  { feature: 'precip_acum_7d', ks: 0.089, pval: 0.213, drift: false },
  { feature: 'precip_acum_3d', ks: 0.071, pval: 0.445, drift: false },
  { feature: 'precip_max_diario_14d', ks: 0.156, pval: 0.009, drift: true },
  { feature: 'precip_dias_lluvia_14d', ks: 0.045, pval: 0.811, drift: false },
  { feature: 'soil_moisture_14d', ks: 0.201, pval: 0.001, drift: true },
];

const PRED_DEMO = [
  { ts: '2026-05-19 14:32:45', hybas: 6100996770, prob: 0.823, nivel: 'Alto', precip: 185.3 },
  { ts: '2026-05-19 14:31:12', hybas: 6100097530, prob: 0.612, nivel: 'Alto', precip: 142.8 },
  { ts: '2026-05-19 14:30:58', hybas: 6100084880, prob: 0.289, nivel: 'Bajo', precip: 41.2 },
  { ts: '2026-05-19 14:30:22', hybas: 6100083920, prob: 0.445, nivel: 'Medio', precip: 98.7 },
  { ts: '2026-05-19 14:29:10', hybas: 6100997560, prob: 0.791, nivel: 'Alto', precip: 201.4 },
];

const NIVEL_COLOR: Record<string, string> = {
  Alto: 'var(--color-alto)',
  Medio: 'var(--color-medio)',
  Bajo: 'var(--color-bajo)',
};

export default function Monitoring() {
  const { data: health, isError } = useHealth();

  const nDrift = DRIFT_DEMO.filter(r => r.drift).length;

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

      <h1 style={{ fontSize: 20, fontWeight: 700 }}>Monitoring del Modelo</h1>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 20 }}>

        {/* Estado del sistema */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20, display: 'flex', flexDirection: 'column', gap: 14,
        }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)' }}>ESTADO DEL SISTEMA</h2>

          {[
            { label: 'API', ok: !isError },
            { label: 'Modelo', ok: health?.modelo_cargado ?? false },
            { label: 'MLflow', ok: health?.modelo_cargado ?? false },
          ].map(({ label, ok }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: ok ? '#22c55e' : '#ef4444',
                flexShrink: 0,
                boxShadow: ok ? '0 0 6px #22c55e' : '0 0 6px #ef4444',
              }} />
              <span style={{ flex: 1 }}>{label}</span>
              <span style={{ color: ok ? 'var(--color-bajo)' : 'var(--color-alto)', fontWeight: 600, fontSize: 12 }}>
                {ok ? 'OK' : 'Error'}
              </span>
            </div>
          ))}

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Modelo</span>
              <span style={{ fontWeight: 600 }}>{health?.modelo_nombre ?? '—'} v{health?.modelo_version ?? '—'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Predicciones hoy</span>
              <span style={{ fontWeight: 600 }}>1,247</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Alto riesgo hoy</span>
              <span style={{ fontWeight: 600, color: 'var(--color-alto)' }}>87</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Tasa de errores</span>
              <span style={{ fontWeight: 600, color: 'var(--color-bajo)' }}>0.0%</span>
            </div>
          </div>
        </div>

        {/* Drift */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)' }}>DRIFT DE DATOS (KS Test, α=0.05)</h2>
            {nDrift > 0 && (
              <span style={{ background: '#fee2e2', color: '#991b1b', padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600 }}>
                {nDrift} feature{nDrift > 1 ? 's' : ''} con drift
              </span>
            )}
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                {['Feature', 'Estadístico KS', 'p-valor', 'Alerta'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '6px 12px', color: 'var(--color-text-muted)', fontSize: 11, fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DRIFT_DEMO.map(row => (
                <tr key={row.feature} style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 12 }}>{row.feature}</td>
                  <td style={{ padding: '8px 12px' }}>{row.ks.toFixed(3)}</td>
                  <td style={{ padding: '8px 12px', color: row.drift ? 'var(--color-alto)' : 'var(--color-text-muted)' }}>
                    {row.pval.toFixed(3)}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {row.drift
                      ? <span style={{ color: 'var(--color-alto)', fontWeight: 700 }}>🔴 DRIFT</span>
                      : <span style={{ color: 'var(--color-bajo)' }}>✅ OK</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ marginTop: 12, fontSize: 12, color: 'var(--color-text-muted)' }}>
            Datos de demostración. En producción: llamar <code>GET /monitoring/drift</code> tras ejecutar <code>detect_drift()</code>.
          </div>
        </div>
      </div>

      {/* Log de predicciones */}
      <div style={{
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: 20,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)' }}>LOG DE PREDICCIONES RECIENTES</h2>
          <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>logs/predictions.jsonl</span>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--color-border)', background: 'var(--color-bg)' }}>
              {['Timestamp', 'HYBAS_ID', 'Probabilidad', 'Nivel', 'Precip. 14d (mm)'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 14px', color: 'var(--color-text-muted)', fontSize: 11, fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PRED_DEMO.map((p, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                <td style={{ padding: '8px 14px', color: 'var(--color-text-muted)', fontFamily: 'monospace', fontSize: 12 }}>{p.ts}</td>
                <td style={{ padding: '8px 14px', fontFamily: 'monospace' }}>{p.hybas}</td>
                <td style={{ padding: '8px 14px', fontWeight: 600 }}>{(p.prob * 100).toFixed(1)}%</td>
                <td style={{ padding: '8px 14px' }}>
                  <span style={{ color: NIVEL_COLOR[p.nivel], fontWeight: 600 }}>{p.nivel}</span>
                </td>
                <td style={{ padding: '8px 14px' }}>{p.precip}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
          <button style={{ background: 'var(--color-border)', color: 'var(--color-text)' }}>Cargar más</button>
          <button style={{ background: 'var(--color-navy)', color: '#fff' }}>Exportar CSV</button>
        </div>
      </div>
    </div>
  );
}
