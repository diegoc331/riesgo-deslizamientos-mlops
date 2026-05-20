import type { NivelRiesgo } from '../../types';

const COLORS: Record<NivelRiesgo, { bg: string; text: string }> = {
  Alto:       { bg: '#fee2e2', text: '#991b1b' },
  Medio:      { bg: '#ffedd5', text: '#9a3412' },
  Bajo:       { bg: '#dcfce7', text: '#166534' },
  'Sin datos':{ bg: '#f3f4f6', text: '#6b7280' },
};

interface Props {
  nivel: NivelRiesgo;
  size?: 'sm' | 'md' | 'lg';
}

export default function RiskBadge({ nivel, size = 'md' }: Props) {
  const { bg, text } = COLORS[nivel];
  const pad = size === 'sm' ? '2px 8px' : size === 'lg' ? '8px 20px' : '4px 12px';
  const fs = size === 'sm' ? 11 : size === 'lg' ? 16 : 13;

  return (
    <span style={{
      background: bg, color: text,
      borderRadius: 20, padding: pad,
      fontSize: fs, fontWeight: 600,
      display: 'inline-block', whiteSpace: 'nowrap',
    }}>
      {nivel === 'Alto' ? '🔴' : nivel === 'Medio' ? '🟠' : nivel === 'Bajo' ? '🟢' : '⚪'} {nivel}
    </span>
  );
}
