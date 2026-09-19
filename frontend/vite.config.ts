import { defineConfig, type HtmlTagDescriptor, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

import siteConfiguration from './.figma/make/site.json'

// Chunk 6 dev proxy target - see the comment on server.proxy below.
function proxyTarget() {
  return {
    target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:5000',
    changeOrigin: true,
    secure: false,
  }
}

// Vite config — https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // .figma/make/deploy-preview passes `--mode development` for cached-preview builds.
  const emitSourcemaps = mode === 'development'

  return {
    base: process.env.FIGMA_PUBLIC_URL ? `${process.env.FIGMA_PUBLIC_URL}/` : '/',
    build: {
      sourcemap: emitSourcemaps ? 'inline' : false,
      minify: !emitSourcemaps,
    },
    plugins: [
      react(),
      tailwindcss(),
      figmaSiteConfiguration(siteConfiguration),
      figmaErrorOverlayReplay(),
      figmaReactRefreshBoundaryFallback(),
      figmaMakeKitPlugin({ storiesGlob: '/src/**/*.stories.{ts,tsx,js,jsx}' }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: parseInt(process.env.PORT || '8443'),
      strictPort: true,
      watch: { ignored: ['**/.figma/**'] },
      // Dev-only proxy to the local Flask backend. Needed because Vite and
      // Flask run on different ports/origins in dev, and the backend's
      // session cookie is SameSite=Lax with no CORS configured - without
      // this, fetch() calls in src/lib/api.ts would 404 against Vite
      // itself instead of reaching Flask, and even if they didn't, the
      // session cookie wouldn't be sent cross-origin. In production the
      // built frontend is served from Flask's static/ folder (same
      // origin), so this proxy only matters for `npm run dev`.
      //
      // Set VITE_API_PROXY_TARGET in your .env if Flask isn't running on
      // the default http://127.0.0.1:5000 (e.g. python app.py's default).
      proxy: {
        '/chats': proxyTarget(),
        '/users': proxyTarget(),
        '/documents': proxyTarget(),
        '/units': proxyTarget(),
        '/universities': proxyTarget(),
        '/content': proxyTarget(),
        '/content-reports': proxyTarget(),
        '/forum': proxyTarget(),
        '/library': proxyTarget(),
        '/admin': proxyTarget(),
        '/auth': proxyTarget(),
        '/login': proxyTarget(),
        '/logout': proxyTarget(),
        '/signup': proxyTarget(),
        '/me': proxyTarget(),
        '/profile': proxyTarget(),
        '/forgot-password': proxyTarget(),
        '/reset-password': proxyTarget(),
        '/resend-verification': proxyTarget(),
        '/verify-email': proxyTarget(),
        '/delete-account': proxyTarget(),
        '/payment': proxyTarget(),
        '/payment-history': proxyTarget(),
        '/subscription': proxyTarget(),
        '/achievements': proxyTarget(),
        '/streak': proxyTarget(),
        '/study-time': proxyTarget(),
        '/xp': proxyTarget(),
        '/gamification': proxyTarget(),
        '/groups': proxyTarget(),
        '/organisations': proxyTarget(),
        '/opportunities': proxyTarget(),
        '/notifications': proxyTarget(),
        '/ambassador': proxyTarget(),
        '/warnings': proxyTarget(),
        '/health': proxyTarget(),
        '/api': proxyTarget(),
      },
    },
    preview: {
      host: '0.0.0.0',
      port: parseInt(process.env.PORT || '8443'),
    },
  }
})

type FigmaSiteConfiguration = {
  title?: string
  description?: string
  language?: string
  robots?: {
    index?: boolean
  }
  icons?: {
    icon?: string
  }
  openGraph?: {
    image?: string
  }
  analytics?: {
    googleAnalyticsId?: string
  }
  customScripts?: {
    headStart?: string
    headEnd?: string
    bodyStart?: string
    bodyEnd?: string
  }
  accessibility?: {
    addBypassLinks?: boolean
  }
}

/** Applies /.figma/make/site.json to the generated document shell. */
function figmaSiteConfiguration(config: FigmaSiteConfiguration): Plugin {
  function sanitizeHtmlValue(value: string | undefined): string {
    return value?.replace(/[^a-zA-Z0-9_-]/g, '') || ''
  }
  function escapeHtmlText(value: string): string {
    return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
  function replaceHtmlCommentSlot(html: string, slotName: string, content: string): string {
    return html.replace(`<!-- ${slotName} -->`, content)
  }

  const title = config.title ?? "Figma Make App"
  const description = config.description ?? ''
  const favicon = config.icons?.icon ?? ''
  const socialImage = config.openGraph?.image ?? ''
  const language = sanitizeHtmlValue(config.language) || 'en'
  const googleAnalyticsId = sanitizeHtmlValue(config.analytics?.googleAnalyticsId)
  const headStart = config.customScripts?.headStart ?? ''
  const headEnd = config.customScripts?.headEnd ?? ''
  const bodyStart = config.customScripts?.bodyStart ?? ''
  const bodyEnd = config.customScripts?.bodyEnd ?? ''
  const robotsTxt = config.robots?.index === false ? 'User-agent: *\nDisallow: /\n' : ''

  return {
    name: 'figma-site-configuration',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!robotsTxt || req.url?.split('?')[0] !== '/robots.txt') return next()

        res.setHeader('Content-Type', 'text/plain; charset=utf-8')
        res.end(robotsTxt)
      })
    },
    generateBundle() {
      if (!robotsTxt) return

      this.emitFile({
        type: 'asset',
        fileName: 'robots.txt',
        source: robotsTxt,
      })
    },
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        let result = html
        result = replaceHtmlCommentSlot(result, 'figma:lang', language)
        result = replaceHtmlCommentSlot(result, 'figma:title', escapeHtmlText(title))
        result = replaceHtmlCommentSlot(result, 'figma:head-start', headStart)
        result = replaceHtmlCommentSlot(result, 'figma:head-end', headEnd)
        result = replaceHtmlCommentSlot(result, 'figma:body-start', bodyStart)
        result = replaceHtmlCommentSlot(result, 'figma:body-end', bodyEnd)