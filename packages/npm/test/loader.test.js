// Offline tests against the local checkout. Run: node --test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  loadCompounds, loadGrades, loadIdentifiers, loadCosmeticClaims, ATTRIBUTION,
} from '../src/index.js';

const DATA = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'data');
const local = { dataDir: DATA };

test('compounds load offline from the local checkout', async () => {
  const c = await loadCompounds(local);
  assert.equal(c.length, 85);
  assert.ok(c[0].slug && c[0].name && c[0].url.startsWith('https://vallydia.com/'));
});

test('grades parse with quoted fields intact and nulls preserved', async () => {
  const g = await loadGrades(local);
  assert.equal(g.length, 475);
  const nulls = g.filter(r => r.grade === '').length;
  assert.equal(nulls, 97); // safety/penetration rows — never coerced to a letter
  // a caveat with an embedded comma must survive as one field
  assert.ok(g.every(r => 'caveat' in r));
});

test('identifiers never carry a SMILES below high confidence', async () => {
  const idf = await loadIdentifiers(local);
  assert.ok(idf.filter(r => r.identifier_confidence !== 'high').every(r => r.smiles === ''));
});

test('cosmetic claims are only for cosmetic compounds', async () => {
  const [claims, comp] = [await loadCosmeticClaims(local), await loadCompounds(local)];
  const cosmetic = new Set(comp.filter(c => c.is_cosmetic).map(c => c.slug));
  assert.ok(claims.every(c => cosmetic.has(c.slug)));
});

test('attribution string names Vallydia and the licence', () => {
  assert.match(ATTRIBUTION, /vallydia\.com/);
  assert.match(ATTRIBUTION, /CC-BY-4\.0/);
});
