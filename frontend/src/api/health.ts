import { useQuery } from '@tanstack/react-query';
import { client } from './client';
import type { HealthResponse } from '../types';

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: async () => {
      const res = await client.get<HealthResponse>('/health');
      return res.data;
    },
    refetchInterval: 30_000,
    retry: false,
  });
}
