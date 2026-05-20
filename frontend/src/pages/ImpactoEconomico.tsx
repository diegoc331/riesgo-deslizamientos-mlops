import { useState, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, CartesianGrid, Legend,
} from 'recharts';
import KpiCard from '../components/ui/KpiCard';
import { useImpacto } from '../api/predict';

const COSTO_SISTEMA = 200;

export default function ImpactoEconomico() {
  const { data: impacto = [], isLoading } = useImpacto();
  const [factor, setFactor] = useState(40);

  const bcr = useMemo(() => {
    const beneficio = 210_400 * (factor / 100) * 0.8;
    return (beneficio / COSTO_SISTEMA).toFixed(2);
  }, [factor]);

  const beneficio = useMemo(() => {
    return (210_400 * (factor / 100) * 0.8).toFixed(0);
  }, [factor]);

  const top20 = useMemo(() => (
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
        <KpiCard label="Costo total" value="$210,400 M" sub="COP (2019-2022)" color="var(--color-alto)" />
        <KpiCard label="Fallecidos" value="115" sub="UNGRD registrados" />
        <KpiCard label="Personas afectadas" value="56,353" sub="evacuadas / damnificadas" />
        <KpiCard label={`BCR (factor ${factor}%)`} value={`${bcr}×`} sub="≥1 = proyecto rentable" color="var(--color-bajo)" />
        <KpiCard label="Cuencas con eventos" value="91" sub="de 549 (16.6%)" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* Bar chart */}
        <div style={{
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)', padding: 20,
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--color-text-muted)' }}>
            TOP 20 CUENCAS POR COSTO HISTÓRICO (M COP)
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={top20} layout="vertical" margin={{ left: 10, right: 20 }}>
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

        {/* Scatter */}
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

      {/* BCR slider */}
      <div style={{
        background: 'var(--color-surface)', border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)', padding: 20,
      }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--color-text-muted)' }}>
          ANÁLISIS BENEFICIO-COSTO — SENSIBILIDAD AL FACTOR DE REDUCCIÓN DE DAÑOS
        </h2>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 20 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 8 }}>
              Factor de reducción de daños: <b>{factor}%</b>
            </label>
            <input
              type="range" min={10} max={90} step={5} value={factor}
              onChange={e => setFactor(parseInt(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--color-navy)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--color-text-muted)' }}>
              <span>10% (conservador)</span><span>90% (optimista)</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <KpiCard label="BCR" value={`${bcr}×`} color={parseFloat(bcr) >= 1 ? 'var(--color-bajo)' : 'var(--color-alto)'} />
            <KpiCard label="Beneficio estimado" value={`$${parseInt(beneficio).toLocaleString('es-CO')} M`} sub="COP" />
            <KpiCard label="Costo sistema (4 años)" value="$200 M" sub="COP" />
          </div>
        </div>

        <div style={{ fontSize: 12, color: 'var(--color-text-muted)', borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
          Punto de equilibrio: reducción ≥ {factor < 20 ? '40%' : 'este nivel'} de daños. Recall del modelo: 0.80 (detecta 80% de eventos). BCR base calculado con factor 40%.
        </div>
      </div>
    </div>
  );
}
