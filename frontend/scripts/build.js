import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendDir = path.resolve(__dirname, '..');
const distDir = path.join(frontendDir, 'dist');
const publicDir = path.join(frontendDir, 'public');

// 1. Ensure dist directory exists
if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

// 2. Build CSS using Tailwind CLI
console.log('[BUILD] Compiling Tailwind CSS...');
execSync('npx @tailwindcss/cli -i ./src/input.css -o ./dist/output.css --minify', {
  cwd: frontendDir,
  stdio: 'inherit'
});

// 3. Copy frontend/index.html to frontend/dist/index.html
console.log('[BUILD] Copying index.html to dist...');
fs.copyFileSync(
  path.join(frontendDir, 'index.html'),
  path.join(distDir, 'index.html')
);

// 4. Copy all public assets to dist
console.log('[BUILD] Copying public assets to dist...');
if (fs.existsSync(publicDir)) {
  fs.cpSync(publicDir, distDir, { recursive: true });
}

// 5. Run Neutralino build
console.log('[BUILD] Building Neutralino application bundle...');
execSync('npx @neutralinojs/neu build --release', {
  cwd: frontendDir,
  stdio: 'inherit'
});

// 6. Sync generated resources.neu to frontend/bin and frontend root for compatibility
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
