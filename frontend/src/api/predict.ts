import { useMutation, useQuery } from '@tanstack/react-query';
import { client } from './client';
import type { BatchPredictResponse, ImpactoData, PredictRequest, PredictResponse } from '../types';

export function usePredict() {
  return useMutation<PredictResponse, Error, PredictRequest>({
    mutationFn: async (req) => {
      const res = await client.post<PredictResponse>('/predict', req);
      return res.data;
    },
  });
}

export function useBatchPredict() {
  return useMutation<BatchPredictResponse, Error, PredictRequest[]>({
    mutationFn: async (cuencas) => {
      const res = await client.post<BatchPredictResponse>('/predict/batch', { cuencas });
      return res.data;
    },
  });
}

/** Predicciones del modelo ML para la semana actual (549 cuencas). */
export function useSemanaPredictions() {
  return useQuery<BatchPredictResponse>({
    queryKey: ['predicciones-semana-actual'],
    queryFn: async () => {
      // 1. API en tiempo real (backend corriendo)
      try {
        const res = await client.get<BatchPredictResponse>('/predicciones/semana-actual');
        return res.data;
      } catch {
        // 2. Fallback: archivo estático generado por el último run del pipeline
        const res = await fetch('/predicciones_semana_actual.json');
        if (res.ok) return res.json() as Promise<BatchPredictResponse>;
        throw new Error('Predicciones no disponibles');
      }
    },
    staleTime: 6 * 60 * 60_000,
    retry: false,
  });
}

export function useImpacto() {
  return useQuery<ImpactoData[]>({
    queryKey: ['impacto'],
    queryFn: async () => {
      // Intentar primero el archivo estático (siempre disponible sin backend)
      try {
        const res = await fetch('/impacto.json');
        if (res.ok) return res.json() as Promise<ImpactoData[]>;
      } catch {
        // ignorar, intentar API
      }
      // Fallback a la API
      const res = await client.get<ImpactoData[]>('/impacto');
      return res.data;
    },
    staleTime: 60 * 60_000,
  });
}

/** Calcula semana_sin/cos y mes_sin/cos desde la fecha de hoy. */
export function calcSeasonality() {
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 0);
  const dayOfYear = Math.floor((now.getTime() - startOfYear.getTime()) / 86_400_000);
  const weekOfYear = Math.ceil(dayOfYear / 7);
  const month = now.getMonth() + 1;
  const twoPi = 2 * Math.PI;
  return {
    semana_sin: parseFloat(Math.sin((twoPi * weekOfYear) / 52).toFixed(6)),
    semana_cos: parseFloat(Math.cos((twoPi * weekOfYear) / 52).toFixed(6)),
    mes_sin: parseFloat(Math.sin((twoPi * month) / 12).toFixed(6)),
    mes_cos: parseFloat(Math.cos((twoPi * month) / 12).toFixed(6)),
  };
}
