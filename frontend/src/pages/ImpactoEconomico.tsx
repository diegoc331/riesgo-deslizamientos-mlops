import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, CartesianGrid, Legend,
} from 'recharts';
import KpiCard from '../components/ui/KpiCard';
import { useImpacto } from '../api/predict';

export default function ImpactoEconomico() {
  const { data: impacto = [], isLoading } = useImpacto();

  const top20Costo = useMemo(() => (
    [...impacto]
      .sort((a, b) => b.costo_m_cop - a.costo_m_cop)
      .slice(0, 20)
      .map(i => ({
        name: String(i.HYBAS_ID).slice(-4),
        hybas: i.HYBAS_ID,
        costo: parseFloat(i.costo_m_cop.toFixed(0)),
        eventos: i.n_eventos,
        fallecidos: i.fallecidos,
      }))
  ), [impacto]);

  const top10Fallecidos = useMemo(() => (
    [...impacto]
      .filter(i => i.fallecidos > 0)
      .sort((a, b) => b.fallecidos - a.fallecidos)
      .slice(0, 10)
  ), [impacto]);

  const scatter = useMemo(() => (
    impacto
      .filter(i => i.n_eventos > 0)
      .map(i => ({
        eventos: i.n_eventos,
        costo: parseFloat(i.costo_m_cop.toFixed(0)),
        fallecidos: i.fallecidos + 1,
        hybas: i.HYBAS_ID,
      }))
  ), [impacto]);

  if (isLoading) return (
    <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-text-muted)' }}>Cargando datos...</div>
  );

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 24 }}>

      <h1 style={{ fontSize: 20, fontWeight: 700 }}>Impacto Económico Histórico — Antioquia 2019-2022</h1>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard label="Costo total" value="$210.400 M" sub="COP (2019-2022)" color="var(--color-alto)" />
        <KpiCard label="Fallecidos" value="115" sub="UNGRD registrados" color="var(--color-alto)" />
        <KpiCard label="Personas afectadas" value="56.353" sub="evacuadas / damnificadas" />
        <KpiCard label="Cuencas con eventos" value="91" sub="de 549 (16.6%)" />
        <KpiCard label="BCR" value="2.11×" sub="escenario conservador 40%" color="var(--color-bajo)" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* Bar chart costo */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20,
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--color-text-muted)' }}>
            TOP 20 CUENCAS POR COSTO HISTÓRICO (M COP)
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={top20Costo} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={48} />
              <Tooltip
                formatter={(v) => [`$${Number(v).toLocaleString('es-CO')} M COP`, 'Costo']}
                labelFormatter={(l) => `HYBAS ...${l}`}
              />
              <Bar dataKey="costo" fill="#dc2626" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Scatter eventos vs costo */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20,
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--color-text-muted)' }}>
            EVENTOS VS COSTO POR CUENCA
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ left: 0, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="eventos" name="Eventos" tick={{ fontSize: 11 }} label={{ value: 'N° eventos', position: 'insideBottom', offset: -2, fontSize: 11 }} />
              <YAxis dataKey="costo" name="Costo" tick={{ fontSize: 11 }} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ payload }) => {
                  if (!payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div style={{ background: '#fff', border: '1px solid var(--color-border)', padding: '8px 12px', borderRadius: 6, fontSize: 12 }}>
                      <div><b>HYBAS {d.hybas}</b></div>
                      <div>Eventos: {d.eventos}</div>
                      <div>Costo: ${d.costo.toLocaleString('es-CO')} M COP</div>
                      <div>Fallecidos: {d.fallecidos - 1}</div>
                    </div>
                  );
                }}
              />
              <Legend />
              <Scatter data={scatter} fill="#f97316" opacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Tabla top 10 fallecidos */}
      <div style={{
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: 20,
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--color-text-muted)' }}>
          TOP 10 CUENCAS POR FALLECIDOS HISTÓRICOS
        </h2>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--color-border)', background: 'var(--color-bg)' }}>
              {['Rank', 'HYBAS_ID', 'Fallecidos', 'Heridos', 'Personas afectadas', 'Eventos', 'Costo M COP'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 14px', color: 'var(--color-text-muted)', fontSize: 11, fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {top10Fallecidos.map((i, idx) => (
              <tr key={i.HYBAS_ID} style={{ borderBottom: '1px solid var(--color-border)' }}>
                <td style={{ padding: '8px 14px', fontWeight: 700, color: idx < 3 ? 'var(--color-alto)' : 'var(--color-text-muted)' }}>#{idx + 1}</td>
                <td style={{ padding: '8px 14px', fontFamily: 'monospace', fontSize: 12 }}>{i.HYBAS_ID}</td>
                <td style={{ padding: '8px 14px', fontWeight: 700, color: 'var(--color-alto)' }}>{i.fallecidos}</td>
                <td style={{ padding: '8px 14px' }}>{i.heridos > 0 ? i.heridos : '—'}</td>
                <td style={{ padding: '8px 14px' }}>{i.personas > 0 ? i.personas.toLocaleString('es-CO') : '—'}</td>
                <td style={{ padding: '8px 14px' }}>{i.n_eventos}</td>
                <td style={{ padding: '8px 14px' }}>{i.costo_m_cop > 0 ? `$${i.costo_m_cop.toLocaleString('es-CO', { maximumFractionDigits: 0 })} M` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--color-text-muted)' }}>
          Fuente: UNGRD (Unidad Nacional para la Gestión del Riesgo de Desastres) 2019-2022. Costo del sistema de predicción: $200 M COP. Recall del modelo: 0.80.
        </div>
      </div>
    </div>
  );
}
