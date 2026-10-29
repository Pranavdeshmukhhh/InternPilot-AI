// Preserve installed production dependency notices, including vendored licenses.
// This is an attribution inventory, not legal clearance or a project reuse grant.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json'), 'utf8'));
const sections = [
  'InternPilot AI — third-party dependency notices',
  'Generated from the installed production lockfile. Some packages are server/build-only; inclusion does not imply browser use. Preserve the applicable original terms. This inventory is not legal clearance and does not grant a license to InternPilot project source.',
];
let count = 0;
function notices(directory, base, output) {
  for (const entry of fs
    .readdirSync(directory, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory() && !['node_modules', '.git'].includes(entry.name))
      notices(filename, base, output);
    else if (entry.isFile() && /^(licen[cs]e|copying|notice)([.-]|$)/i.test(entry.name)) {
      output.push(`${path.relative(base, filename)}\n${fs.readFileSync(filename, 'utf8')}`);
    }
  }
}
for (const [relative, item] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b))) {
  if (!relative.startsWith('node_modules/') || item.dev) continue;
  const directory = path.resolve(root, relative);
  if (!directory.startsWith(root + path.sep + 'node_modules' + path.sep))
    throw new Error('Invalid package path');
  if (!fs.existsSync(directory)) {
    if (item.optional) continue; // Native optional dependencies differ by OS.
    throw new Error(`Install dependencies first: ${relative}`);
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
  const bodies = [];
  notices(directory, directory, bodies);
  sections.push(
    `\n${'='.repeat(72)}\n${pkg.name}@${pkg.version}\nDeclared license: ${typeof pkg.license === 'string' ? pkg.license : 'See package metadata'}\n${bodies.join('\n\n') || 'No separate notice file present; review the package distribution and declared terms.'}`,
  );
  count++;
}
const target = path.join(root, 'public', 'third-party-notices.txt');
fs.mkdirSync(path.dirname(target), { recursive: true });
fs.writeFileSync(target, sections.join('\n\n') + '\n');
console.log(
  `Preserved installed production notices for ${count} packages; optional platform packages may vary.`,
);
