import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import RiskGauge from '../components/charts/RiskGauge';
import RiskBadge from '../components/ui/RiskBadge';
import { usePredict, useImpacto, calcSeasonality } from '../api/predict';
import type { PredictRequest, NivelRiesgo } from '../types';

const SEASON = calcSeasonality();

const DEFAULT: Omit<PredictRequest, 'hybas_id'> = {
  precip_acum_14d: 82.4,
  precip_acum_7d: 45.1,
  precip_acum_3d: 18.2,
  precip_max_diario_14d: 22.7,
  precip_dias_lluvia_14d: 9,
  SUB_AREA: 245.8,
  UP_AREA: 1823.4,
  DIST_MAIN: 18.6,
  ORDER: 4,
  soil_moisture_14d: 0.31,
  ...SEASON,
};

type FieldKey = keyof Omit<PredictRequest, 'hybas_id'>;

const FIELDS: { key: FieldKey; label: string; unit: string; min?: number; max?: number; step?: number }[] = [
  { key: 'precip_acum_14d', label: 'Precipitación acum. 14d', unit: 'mm', min: 0, step: 0.1 },
  { key: 'precip_acum_7d', label: 'Precipitación acum. 7d', unit: 'mm', min: 0, step: 0.1 },
  { key: 'precip_acum_3d', label: 'Precipitación acum. 3d', unit: 'mm', min: 0, step: 0.1 },
  { key: 'precip_max_diario_14d', label: 'Máx. diario 14d', unit: 'mm/día', min: 0, step: 0.1 },
  { key: 'precip_dias_lluvia_14d', label: 'Días con lluvia (14d)', unit: 'días', min: 0, max: 14, step: 1 },
  { key: 'soil_moisture_14d', label: 'Humedad suelo 14d', unit: 'm³/m³', min: 0, max: 1, step: 0.01 },
  { key: 'SUB_AREA', label: 'Área sub-cuenca', unit: 'km²', min: 0.1, step: 0.1 },
  { key: 'UP_AREA', label: 'Área drenaje aguas arriba', unit: 'km²', min: 0.1, step: 0.1 },
  { key: 'DIST_MAIN', label: 'Distancia cauce principal', unit: 'km', min: 0, step: 0.1 },
  { key: 'ORDER', label: 'Orden de Strahler', unit: '', min: 1, max: 11, step: 1 },
  { key: 'semana_sin', label: 'Semana sin (auto)', unit: '', min: -1, max: 1, step: 0.001 },
  { key: 'semana_cos', label: 'Semana cos (auto)', unit: '', min: -1, max: 1, step: 0.001 },
  { key: 'mes_sin', label: 'Mes sin (auto)', unit: '', min: -1, max: 1, step: 0.001 },
  { key: 'mes_cos', label: 'Mes cos (auto)', unit: '', min: -1, max: 1, step: 0.001 },
];

export default function Prediccion() {
  const { hybasId } = useParams<{ hybasId?: string }>();
  const navigate = useNavigate();
  const { data: impacto = [] } = useImpacto();
  const { mutate: predict, data: result, isPending, isError, reset } = usePredict();

  const [hybas, setHybas] = useState<number>(hybasId ? parseInt(hybasId) : 6100996770);
  const [form, setForm] = useState<Omit<PredictRequest, 'hybas_id'>>(DEFAULT);

  const imp = impacto.find(i => i.HYBAS_ID === hybas);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    predict({ hybas_id: hybas, ...form });
  };

  const handleChange = (key: FieldKey, val: string) => {
    setForm(f => ({ ...f, [key]: parseFloat(val) || 0 }));
    reset();
  };

  return (
    <div style={{ padding: 24, maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => navigate('/')} style={{ background: 'var(--color-border)', color: 'var(--color-text)', padding: '6px 12px' }}>
          ← Mapa
        </button>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Predicción Individual por Cuenca</h1>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20 }}>

        {/* Formulario */}
        <form onSubmit={handleSubmit} style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20, display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', display: 'block', marginBottom: 4 }}>
              HYBAS_ID (cuenca)
            </label>
            <input
              type="number"
              value={hybas}
              onChange={e => { setHybas(parseInt(e.target.value)); reset(); }}
            />
          </div>

          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
            borderTop: '1px solid var(--color-border)', paddingTop: 12, marginTop: 4,
          }}>
            {FIELDS.map(({ key, label, unit, min, max, step }) => (
              <div key={key}>
                <label style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-muted)', display: 'block', marginBottom: 3 }}>
                  {label} {unit && <span style={{ opacity: 0.6 }}>({unit})</span>}
                </label>
                <input
                  type="number"
                  value={form[key] as number}
                  min={min}
                  max={max}
                  step={step}
                  onChange={e => handleChange(key, e.target.value)}
                />
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button type="submit" disabled={isPending}
              style={{ background: 'var(--color-navy)', color: '#fff', flex: 1, padding: '10px 0', fontSize: 14 }}>
              {isPending ? 'Calculando...' : 'Predecir'}
            </button>
            <button type="button" onClick={() => { setForm(DEFAULT); reset(); }}
              style={{ background: 'var(--color-border)', color: 'var(--color-text)' }}>
              Limpiar
            </button>
          </div>

          {isError && (
            <div style={{ background: '#fee2e2', color: '#991b1b', padding: '8px 12px', borderRadius: 6, fontSize: 13 }}>
              Error al conectar con la API. Verificar que el servidor esté corriendo en localhost:8000.
            </div>
          )}
        </form>

        {/* Panel de resultado */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Gauge */}
          <div style={{
            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)', padding: 20, textAlign: 'center',
          }}>
            {result ? (
              <>
                <RiskGauge
                  probabilidad={result.probabilidad_deslizamiento}
                  nivel={result.nivel_riesgo as NivelRiesgo}
                />
                <div style={{ marginTop: 12 }}>
                  <RiskBadge nivel={result.nivel_riesgo as NivelRiesgo} size="lg" />
                </div>
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--color-text-muted)' }}>
                  {new Date(result.timestamp).toLocaleString('es-CO')}
                </div>
              </>
            ) : (
              <div style={{ padding: '40px 0', color: 'var(--color-text-muted)', fontSize: 13 }}>
                Ingrese los datos y haga clic en Predecir para ver el resultado.
              </div>
            )}
          </div>

          {/* Contexto histórico */}
          {imp && (
            <div style={{
              background: 'var(--color-surface)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)', padding: 16,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 10 }}>
                CONTEXTO HISTÓRICO CUENCA
              </div>
              {[
                ['Eventos UNGRD 2019-2022', imp.n_eventos],
                ['Costo histórico', `$${imp.costo_m_cop.toFixed(0)} M COP`],
                ['Fallecidos', imp.fallecidos],
                ['Personas afectadas', imp.personas.toLocaleString('es-CO')],
                ['Índice de riesgo', imp.indice_riesgo.toFixed(0)],
                ['Área sub-cuenca', `${imp.SUB_AREA.toFixed(1)} km²`],
              ].map(([k, v]) => (
                <div key={String(k)} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--color-border)', fontSize: 12 }}>
                  <span style={{ color: 'var(--color-text-muted)' }}>{k}</span>
                  <span style={{ fontWeight: 600 }}>{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
