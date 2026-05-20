import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // En desarrollo, redirige /api/* a FastAPI en :8000
      // El cliente usa VITE_API_URL=http://localhost:8000 directamente,
      // así que este proxy es solo como alternativa si se prefiere.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
