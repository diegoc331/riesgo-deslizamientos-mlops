import { useQuery } from '@tanstack/react-query';
import { client } from './client';
import type { MetadataResponse } from '../types';

export function useMetadata() {
  return useQuery<MetadataResponse>({
    queryKey: ['metadata'],
    queryFn: async () => {
      const res = await client.get<MetadataResponse>('/metadata');
      return res.data;
    },
    staleTime: 5 * 60_000,
  });
}
