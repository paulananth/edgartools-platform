// THROWAWAY PROTOTYPE — inlines interpret.mjs and the Person document into
// demo.src.html so demo.html opens by double-click (file://, no server).
//   node build-demo.mjs
import { readFileSync, writeFileSync } from 'node:fs';

const src = readFileSync('demo.src.html', 'utf8');
const mod = readFileSync('interpret.mjs', 'utf8')
  .replace(/^export /gm, '');                       // inline: no module exports
const doc = readFileSync('policy-person.json', 'utf8');

const out = src.replace(
  /\/\/ The interpreter and the documents[\s\S]*?await \(await fetch\('\.\/policy-person\.json'\)\)\.json\(\);/,
  () => `// INLINED by build-demo.mjs — edit interpret.mjs / policy-person.json, then rebuild.\n${mod}\nconst person = ${doc};`
);
if (out === src) { console.error('marker not found — demo.src.html changed shape'); process.exit(1); }
writeFileSync('demo.html', out);
console.log(`demo.html written (${(out.length / 1024).toFixed(0)} KB, self-contained)`);
