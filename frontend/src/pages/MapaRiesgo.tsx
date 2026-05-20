import { useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import RiskMap from '../components/map/RiskMap';
import KpiCard from '../components/ui/KpiCard';
import RiskBadge from '../components/ui/RiskBadge';
import { useImpacto, useSemanaPredictions } from '../api/predict';

export default function MapaRiesgo() {
  const navigate = useNavigate();
  const { data: impacto = [], isLoading: loadingImpacto } = useImpacto();
  const { data: semanaPred, isLoading: loadingPred } = useSemanaPredictions();

  const predictions = semanaPred?.resultados ?? [];
  const semana = semanaPred?.semana ?? '';

  const counts = useMemo(() => {
    if (predictions.length === 0) {
      const alto = impacto.filter(i => i.indice_riesgo > 1000).length;
      const medio = impacto.filter(i => i.indice_riesgo > 200 && i.indice_riesgo <= 1000).length;
      const bajo = impacto.filter(i => i.indice_riesgo <= 200).length;
      return { alto, medio, bajo };
    }
    const alto = predictions.filter(p => p.nivel_riesgo === 'Alto').length;
    const medio = predictions.filter(p => p.nivel_riesgo === 'Medio').length;
    const bajo = predictions.filter(p => p.nivel_riesgo === 'Bajo').length;
    return { alto, medio, bajo };
  }, [predictions, impacto]);

  const altoCuencas = useMemo(() => {
    if (predictions.length > 0) {
      return predictions
        .filter(p => p.nivel_riesgo === 'Alto')
        .sort((a, b) => b.probabilidad_deslizamiento - a.probabilidad_deslizamiento)
        .slice(0, 10);
    }
    return impacto
      .filter(i => i.indice_riesgo > 1000)
      .sort((a, b) => b.indice_riesgo - a.indice_riesgo)
      .slice(0, 10)
      .map(i => ({
        hybas_id: i.HYBAS_ID,
        probabilidad_deslizamiento: Math.min(i.indice_riesgo / 5000, 0.99),
        nivel_riesgo: 'Alto' as const,
        timestamp: '',
      }));
  }, [predictions, impacto]);

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
        padding: '12px 20px',
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border)',
        flexShrink: 0,
      }}>
        <KpiCard label="Alto riesgo" value={counts.alto} color="var(--color-alto)" />
        <KpiCard label="Medio riesgo" value={counts.medio} color="var(--color-medio)" />
        <KpiCard label="Bajo riesgo" value={counts.bajo} color="var(--color-bajo)" />
        <KpiCard label="Total cuencas" value={impacto.length || 549} />

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: predictions.length > 0 ? 'var(--color-bajo)' : 'var(--color-text-muted)' }}>
            {predictions.length > 0 ? '● ' : ''}{modoLabel}
          </span>
        </div>
      </div>

      {/* Cuerpo: sidebar + mapa */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar izquierdo */}
        <aside style={{
          width: 220,
          background: 'var(--color-surface)',
          borderRight: '1px solid var(--color-border)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden', flexShrink: 0,
        }}>
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--color-border)', fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)' }}>
            CUENCAS ALTO RIESGO
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {altoCuencas.map((c) => {
              const imp = impacto.find(i => i.HYBAS_ID === c.hybas_id);
              return (
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
                  <div style={{ fontWeight: 600, color: 'var(--color-alto)', marginBottom: 2 }}>
                    {c.hybas_id}
                  </div>
                  <div style={{ color: 'var(--color-text-muted)' }}>
                    Prob: {(c.probabilidad_deslizamiento * 100).toFixed(0)}%
                    {imp ? ` · $${imp.costo_m_cop.toFixed(0)} M` : ''}
                  </div>
                </button>
              );
            })}
            {altoCuencas.length === 0 && (
              <div style={{ padding: '20px 14px', color: 'var(--color-text-muted)', fontSize: 12 }}>
                Sin cuencas de alto riesgo identificadas.
              </div>
            )}
          </div>

          {/* Leyenda */}
          <div style={{ padding: '12px 14px', borderTop: '1px solid var(--color-border)', fontSize: 12 }}>
            <div style={{ fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8 }}>LEYENDA</div>
            {(['Alto', 'Medio', 'Bajo'] as const).map(n => (
              <div key={n} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
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
          width: 200,
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
                    width: `${(count / (impacto.length || 549)) * 100}%`,
                    transition: 'width 0.5s',
                  }} />
                </div>
              </div>
            ))}
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8 }}>IMPACTO HISTÓRICO</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>2019-2022</div>
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
              <div>Costo total: <b>$210 Mil MM</b></div>
              <div>Fallecidos: <b>115</b></div>
              <div>Afectados: <b>56,353</b></div>
              <div>BCR: <b>2.11×</b></div>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 16 }}>
            <button
              onClick={() => navigate('/prediccion')}
              style={{ background: 'var(--color-navy)', color: '#fff', width: '100%', padding: '8px 0' }}
            >
              Nueva predicción
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
