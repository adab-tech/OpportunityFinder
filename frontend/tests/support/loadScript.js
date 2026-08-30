import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, '..', '..');

/**
 * Executes an actual production script (js/app.js, js/admin.js) — completely
 * unmodified — against the current jsdom global scope, the same way a
 * classic (non-module) <script> tag would run it in a real browser: a
 * top-level `function foo(){}` becomes `window.foo`, while top-level
 * `const`/`let` stay local to the script and are only reachable through
 * closures. This is deliberate: it means these tests exercise the exact
 * file that ships to production, with zero risk of the test harness
 * drifting from real behavior, and require no changes to the site's
 * script-loading model (still plain <script src> tags, no build step).
 */
export function loadScript(relativePath) {
  const code = fs.readFileSync(path.join(FRONTEND_DIR, relativePath), 'utf-8');
  vm.runInThisContext(code, { filename: relativePath });
}
