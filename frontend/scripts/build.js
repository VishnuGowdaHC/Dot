import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendDir = path.resolve(__dirname, '..');
const distDir = path.join(frontendDir, 'dist');
const publicDir = path.join(frontendDir, 'public');

// 1. Build React application bundle using Vite
console.log('[BUILD] Compiling React and Tailwind bundle with Vite...');
execSync('npx vite build', {
  cwd: frontendDir,
  stdio: 'inherit'
});

// 2. Copy public assets to dist if any exist outside Vite
console.log('[BUILD] Verifying public assets in dist...');
if (fs.existsSync(publicDir)) {
  fs.cpSync(publicDir, distDir, { recursive: true });
}

// 3. Run Neutralino build
console.log('[BUILD] Building Neutralino application bundle...');
execSync('npx @neutralinojs/neu build --release', {
  cwd: frontendDir,
  stdio: 'inherit'
});

// 4. Sync generated resources.neu to frontend/bin and frontend root for compatibility
const outRes = path.join(frontendDir, 'out', 'Dot', 'resources.neu');
const binRes = path.join(frontendDir, 'bin', 'resources.neu');
const rootRes = path.join(frontendDir, 'resources.neu');

if (fs.existsSync(outRes)) {
  if (fs.existsSync(path.dirname(binRes))) {
    fs.copyFileSync(outRes, binRes);
    console.log('[BUILD] Synced resources.neu to bin directory.');
  }
  fs.copyFileSync(outRes, rootRes);
  console.log('[BUILD] Synced resources.neu to frontend root directory.');
}

console.log('[BUILD] Frontend build finished successfully.');
