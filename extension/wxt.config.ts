import { defineConfig } from 'wxt'
import tailwindcss from '@tailwindcss/vite'
import { loadEnv } from 'vite'

export default defineConfig({
  srcDir: 'src',
  modules: ['@wxt-dev/module-react', '@wxt-dev/auto-icons'],
  autoIcons: { baseIconPath: 'assets/icon.svg' },
  vite: () => ({ plugins: [tailwindcss()] }),
  manifest: ({ mode }) => {
    const env = loadEnv(mode, process.cwd(), 'WXT_')
    const ghlHost = env.WXT_GHL_HOST || 'app.example.com'
    const apiBase = env.WXT_API_BASE_URL || 'http://localhost:8000'
    let apiOrigin = apiBase
    try {
      apiOrigin = new URL(apiBase).origin
    } catch {
      apiOrigin = apiBase
    }
    return {
      name: mode === 'production' ? 'WCM Sales Assistant' : 'WCM Sales Assistant (dev)',
      description: 'Call script, history and research for WCM SDRs inside GoHighLevel.',
      permissions: ['sidePanel', 'storage'],
      host_permissions: [`https://${ghlHost}/*`, `${apiOrigin}/*`],
      side_panel: { default_path: 'sidepanel.html' },
      action: { default_title: 'WCM Sales Assistant' },
    }
  },
})
