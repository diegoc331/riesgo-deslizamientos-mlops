import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import RiskMap from '../components/map/RiskMap';
import KpiCard from '../components/ui/KpiCard';
import RiskBadge from '../components/ui/RiskBadge';
import {
  useImpacto,
  useSemanaPredictions,
  useSemanasDisponibles,
  usePredicionesHistoricas,
} from '../api/predict';

type FiltroNivel = 'Alto' | 'Medio' | 'Bajo';

function formatSemana(s: string): string {
  const [ini, fin] = s.split('/');
  const fmt = (d: string) =>
    new Date(d + 'T12:00:00').toLocaleDateString('es-CO', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  return fin ? `${fmt(ini)} — ${fmt(fin)}` : fmt(ini);
}

export default function MapaRiesgo() {
  const navigate = useNavigate();
  const { data: impacto = [], isLoading: loadingImpacto } = useImpacto();
  const { data: semanasData, isError: semanasError, isLoading: semanasLoading } = useSemanasDisponibles();
  const [semanaSeleccionada, setSemanaSeleccionada] = useState<string | null>(null);

  const { data: semanaPredActual, isLoading: loadingActual } = useSemanaPredictions();
  const { data: semanaPredHistorica, isLoading: loadingHistorica } = usePredicionesHistoricas(semanaSeleccionada);

  const semanaPred = semanaSeleccionada ? semanaPredHistorica : semanaPredActual;
  const loadingPred = semanaSeleccionada ? loadingHistorica : loadingActual;

  const [filtroNiveles, setFiltroNiveles] = useState<Set<FiltroNivel>>(
    new Set(['Alto', 'Medio', 'Bajo'])
  );
  const [soloConEventos, setSoloConEventos] = useState(false);

  const predictions = semanaPred?.resultados ?? [];
  const semana = semanaPred?.semana ?? '';
  const total = impacto.length || 549;

  const counts = useMemo(() => {
    if (predictions.length === 0) {
      return {
        alto: impacto.filter(i => i.indice_riesgo > 1000).length,
        medio: impacto.filter(i => i.indice_riesgo > 200 && i.indice_riesgo <= 1000).length,
        bajo: impacto.filter(i => i.indice_riesgo <= 200).length,
      };
    }
    return {
      alto: predictions.filter(p => p.nivel_riesgo === 'Alto').length,
      medio: predictions.filter(p => p.nivel_riesgo === 'Medio').length,
      bajo: predictions.filter(p => p.nivel_riesgo === 'Bajo').length,
    };
  }, [predictions, impacto]);

  const maxIndice = useMemo(
    () => Math.max(...impacto.map(i => i.indice_riesgo ?? 0), 1),
    [impacto]
  );

  const toggleNivel = (n: FiltroNivel) => {
    setFiltroNiveles(prev => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  };

  // Top 10 por score combinado aplicando filtros
  const altoCuencas = useMemo(() => {
    const candidatos = predictions.length > 0
      ? predictions
          .filter(p => filtroNiveles.has(p.nivel_riesgo as FiltroNivel))
          .map(p => {
            const imp = impacto.find(i => i.HYBAS_ID === p.hybas_id);
            const indiceNorm = imp ? imp.indice_riesgo / maxIndice : 0;
            return {
              hybas_id: p.hybas_id,
              probabilidad_deslizamiento: p.probabilidad_deslizamiento,
              nivel_riesgo: p.nivel_riesgo,
              timestamp: p.timestamp,
              n_eventos: imp?.n_eventos ?? 0,
              costo_m_cop: imp?.costo_m_cop ?? 0,
              score: p.probabilidad_deslizamiento * (1 + indiceNorm),
            };
          })
          .filter(c => !soloConEventos || c.n_eventos > 0)
          .sort((a, b) => b.score - a.score)
          .slice(0, 10)
      : impacto
          .filter(i => filtroNiveles.has('Alto') && i.indice_riesgo > 1000)
          .filter(i => !soloConEventos || i.n_eventos > 0)
          .sort((a, b) => b.indice_riesgo - a.indice_riesgo)
          .slice(0, 10)
          .map(i => ({
            hybas_id: i.HYBAS_ID,
            probabilidad_deslizamiento: Math.min(i.indice_riesgo / 5000, 0.99),
            nivel_riesgo: 'Alto' as const,
            timestamp: '',
            n_eventos: i.n_eventos,
            costo_m_cop: i.costo_m_cop,
            score: i.indice_riesgo / 5000,
          }));
    return candidatos;
  }, [predictions, impacto, maxIndice, filtroNiveles, soloConEventos]);

  const handleSelectCuenca = useCallback((hybas: number) => {
    navigate(`/prediccion/${hybas}`);
  }, [navigate]);

  const isLoading = loadingImpacto || loadingPred;
  const modoLabel = predictions.length > 0
    ? `Predicciones ML — ${semana}`
    : isLoading
    ? 'Cargando...'
    : 'Datos históricos UNGRD 2019-2022 (sin predicciones ML disponibles)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, height: 'calc(100vh - 52px)' }}>

      {/* KPI bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px',
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border)',
        flexShrink: 0, flexWrap: 'wrap',
      }}>
        <KpiCard
          label="Alto riesgo"
          value={`${counts.alto} (${Math.round(counts.alto / total * 100)}%)`}
          color="var(--color-alto)"
        />
        <KpiCard label="Medio riesgo" value={counts.medio} color="var(--color-medio)" />
        <KpiCard label="Bajo riesgo" value={counts.bajo} color="var(--color-bajo)" />
        <KpiCard label="Total cuencas" value={total} />

        {/* Filtros rápidos */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 14,
          marginLeft: 16, paddingLeft: 16, borderLeft: '1px solid var(--color-border)',
          flexWrap: 'wrap',
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)' }}>FILTRAR:</span>
          {(['Alto', 'Medio', 'Bajo'] as FiltroNivel[]).map(n => (
            <label key={n} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 12, userSelect: 'none' }}>
              <input
                type="checkbox"
                checked={filtroNiveles.has(n)}
                onChange={() => toggleNivel(n)}
                style={{ accentColor: n === 'Alto' ? '#dc2626' : n === 'Medio' ? '#f97316' : '#16a34a', cursor: 'pointer' }}
              />
              <span style={{ color: n === 'Alto' ? 'var(--color-alto)' : n === 'Medio' ? 'var(--color-medio)' : 'var(--color-bajo)', fontWeight: 600 }}>{n}</span>
            </label>
          ))}
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 12, userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={soloConEventos}
              onChange={e => setSoloConEventos(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            Solo con eventos
          </label>
        </div>

        <div style={{ marginLeft: 'auto' }}>
          <span style={{ fontSize: 12, color: predictions.length > 0 ? 'var(--color-bajo)' : 'var(--color-text-muted)' }}>
            {predictions.length > 0 ? '● ' : ''}
            {loadingHistorica ? 'Calculando predicciones...' : modoLabel}
          </span>
        </div>
      </div>

      {/* Cuerpo: sidebar + mapa + panel derecho */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar izquierdo */}
        <aside style={{
          width: 230,
          background: 'var(--color-surface)',
          borderRight: '1px solid var(--color-border)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden', flexShrink: 0,
        }}>
          <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--color-border)', fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)' }}>
            TOP CUENCAS POR PRIORIDAD
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
            {altoCuencas.map((c) => (
              <button
                key={c.hybas_id}
                onClick={() => navigate(`/prediccion/${c.hybas_id}`)}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '8px 14px', background: 'transparent',
                  borderRadius: 0, borderBottom: '1px solid var(--color-border)',
                  fontSize: 12,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                  <span style={{ fontWeight: 600, color: c.nivel_riesgo === 'Alto' ? 'var(--color-alto)' : c.nivel_riesgo === 'Medio' ? 'var(--color-medio)' : 'var(--color-bajo)' }}>
                    {c.hybas_id}
                  </span>
                  <RiskBadge nivel={c.nivel_riesgo as 'Alto' | 'Medio' | 'Bajo'} size="sm" />
                </div>
                <div style={{ color: 'var(--color-text-muted)', display: 'flex', gap: 8 }}>
                  <span>Prob: {(c.probabilidad_deslizamiento * 100).toFixed(0)}%</span>
                  {c.n_eventos > 0 && <span>· {c.n_eventos} ev.</span>}
                  {c.costo_m_cop > 0 && <span>· ${c.costo_m_cop.toFixed(0)} M</span>}
                </div>
              </button>
            ))}
            {altoCuencas.length === 0 && (
              <div style={{ padding: '20px 14px', color: 'var(--color-text-muted)', fontSize: 12 }}>
                Sin cuencas con los filtros aplicados.
              </div>
            )}
          </div>

          {/* Leyenda */}
          <div style={{ padding: '10px 14px', borderTop: '1px solid var(--color-border)', fontSize: 12 }}>
            <div style={{ fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6 }}>LEYENDA</div>
            {(['Alto', 'Medio', 'Bajo'] as const).map(n => (
              <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{
                  width: 12, height: 12, borderRadius: 2, flexShrink: 0,
                  background: n === 'Alto' ? 'var(--color-alto)' : n === 'Medio' ? 'var(--color-medio)' : 'var(--color-bajo)',
                }} />
                <RiskBadge nivel={n} size="sm" />
              </div>
            ))}
          </div>
        </aside>

        {/* Mapa */}
        <div style={{ flex: 1, position: 'relative' }}>
          <RiskMap
            impacto={impacto}
            predictions={predictions}
            onSelectCuenca={handleSelectCuenca}
          />
        </div>

        {/* Panel resumen derecho */}
        <aside style={{
          width: 210,
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-border)',
          padding: '16px 14px',
          display: 'flex', flexDirection: 'column', gap: 16,
          flexShrink: 0, overflow: 'auto',
        }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8 }}>DISTRIBUCIÓN</div>
            {[
              { label: 'Alto', count: counts.alto, color: 'var(--color-alto)' },
              { label: 'Medio', count: counts.medio, color: 'var(--color-medio)' },
              { label: 'Bajo', count: counts.bajo, color: 'var(--color-bajo)' },
            ].map(({ label, count, color }) => (
              <div key={label} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: 12 }}>
                  <span style={{ color }}>{label}</span>
                  <span style={{ fontWeight: 600 }}>{count}</span>
                </div>
                <div style={{ height: 6, background: 'var(--color-border)', borderRadius: 3 }}>
                  <div style={{
                    height: '100%', borderRadius: 3, background: color,
                    width: `${(count / total) * 100}%`,
                    transition: 'width 0.5s',
                  }} />
                </div>
              </div>
            ))}
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8 }}>IMPACTO HISTÓRICO</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>2019-2022</div>
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
              <div>Costo total: <b>$210 Mil MM</b></div>
              <div>Fallecidos: <b>115</b></div>
              <div>Afectados: <b>56.353</b></div>
              <div>BCR: <b>2.11×</b></div>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 6 }}>SEMANA DE ANÁLISIS</div>
            {semanasError ? (
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', padding: '5px 0' }}>
                Semanas históricas requieren el backend activo.
              </div>
            ) : (
              <select
                value={semanaSeleccionada ?? ''}
                onChange={e => setSemanaSeleccionada(e.target.value || null)}
                disabled={semanasLoading}
                style={{
                  width: '100%', fontSize: 12, padding: '5px 6px',
                  border: '1px solid var(--color-border)', borderRadius: 6,
                  background: 'var(--color-bg)', color: 'var(--color-text)',
                  opacity: semanasLoading ? 0.5 : 1,
                }}
              >
                <option value="">{semanasLoading ? 'Cargando...' : 'Semana actual (ML)'}</option>
                {semanasData && [...semanasData.semanas].reverse().map(s => (
                  <option key={s} value={s}>{formatSemana(s)}</option>
                ))}
              </select>
            )}
            {loadingHistorica && (
              <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginTop: 4 }}>Calculando predicciones...</div>
            )}
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button
              onClick={() => navigate('/prioridades')}
              style={{ background: 'var(--color-navy)', color: '#fff', width: '100%', padding: '8px 0', fontSize: 13, fontWeight: 600 }}
            >
              Ver tabla de prioridades
            </button>
            <button
              onClick={() => navigate('/prediccion')}
              style={{ background: 'var(--color-border)', color: 'var(--color-text)', width: '100%', padding: '7px 0', fontSize: 12 }}
            >
              Consultar cuenca
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
