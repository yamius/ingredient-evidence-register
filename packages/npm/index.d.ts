// Type definitions for @vallydia-data/ingredient-register

export const ATTRIBUTION: string;
export const HOMEPAGE: string;
export const VERSION: string;

export type Source = "github" | "hf";

export interface LoadOptions {
  /** Where to fetch published data from. Default "github". Ignored if dataDir is set. */
  source?: Source;
  /** A local checkout's data/ directory — fully offline, no network. */
  dataDir?: string;
  /** Cache fetched files on disk (default true). */
  useCache?: boolean;
}

export type Grade = "A" | "B" | "C" | "D" | "F" | "";

export interface GradeRow {
  slug: string; name: string; compound_class: string;
  outcome: string; grade: Grade; base: string; effect: string; caveat: string;
}
export interface LegalStatusRow {
  slug: string; name: string; region: string; status: string; note: string;
}
export interface CitationRow {
  slug: string; name: string; source_index: string; source_text: string;
  doi: string; resolved: string; verified_title: string;
  openalex_id?: string; semantic_scholar_id?: string;
  citation_count?: string; oa_url?: string; enrichment_source?: string;
}
export interface CosmeticClaimRow {
  slug: string; name: string; claim_type: "allowed" | "forbidden"; claim_text: string;
}
export interface IdentifierRow {
  slug: string; name: string; compound_class: string;
  cas: string; pubchem_cid: string; inchikey: string; inchi: string; smiles: string;
  unii: string; chembl_id: string; drugbank_id: string;
  identifier_source: string; identifier_confidence: "high" | "medium" | "low" | "none";
  entity_note: string;
}
export interface Compound {
  slug: string; name: string; title: string; url: string;
  synonyms: string[]; compound_class: string; overall_grade: Grade | null;
  grades_by_outcome: Array<{ outcome: string; grade: Grade | null; base: string; effect: string; caveat: string }>;
  legal_status: Array<{ region: string; status: string; note: string }>;
  wada: { prohibited: boolean; note: string | null };
  function_tags: string[]; related: string[]; is_cosmetic: boolean;
  structure_image: string | null; grade_card_image: string | null;
  [key: string]: unknown;
}

export function loadCompounds(opts?: LoadOptions): Promise<Compound[]>;
export function loadGrades(opts?: LoadOptions): Promise<GradeRow[]>;
export function loadLegalStatus(opts?: LoadOptions): Promise<LegalStatusRow[]>;
export function loadCitations(opts?: LoadOptions & { enriched?: boolean }): Promise<CitationRow[]>;
export function loadCosmeticClaims(opts?: LoadOptions): Promise<CosmeticClaimRow[]>;
export function loadIdentifiers(opts?: LoadOptions): Promise<IdentifierRow[]>;
