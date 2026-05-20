import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import RiskBadge from '../components/ui/RiskBadge';
import {
  useImpacto,
  useSemanaPredictions,
  useSemanasDisponibles,
  usePredicionesHistoricas,
} from '../api/predict';
import type { NivelRiesgo } from '../types';

function formatSemana(s: string): string {
  const [ini, fin] = s.split('/');
  const fmt = (d: string) =>
    new Date(d + 'T12:00:00').toLocaleDateString('es-CO', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  return fin ? `${fmt(ini)} — ${fmt(fin)}` : fmt(ini);
}

type FiltroNivel = 'Alto' | 'Medio' | 'Bajo';

interface FilaTabla {
  hybas_id: number;
  prob: number;
  nivel: string;
  n_eventos: number;
  fallecidos: number;
  costo_m_cop: number;
  poblacion_estimada: number;
  score: number;
}

export default function Prioridades() {
  const navigate = useNavigate();
  const { data: impacto = [], isLoading: loadingImpacto } = useImpacto();
  const { data: semanasData, isError: semanasError } = useSemanasDisponibles();
  const [semanaSeleccionada, setSemanaSeleccionada] = useState<string | null>(null);

  const { data: semanaPredActual, isLoading: loadingActual } = useSemanaPredictions();
  const { data: semanaPredHistorica, isLoading: loadingHistorica } = usePredicionesHistoricas(semanaSeleccionada);

  const semanaPred = semanaSeleccionada ? semanaPredHistorica : semanaPredActual;
  const loadingPred = semanaSeleccionada ? loadingHistorica : loadingActual;

  const [filtroNiveles, setFiltroNiveles] = useState<Set<FiltroNivel>>(
    new Set(['Alto', 'Medio', 'Bajo'])
  );
  const [soloConEventos, setSoloConEventos] = useState(false);

  const semana = semanaPred?.semana ?? '—';
  const predictions = semanaPred?.resultados ?? [];

  const maxIndice = useMemo(() => {
    return Math.max(...impacto.map(i => i.indice_riesgo ?? 0), 1);
  }, [impacto]);

  const tabla: FilaTabla[] = useMemo(() => {
    return predictions
      .map(p => {
        const imp = impacto.find(i => i.HYBAS_ID === p.hybas_id);
        const indiceNorm = imp ? imp.indice_riesgo / maxIndice : 0;
        const score = p.probabilidad_deslizamiento * (1 + indiceNorm);
        return {
          hybas_id: p.hybas_id,
          prob: p.probabilidad_deslizamiento,
          nivel: p.nivel_riesgo,
          n_eventos: imp?.n_eventos ?? 0,
          fallecidos: imp?.fallecidos ?? 0,
          costo_m_cop: imp?.costo_m_cop ?? 0,
          poblacion_estimada: imp?.poblacion_estimada ?? 0,
          score,
        };
      })
      .filter(r => filtroNiveles.has(r.nivel as FiltroNivel))
      .filter(r => !soloConEventos || r.n_eventos > 0)
      .sort((a, b) => b.score - a.score);
  }, [predictions, impacto, maxIndice, filtroNiveles, soloConEventos]);

  const toggleNivel = (n: FiltroNivel) => {
    setFiltroNiveles(prev => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  };

  const exportCSV = () => {
    const header = 'Rank,HYBAS_ID,Prob_%,Nivel,Eventos_hist,Fallecidos,Costo_M_COP,Poblacion,Score';
    const rows = tabla.map((r, i) =>
      [
        i + 1,
        r.hybas_id,
        (r.prob * 100).toFixed(1),
        r.nivel,
        r.n_eventos,
        r.fallecidos,
        r.costo_m_cop.toFixed(0),
        r.poblacion_estimada,
        r.score.toFixed(3),
      ].join(',')
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `prioridades_${semana.replace(/\//g, '-')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isLoading = loadingPred || loadingImpacto;

  return (
    <div style={{ padding: 24, maxWidth: 1240, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Encabezado */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>Tabla de Prioridades — Mesa Técnica Semanal</h1>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 4 }}>
            Semana: <b>{semana}</b> · {tabla.length} cuencas mostradas ·{' '}
            ordenadas por score de prioridad (probabilidad ML × impacto histórico)
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {!semanasError && (
            <select
              value={semanaSeleccionada ?? ''}
              onChange={e => setSemanaSeleccionada(e.target.value || null)}
              disabled={!semanasData}
              style={{
                fontSize: 12, padding: '6px 10px',
                border: '1px solid var(--color-border)', borderRadius: 6,
                background: 'var(--color-bg)', color: 'var(--color-text)',
                maxWidth: 280, opacity: !semanasData ? 0.5 : 1,
              }}
            >
              <option value="">{semanasData ? 'Semana actual (pipeline ML)' : 'Cargando...'}</option>
              {semanasData && [...semanasData.semanas].reverse().map(s => (
                <option key={s} value={s}>{formatSemana(s)}</option>
              ))}
            </select>
          )}
          {loadingHistorica && (
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Calculando predicciones...</span>
          )}
          <button
            onClick={exportCSV}
            disabled={tabla.length === 0}
            style={{
              background: 'var(--color-navy)', color: '#fff',
              padding: '9px 20px', fontSize: 13, fontWeight: 600,
              opacity: tabla.length === 0 ? 0.5 : 1,
            }}
          >
            Exportar CSV
          </button>
        </div>
      </div>

      {/* Barra de filtros */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: '10px 16px',
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)' }}>NIVEL:</span>
        {(['Alto', 'Medio', 'Bajo'] as FiltroNivel[]).map(n => (
          <label key={n} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={filtroNiveles.has(n)}
              onChange={() => toggleNivel(n)}
              style={{ accentColor: n === 'Alto' ? '#dc2626' : n === 'Medio' ? '#f97316' : '#16a34a', cursor: 'pointer' }}
            />
            <span style={{
              color: n === 'Alto' ? 'var(--color-alto)' : n === 'Medio' ? 'var(--color-medio)' : 'var(--color-bajo)',
              fontWeight: 600,
            }}>{n}</span>
          </label>
        ))}

        <div style={{ width: 1, height: 20, background: 'var(--color-border)', margin: '0 4px' }} />

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 13, userSelect: 'none' }}>
          <input
            type="checkbox"
            checked={soloConEventos}
            onChange={e => setSoloConEventos(e.target.checked)}
            style={{ cursor: 'pointer' }}
          />
          Solo cuencas con eventos históricos UNGRD
        </label>

        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--color-text-muted)' }}>
          {tabla.length} resultado{tabla.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tabla */}
      {isLoading ? (
        <div style={{ padding: 60, textAlign: 'center', color: 'var(--color-text-muted)' }}>
          Cargando datos...
        </div>
      ) : predictions.length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center', color: 'var(--color-text-muted)',
          background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)',
        }}>
          <div style={{ fontSize: 15, marginBottom: 8 }}>No hay predicciones disponibles para esta semana.</div>
          <code style={{ fontSize: 12 }}>uv run python pipelines/prediction_flow.py</code>
        </div>
      ) : (
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', overflow: 'auto',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: 'var(--color-bg)', borderBottom: '2px solid var(--color-border)' }}>
                {['Rank', 'HYBAS_ID', 'Prob %', 'Nivel', 'Eventos hist.', 'Fallecidos', 'Costo M COP', 'Población', 'Score ▼'].map(h => (
                  <th key={h} style={{
                    textAlign: 'left', padding: '10px 14px',
                    color: 'var(--color-text-muted)', fontSize: 11, fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tabla.map((r, i) => (
                <tr
                  key={r.hybas_id}
                  onClick={() => navigate(`/prediccion/${r.hybas_id}`)}
                  title="Ver detalle de la cuenca"
                  style={{
                    borderBottom: '1px solid var(--color-border)',
                    cursor: 'pointer',
                    background: i < 10 && r.nivel === 'Alto' ? 'rgba(220,38,38,0.03)' : '',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-bg)')}
                  onMouseLeave={e => (e.currentTarget.style.background = i < 10 && r.nivel === 'Alto' ? 'rgba(220,38,38,0.03)' : '')}
                >
                  <td style={{
                    padding: '9px 14px', fontWeight: 700, width: 50,
                    color: i < 10 ? 'var(--color-alto)' : 'var(--color-text-muted)',
                  }}>
                    #{i + 1}
                  </td>
                  <td style={{ padding: '9px 14px', fontFamily: 'monospace', fontWeight: 600, fontSize: 12 }}>
                    {r.hybas_id}
                  </td>
                  <td style={{ padding: '9px 14px', fontWeight: 700 }}>
                    {(r.prob * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: '9px 14px' }}>
                    <RiskBadge nivel={r.nivel as NivelRiesgo} size="sm" />
                  </td>
                  <td style={{
                    padding: '9px 14px',
                    color: r.n_eventos > 0 ? 'var(--color-text)' : 'var(--color-text-muted)',
                    fontWeight: r.n_eventos > 5 ? 700 : 400,
                  }}>
                    {r.n_eventos > 0 ? r.n_eventos : '—'}
                  </td>
                  <td style={{
                    padding: '9px 14px',
                    color: r.fallecidos > 0 ? 'var(--color-alto)' : 'var(--color-text-muted)',
                    fontWeight: r.fallecidos > 0 ? 700 : 400,
                  }}>
                    {r.fallecidos > 0 ? r.fallecidos : '—'}
                  </td>
                  <td style={{ padding: '9px 14px' }}>
                    {r.costo_m_cop > 0
                      ? `$${r.costo_m_cop.toLocaleString('es-CO', { maximumFractionDigits: 0 })} M`
                      : '—'}
                  </td>
                  <td style={{ padding: '9px 14px' }}>
                    {r.poblacion_estimada.toLocaleString('es-CO')}
                  </td>
                  <td style={{ padding: '9px 14px', fontWeight: 700, color: 'var(--color-navy)', fontSize: 13 }}>
                    {r.score.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: 12, color: 'var(--color-text-muted)', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <span><b>Score</b> = probabilidad ML × (1 + índice_riesgo_normalizado)</span>
        <span><b>Índice riesgo</b> = compuesto UNGRD: eventos, fallecidos, personas, costo</span>
        <span>Click en cualquier fila para ver el detalle de la cuenca.</span>
      </div>
    </div>
  );
}
