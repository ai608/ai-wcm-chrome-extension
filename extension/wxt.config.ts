import { defineConfig } from 'wxt'
import tailwindcss from '@tailwindcss/vite'
import { loadEnv } from 'vite'

function requireReleaseUrl(name: string, value: string | undefined): void {
  if (!value) throw new Error(`${name} is required for a release`)
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error(`${name} must be a valid HTTPS URL`)
  }
  if (
    url.protocol !== 'https:' ||
    ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  ) {
    throw new Error(`${name} must be a deployed HTTPS URL`)
  }
}

export default defineConfig({
  srcDir: 'src',
  outDir: process.env.WCM_DEBUG ? '.output-debug' : '.output',
  modules: ['@wxt-dev/module-react', '@wxt-dev/auto-icons'],
  autoIcons: { baseIconPath: 'assets/icon.svg' },
  vite: () => ({
    plugins: [tailwindcss()],
    // WCM_DEBUG=1: unminified dev React, so errors like #185 name the component
    ...(process.env.WCM_DEBUG
      ? { define: { 'process.env.NODE_ENV': '"development"' }, build: { minify: false } }
      : {}),
  }),
  manifest: ({ mode }) => {
    const env = loadEnv(mode, process.cwd(), 'WXT_')
    if (process.env.WXT_RELEASE === '1') {
      requireReleaseUrl('WXT_API_BASE_URL', env.WXT_API_BASE_URL)
      requireReleaseUrl('WXT_O1_WEB_URL', env.WXT_O1_WEB_URL)
      if (env.WXT_API_MOCK !== 'false') {
        throw new Error('WXT_API_MOCK must be false for a release')
      }
    }
    const ghlHost = env.WXT_GHL_HOST || 'app.example.com'
    const apiBase = env.WXT_API_BASE_URL || 'http://localhost:8001'
    const o1WebUrl = new URL(env.WXT_O1_WEB_URL || 'http://localhost:5173')
    let apiOrigin = apiBase
    try {
      apiOrigin = new URL(apiBase).origin
    } catch {
      apiOrigin = apiBase
    }
    return {
      name: mode === 'production' ? 'WCM Sales Assistant' : 'WCM Sales Assistant (dev)',
      description: 'Call script, history and research for WCM SDRs inside GoHighLevel.',
      permissions: ['sidePanel', 'storage', 'tabs'],
      host_permissions: [`https://${ghlHost}/*`, `${apiOrigin}/*`],
      externally_connectable: {
        matches: [`${o1WebUrl.protocol}//${o1WebUrl.hostname}/*`],
      },
      side_panel: { default_path: 'sidepanel.html' },
      action: { default_title: 'WCM Sales Assistant' },
    }
  },
})
