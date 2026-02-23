import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'neutralino-globals',
      transformIndexHtml() {
        let port = '', token = ''
        try {
          const auth = JSON.parse(fs.readFileSync('.tmp/auth_info.json', 'utf8'))
          port = auth.nlPort
          token = auth.nlToken
        } catch(e) {}
        
        return [
          {
            tag: 'script',
            attrs: { src: `http://localhost:${port}/js/neutralino.js` },
            injectTo: 'head-prepend'
          },
          {
            tag: 'script',
            children: `window.NL_PORT=${port};window.NL_TOKEN="${token}";window.NL_ARGS=[];window.NL_GINJECTED=true;`,
            injectTo: 'head-prepend'
          }
        ]
      }
    }
  ]
})