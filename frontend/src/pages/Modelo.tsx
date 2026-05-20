import { useMetadata } from '../api/metadata';
import { useHealth } from '../api/health';

const FEATURE_GROUPS = {
  'Precipitación CHIRPS (5)': [
    'precip_acum_14d', 'precip_acum_7d', 'precip_acum_3d',
    'precip_max_diario_14d', 'precip_dias_lluvia_14d',
  ],
  'Humedad ERA5-Land (1)': ['soil_moisture_14d'],
  'Estáticas HydroSHEDS (4)': ['SUB_AREA', 'UP_AREA', 'DIST_MAIN', 'ORDER'],
  'Ciclicidad temporal (4)': ['semana_sin', 'semana_cos', 'mes_sin', 'mes_cos'],
};

const METRICAS = [
  { label: 'AUC-ROC (grid completo)', value: '0.670', note: 'métrica honesta', ok: true },
  { label: 'Recall', value: '0.800', note: '80% de eventos detectados', ok: true },
  { label: 'Precision', value: '0.150', note: '15% de alertas son positivos reales', ok: null },
  { label: 'F1-score', value: '0.260', note: '', ok: null },
  { label: 'AUC pseudo-ausencias', value: '0.993', note: '⚠ inflado por filtro de precip. — NO usar', ok: false },
];

export default function Modelo() {
  const { data: meta, isLoading, isError } = useMetadata();
  const { data: health } = useHealth();

  if (isLoading) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>
      Cargando metadatos del modelo...
    </div>
  );

  if (isError || !meta) return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <div style={{ color: 'var(--color-alto)', marginBottom: 8 }}>Modelo no disponible</div>
      <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
        La API en localhost:8000 no está respondiendo o el modelo no está cargado en MLflow Registry.
      </div>
    </div>
  );

  return (
    <div style={{ padding: 24, maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

      <h1 style={{ fontSize: 20, fontWeight: 700 }}>Metadatos del Modelo en Producción</h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* Identificación */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20,
        }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 14 }}>IDENTIFICACIÓN</h2>
          {[
            ['Nombre', meta.modelo_nombre],
            ['Versión', `${meta.modelo_version} (${health?.status === 'ok' ? 'Staging' : 'No cargado'})`],
            ['Algoritmo', 'BaggingPuClassifier (PU-Learning)'],
            ['Departamento', meta.departamento.charAt(0).toUpperCase() + meta.departamento.slice(1)],
            ['Período de entrenamiento', meta.periodo_entrenamiento],
            ['Granularidad', `Cuenca HydroSHEDS nivel 10`],
            ['Cuencas monitoreadas', '549'],
            ['Horizonte predicción', '7 días'],
          ].map(([k, v]) => (
            <div key={String(k)} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
              padding: '7px 0', borderBottom: '1px solid var(--color-border)', fontSize: 13,
            }}>
              <span style={{ color: 'var(--color-text-muted)', flexShrink: 0, marginRight: 12 }}>{k}</span>
              <span style={{ fontWeight: 500, textAlign: 'right', wordBreak: 'break-all' }}>{v}</span>
            </div>
          ))}
        </div>

        {/* Métricas */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20,
        }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 14 }}>MÉTRICAS DE RENDIMIENTO</h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {METRICAS.map(({ label, value, note, ok }) => (
              <div key={label} style={{
                background: ok === false ? '#fef9c3' : 'var(--color-bg)',
                border: `1px solid ${ok === false ? '#fde047' : 'var(--color-border)'}`,
                borderRadius: 6, padding: '10px 14px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13 }}>{label}</span>
                  <span style={{
                    fontSize: 20, fontWeight: 700,
                    color: ok === true ? 'var(--color-bajo)' : ok === false ? '#854d0e' : 'var(--color-text)',
                  }}>{value}</span>
                </div>
                {note && <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 2 }}>{note}</div>}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 16, fontSize: 12, color: 'var(--color-text-muted)', borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
            <b>Umbrales de promoción a Staging:</b><br />
            AUC-ROC ≥ {meta.umbral_staging_auc} AND Precision ≥ {meta.umbral_staging_precision}
          </div>
        </div>
      </div>

      {/* Features */}
      <div style={{
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: 20,
      }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 16 }}>
          FEATURES DEL MODELO ({meta.n_features} en total)
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          {Object.entries(FEATURE_GROUPS).map(([group, features]) => (
            <div key={group} style={{ background: 'var(--color-bg)', borderRadius: 6, padding: '12px 14px' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-navy)', marginBottom: 8 }}>{group}</div>
              {features.map(f => (
                <div key={f} style={{
                  fontFamily: 'monospace', fontSize: 12,
                  padding: '3px 0',
                  color: 'var(--color-text)',
                  borderBottom: '1px solid var(--color-border)',
                }}>
                  {f}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Niveles de riesgo */}
      <div style={{
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: 20, display: 'flex', gap: 20,
      }}>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 12 }}>NIVELES DE RIESGO</h2>
          {[
            { nivel: 'Bajo', rango: 'prob < 0.30', color: 'var(--color-bajo)' },
            { nivel: 'Medio', rango: '0.30 ≤ prob < 0.60', color: 'var(--color-medio)' },
            { nivel: 'Alto', rango: 'prob ≥ 0.60', color: 'var(--color-alto)' },
          ].map(({ nivel, rango, color }) => (
            <div key={nivel} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <span style={{ width: 12, height: 12, borderRadius: '50%', background: color, flexShrink: 0 }} />
              <span style={{ fontWeight: 600, color, minWidth: 48 }}>{nivel}</span>
              <span style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--color-text-muted)' }}>{rango}</span>
            </div>
          ))}
        </div>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 12 }}>DESCRIPCIÓN</h2>
          <p style={{ fontSize: 13, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>{meta.descripcion}</p>
        </div>
      </div>
    </div>
  );
}
