import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Elektrica Rentals dashboard dev server. PINNED port -- do not remove
// strictPort. This multi-app family assigns fixed ports per dashboard
// (shell=5173, vls=5180, elektrica=5181, collision=5182); a prior
// port-drift incident (Vite silently picking the next free port when
// 5181 was busy) served the WRONG app on a stale bookmarked URL and
// caused real user confusion. strictPort:true makes Vite fail loudly
// instead of drifting.
export default defineConfig({
  server: { port: 5181, strictPort: true },
  plugins: [react()],
})
