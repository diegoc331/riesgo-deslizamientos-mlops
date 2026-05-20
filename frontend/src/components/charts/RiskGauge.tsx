import { PieChart, Pie, Cell } from 'recharts';
import type { NivelRiesgo } from '../../types';

interface Props {
  probabilidad: number;
  nivel: NivelRiesgo;
}

const NIVEL_COLOR: Record<NivelRiesgo, string> = {
  Alto: '#dc2626',
  Medio: '#f97316',
  Bajo: '#16a34a',
  'Sin datos': '#9ca3af',
};

export default function RiskGauge({ probabilidad, nivel }: Props) {
  const pct = Math.round(probabilidad * 100);
  const color = NIVEL_COLOR[nivel];

  const data = [
    { value: pct },
    { value: 100 - pct },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div style={{ position: 'relative', width: 160, height: 160 }}>
        <PieChart width={160} height={160}>
          <Pie
            data={data}
            cx={75}
            cy={75}
            innerRadius={52}
            outerRadius={72}
            startAngle={90}
            endAngle={-270}
            dataKey="value"
            strokeWidth={0}
          >
            <Cell fill={color} />
            <Cell fill="#e5e7eb" />
          </Pie>
        </PieChart>
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <span style={{ fontSize: 26, fontWeight: 700, color }}>{pct}%</span>
          <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>prob.</span>
        </div>
      </div>
    </div>
  );
}
