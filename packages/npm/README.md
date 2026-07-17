# @vallydia-data/ingredient-register

A typed loader for the [Vallydia Ingredient-Evidence Register](https://vallydia.com) — an
evidence-graded open dataset of cosmetic and research ingredients.

```bash
npm install @vallydia-data/ingredient-register
```

```js
import { loadCompounds, loadGrades, loadCitations } from '@vallydia-data/ingredient-register';

const compounds = await loadCompounds();   // Compound[] (85)
const grades    = await loadGrades();      // GradeRow[] (456)

const aGrade = grades.filter(g => g.grade === 'A');

// citations with scholarly cross-links (OpenAlex / Semantic Scholar)
const cites = await loadCitations({ enriched: true });
```

Fully typed — `Compound`, `GradeRow`, `IdentifierRow`, etc. are exported.

## Loaders

| Function | Returns | Notes |
|---|---|---|
| `loadCompounds()` | `Compound[]` | full nested records |
| `loadGrades()` | `GradeRow[]` | `grade` is `''` for non-efficacy (safety/penetration) rows |
| `loadLegalStatus()` | `LegalStatusRow[]` | per region |
| `loadCitations({enriched})` | `CitationRow[]` | `enriched: true` adds OpenAlex/S2 cross-links |
| `loadCosmeticClaims()` | `CosmeticClaimRow[]` | permitted / forbidden wordings |
| `loadIdentifiers()` | `IdentifierRow[]` | CAS/CID/InChIKey/SMILES; blanks are honest |

## Where the data comes from

Requires Node ≥ 18 (uses the global `fetch`). By default the loader fetches the published
data from GitHub raw and caches it in the OS temp dir. Options on every loader:

```js
await loadCompounds({ source: 'hf' });                 // Hugging Face mirror
await loadCompounds({ dataDir: '/path/to/data' });     // local checkout, fully offline
await loadCompounds({ useCache: false });              // always re-fetch
```

## Attribution

Data: Vallydia Ingredient-Evidence Register (https://vallydia.com), CC-BY-4.0. Any use — including
in derived datasets or model training — must attribute Vallydia. Appearance/evidence reference
only; not medical advice.
