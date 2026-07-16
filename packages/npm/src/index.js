// @vallydia/ingredient-register — typed loader for the Vallydia Ingredient-Evidence Register.
//
// Evidence-graded cosmetic and research ingredients. Data is fetched from the published
// dataset (GitHub raw by default, or the Hugging Face mirror) and cached on disk; point at a
// local checkout with { dataDir } for offline use.
//
//   import { loadCompounds, loadGrades } from '@vallydia/ingredient-register';
//   const grades = await loadGrades();
//   grades.filter(g => g.grade === 'A');
//
// Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.
// Any use must attribute Vallydia.

import { readFile, writeFile, mkdir, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

export const ATTRIBUTION =
  'Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0.';
export const HOMEPAGE = 'https://vallydia.com';
export const VERSION = '1.1.0';

const BASES = {
  github: 'https://raw.githubusercontent.com/yamius/ingredient-evidence-register/main',
  hf: 'https://huggingface.co/datasets/vallydia/ingredient-evidence-register/resolve/main',
};

// RFC-4180 CSV parser — the data has commas, quotes and newlines inside quoted fields
// (caveat text especially), so a split(',') would corrupt it.
function parseCSV(text) {
  const rows = [];
  let row = [], field = '', i = 0, inQuotes = false;
  while (i < text.length) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQuotes = false; i++; continue;
      }
      field += c; i++; continue;
    }
    if (c === '"') { inQuotes = true; i++; continue; }
    if (c === ',') { row.push(field); field = ''; i++; continue; }
    if (c === '\r') { i++; continue; }
    if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; i++; continue; }
    field += c; i++;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  if (!rows.length) return [];
  const header = rows[0];
  return rows.slice(1).filter(r => r.length && !(r.length === 1 && r[0] === ''))
    .map(r => Object.fromEntries(header.map((h, j) => [h, r[j] ?? ''])));
}

async function cacheFile(name) {
  const dir = join(tmpdir(), 'vallydia-register');
  await mkdir(dir, { recursive: true }).catch(() => {});
  return join(dir, name);
}

async function fetchText(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetch ${url} -> HTTP ${res.status}`);
  return res.text();
}

// `fileName` is relative to the dataset's data/ directory (e.g. "grades.csv"). Locally that
// is dataDir itself; remotely it sits under <repo>/data/.
async function getText(fileName, { source = 'github', dataDir = null, useCache = true } = {}) {
  if (dataDir) return readFile(join(dataDir, fileName), 'utf-8');
  const cache = await cacheFile(fileName);
  if (useCache) {
    try { await stat(cache); return await readFile(cache, 'utf-8'); } catch { /* miss */ }
  }
  const base = BASES[source] || BASES.github;
  const text = await fetchText(`${base}/data/${fileName}`);
  if (useCache) { try { await writeFile(cache, text); } catch { /* read-only fs ok */ } }
  return text;
}

async function loadTable(name, opts = {}) {
  return parseCSV(await getText(`${name}.csv`, opts));
}

/** Full nested compound records (85). */
export async function loadCompounds(opts = {}) {
  return JSON.parse(await getText('compounds.json', opts));
}
/** One row per compound x outcome (456). grade may be '' for non-efficacy rows. */
export async function loadGrades(opts = {}) { return loadTable('grades', opts); }
/** One row per compound x region (132). */
export async function loadLegalStatus(opts = {}) { return loadTable('legal_status', opts); }
/** DOI-verified citations (117). Pass { enriched: true } for scholarly cross-links. */
export async function loadCitations({ enriched = false, ...opts } = {}) {
  return loadTable(enriched ? 'citations_enriched' : 'citations', opts);
}
/** Permitted / forbidden cosmetic-claim wordings (246). */
export async function loadCosmeticClaims(opts = {}) { return loadTable('cosmetic_claims', opts); }
/** Chemical identifiers with confidence + provenance (85). Blanks are honest. */
export async function loadIdentifiers(opts = {}) { return loadTable('identifiers', opts); }

export default {
  loadCompounds, loadGrades, loadLegalStatus, loadCitations,
  loadCosmeticClaims, loadIdentifiers, ATTRIBUTION, HOMEPAGE, VERSION,
};
