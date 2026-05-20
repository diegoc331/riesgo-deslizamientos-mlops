import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import RiskGauge from '../components/charts/RiskGauge';
import RiskBadge from '../components/ui/RiskBadge';
import { usePredict, useImpacto, useSemanaPredictions, calcSeasonality } from '../api/predict';
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
  const { data: semanaPred } = useSemanaPredictions();
  const { mutate: predict, data: simResult, isPending, isError, reset } = usePredict();

  const [hybas, setHybas] = useState<number>(hybasId ? parseInt(hybasId) : 6100996770);
  const [form, setForm] = useState<Omit<PredictRequest, 'hybas_id'>>(DEFAULT);
  const [mostrarSimulador, setMostrarSimulador] = useState(false);

  const imp = impacto.find(i => i.HYBAS_ID === hybas);
  const predML = semanaPred?.resultados?.find(p => p.hybas_id === hybas);

  const handleHybasChange = (val: string) => {
    setHybas(parseInt(val) || 0);
    reset();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    predict({ hybas_id: hybas, ...form });
  };

  const handleChange = (key: FieldKey, val: string) => {
    setForm(f => ({ ...f, [key]: parseFloat(val) || 0 }));
    reset();
  };

  const resultadoMostrar = simResult ?? predML;
  const esSimulacion = !!simResult;

  return (
    <div style={{ padding: 24, maxWidth: 980, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Encabezado con navegación */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button
          onClick={() => navigate('/')}
          style={{ background: 'var(--color-border)', color: 'var(--color-text)', padding: '6px 12px', fontSize: 12 }}
        >
          ← Mapa
        </button>
        <button
          onClick={() => navigate('/prioridades')}
          style={{ background: 'var(--color-border)', color: 'var(--color-text)', padding: '6px 12px', fontSize: 12 }}
        >
          ← Prioridades
        </button>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginLeft: 6 }}>Detalle de Cuenca</h1>
      </div>

      {/* Selector de cuenca */}
      <div style={{
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: '14px 20px',
        display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
          HYBAS_ID (cuenca):
        </label>
        <input
          type="number"
          value={hybas}
          onChange={e => handleHybasChange(e.target.value)}
          style={{ width: 160, fontSize: 14, fontWeight: 600 }}
        />
        {predML && (
          <span style={{ fontSize: 12, color: 'var(--color-bajo)' }}>
            ● Cuenca encontrada en predicciones de la semana {semanaPred?.semana}
          </span>
        )}
        {!predML && semanaPred && (
          <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
            Cuenca no está en las predicciones de esta semana.
          </span>
        )}
      </div>

      {/* Vista principal: resultado ML o simulación */}
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20 }}>

        {/* Gauge */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 24, textAlign: 'center',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        }}>
          {resultadoMostrar ? (
            <>
              {esSimulacion && (
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8 }}>
                  SIMULACIÓN — datos ingresados manualmente
                </div>
              )}
              {!esSimulacion && (
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-bajo)', marginBottom: 8 }}>
                  PREDICCIÓN ML — semana actual
                </div>
              )}
              <RiskGauge
                probabilidad={resultadoMostrar.probabilidad_deslizamiento}
                nivel={resultadoMostrar.nivel_riesgo as NivelRiesgo}
              />
              <div style={{ marginTop: 14 }}>
                <RiskBadge nivel={resultadoMostrar.nivel_riesgo as NivelRiesgo} size="lg" />
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--color-text-muted)' }}>
                {new Date(resultadoMostrar.timestamp).toLocaleString('es-CO')}
              </div>
            </>
          ) : (
            <div style={{ padding: '32px 0', color: 'var(--color-text-muted)', fontSize: 13 }}>
              {semanaPred
                ? 'Esta cuenca no tiene predicción para la semana actual.'
                : 'Seleccione una cuenca con HYBAS_ID.'}
            </div>
          )}
        </div>

        {/* Contexto de la cuenca */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Info de la predicción ML */}
          {predML && !esSimulacion && (
            <div style={{
              background: 'var(--color-surface)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)', padding: 16,
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 10 }}>
                PREDICCIÓN PIPELINE SEMANAL
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: 13 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-muted)' }}>Semana</span>
                  <span style={{ fontWeight: 600 }}>{semanaPred?.semana ?? '—'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-muted)' }}>Probabilidad</span>
                  <span style={{ fontWeight: 700 }}>{(predML.probabilidad_deslizamiento * 100).toFixed(1)}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-muted)' }}>Nivel</span>
                  <RiskBadge nivel={predML.nivel_riesgo as NivelRiesgo} size="sm" />
                </div>
              </div>
            </div>
          )}

          {/* Contexto histórico UNGRD */}
          {imp ? (
            <div style={{
              background: 'var(--color-surface)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)', padding: 16,
            }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 10 }}>
                HISTORIAL UNGRD 2019-2022
              </div>
              {[
                ['Eventos registrados', imp.n_eventos > 0 ? imp.n_eventos : '— (sin eventos)'],
                ['Fallecidos', imp.fallecidos > 0 ? imp.fallecidos : '—'],
                ['Personas afectadas', imp.personas > 0 ? imp.personas.toLocaleString('es-CO') : '—'],
                ['Costo histórico', imp.costo_m_cop > 0 ? `$${imp.costo_m_cop.toLocaleString('es-CO', { maximumFractionDigits: 0 })} M COP` : '—'],
                ['Viviendas destruidas', imp.viviendas_destruidas > 0 ? imp.viviendas_destruidas : '—'],
                ['Población estimada', imp.poblacion_estimada.toLocaleString('es-CO')],
                ['Área sub-cuenca', `${imp.SUB_AREA.toFixed(1)} km²`],
                ['Índice de riesgo', imp.indice_riesgo.toFixed(1)],
              ].map(([k, v]) => (
                <div key={String(k)} style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '5px 0', borderBottom: '1px solid var(--color-border)', fontSize: 12,
                }}>
                  <span style={{ color: 'var(--color-text-muted)' }}>{k}</span>
                  <span style={{ fontWeight: 600 }}>{v}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{
              background: 'var(--color-surface)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)', padding: 16, fontSize: 13, color: 'var(--color-text-muted)', textAlign: 'center',
            }}>
              Sin eventos UNGRD registrados para esta cuenca (2019-2022).
            </div>
          )}
        </div>
      </div>

      {/* Simulador — sección colapsable para analistas */}
      <div style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
        <button
          onClick={() => setMostrarSimulador(v => !v)}
          style={{
            width: '100%', textAlign: 'left',
            background: 'var(--color-surface)', padding: '12px 20px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            fontSize: 13, fontWeight: 600, color: 'var(--color-text-muted)',
            borderRadius: 0,
          }}
        >
          <span>Simular escenario (análisis avanzado — 14 variables)</span>
          <span>{mostrarSimulador ? '▲' : '▼'}</span>
        </button>

        {mostrarSimulador && (
          <form
            onSubmit={handleSubmit}
            style={{
              background: 'var(--color-bg)', borderTop: '1px solid var(--color-border)',
              padding: 20, display: 'flex', flexDirection: 'column', gap: 12,
            }}
          >
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
              Ingrese valores hipotéticos de precipitación y características de la cuenca para simular una predicción puntual.
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              {FIELDS.map(({ key, label, unit, min, max, step }) => (
                <div key={key}>
                  <label style={{ fontSize: 11, fontWeight: 500, color: 'var(--color-text-muted)', display: 'block', marginBottom: 3 }}>
                    {label} {unit && <span style={{ opacity: 0.6 }}>({unit})</span>}
                  </label>
                  <input
                    type="number"
                    value={form[key] as number}
                    min={min} max={max} step={step}
                    onChange={e => handleChange(key, e.target.value)}
                  />
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              <button
                type="submit" disabled={isPending}
                style={{ background: 'var(--color-navy)', color: '#fff', flex: 1, padding: '9px 0', fontSize: 13 }}
              >
                {isPending ? 'Calculando...' : 'Simular predicción'}
              </button>
              <button
                type="button"
                onClick={() => { setForm(DEFAULT); reset(); }}
                style={{ background: 'var(--color-border)', color: 'var(--color-text)' }}
              >
                Limpiar
              </button>
            </div>

            {isError && (
              <div style={{ background: '#fee2e2', color: '#991b1b', padding: '8px 12px', borderRadius: 6, fontSize: 13 }}>
                Error al conectar con la API. Verificar que el servidor esté corriendo en localhost:8000.
              </div>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
