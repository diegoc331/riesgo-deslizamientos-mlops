import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { ImpactoData, PredictResponse } from '../../types';

interface Props {
  impacto: ImpactoData[];
  predictions: PredictResponse[];
  onSelectCuenca: (hybas: number) => void;
}

const RISK_COLORS: Record<string, string> = {
  Alto: '#dc2626',
  Medio: '#f97316',
  Bajo: '#16a34a',
};

function getRiskColor(
  hybas: number,
  predictions: PredictResponse[],
  impacto: ImpactoData[],
  props?: Record<string, unknown>,
): string {
  // 1. Predicción ML en tiempo real
  const pred = predictions.find(p => p.hybas_id === hybas);
  if (pred) return RISK_COLORS[pred.nivel_riesgo] ?? '#9ca3af';

  // 2. Índice histórico UNGRD
  const imp = impacto.find(i => i.HYBAS_ID === hybas);
  if (imp) {
    if (imp.indice_riesgo > 1000) return '#dc2626';
    if (imp.indice_riesgo > 200) return '#f97316';
    return '#16a34a';
  }

  // 3. Fallback: atributos hidrológicos del GeoJSON (tamaño de cuenca)
  const upArea = (props?.UP_AREA as number) ?? 0;
  const order  = (props?.ORDER  as number) ?? 0;
  if (upArea > 8000 || order >= 5) return '#f97316';
  if (upArea > 1000 || order >= 3) return '#86efac'; // verde claro
  return '#16a34a';
}

export default function RiskMap({ impacto, predictions, onSelectCuenca }: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<L.GeoJSON | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current, {
      center: [6.9, -75.4],
      zoom: 8,
      zoomControl: true,
    });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(mapRef.current);
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    fetch('/cuencas_antioquia.geojson')
      .then(r => r.json())
      .then(geojson => {
        layerRef.current = L.geoJSON(geojson, {
          style: (feature) => {
            const hybas = feature?.properties?.HYBAS_ID as number;
            const color = getRiskColor(hybas, predictions, impacto, feature?.properties);
            return {
              fillColor: color,
              fillOpacity: 0.65,
              color: '#fff',
              weight: 0.8,
              opacity: 0.9,
            };
          },
          onEachFeature: (feature, layer) => {
            const hybas = feature.properties?.HYBAS_ID as number;
            const pred = predictions.find(p => p.hybas_id === hybas);
            const imp = impacto.find(i => i.HYBAS_ID === hybas);

            const prob = pred ? `${(pred.probabilidad_deslizamiento * 100).toFixed(1)}%` : '—';
            const nivel = pred?.nivel_riesgo ?? (imp && imp.indice_riesgo > 1000 ? 'Alto' : imp && imp.indice_riesgo > 200 ? 'Medio' : 'Bajo');
            const costo = imp ? `$${imp.costo_m_cop.toFixed(0)} M COP` : '—';
            const eventos = imp?.n_eventos ?? 0;

            layer.bindTooltip(
              `<div style="font-size:12px;line-height:1.5">
                <b>HYBAS ${hybas}</b><br/>
                Prob: <b>${prob}</b> | Nivel: <b>${nivel}</b><br/>
                Costo hist.: <b>${costo}</b> | Eventos: <b>${eventos}</b>
              </div>`,
              { sticky: true }
            );

            layer.on('click', () => onSelectCuenca(hybas));
          },
        }).addTo(map);
      })
      .catch(() => {
        // GeoJSON no disponible aún — mapa base sigue funcionando
      });
  }, [impacto, predictions, onSelectCuenca]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
