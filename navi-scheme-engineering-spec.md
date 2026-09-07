# Navi Scheme — Engineering Business Logic Specification (v1)
### Maps directly onto the repo structure in the project README. Written so an AI coding agent (or a human dev) can implement the MVP with no ambiguous decisions left open.

---

## 0. How to Use This Document

Each section corresponds to a real folder in the repo tree. Implement in the order given in **§12 (Build Order)** — later modules depend on earlier ones being contract-stable. Every schema below is the *source of truth*; if code and this doc disagree, this doc wins until explicitly revised.

Three things marked **[NEEDS YOUR INPUT]** below are genuinely blocked on your data/decisions — everything else has a concrete default so the agent can proceed without stalling.

---

## 1. Environment & Setup Decisions

### 1.1 AI — Gemini

- Model: `gemini-2.5-flash` (primary) — good reasoning/cost balance, 1M context, free tier via AI Studio.
- Fallback for high free-tier volume during dev/testing: `gemini-2.5-flash-lite` (higher RPD on the free tier).
- **Do not use `gemini-1.5-flash` or `gemini-1.5-pro`** — both deprecated; calls will return model-not-found errors.
- `GEMINI_MODEL` should be an env var, not hardcoded, so it can be swapped without a redeploy.
- Free tier is rate-limited (RPM/RPD, project-specific — check your AI Studio console). Code must handle `429 RESOURCE_EXHAUSTED` with exponential backoff (start 1s, double, cap ~64s, ±20% jitter) and a graceful degraded response (§5.5) rather than a raw error to the citizen.

### 1.2 Database — Free, prod + local

**Recommendation:** Neon (serverless Postgres, permanent free tier: 0.5GB storage, scale-to-zero compute, standard Postgres wire protocol — no proprietary API, works with your existing `pg8000` driver unchanged).

- **Local dev (zero-cost, offline-friendly):** SQLite (`navi_scheme.db`) — keep this as the default for `NODE_ENV=development` when `DATABASE_URL` is unset.
- **Prod (and optionally shared local/staging):** Neon Postgres via `DATABASE_URL=postgresql+pg8000://<user>:<pass>@<neon-host>/<db>?sslmode=require`.
- Your existing AlloyDB code path: **keep commented out, not deleted**, behind a `DB_DRIVER=alloydb|neon|sqlite` env flag so it's a one-line swap later — matches your instruction to preserve it for future GCP migration.
- **Caveat to plan around:** Neon free tier suspends compute after idle — first query after suspend has a cold-start delay (hundreds of ms to a few seconds). Fine for MVP; the API layer should not treat this as a failure (set a slightly generous DB connection timeout, e.g. 10s, on cold path).
- Because both SQLite and Postgres must work from the same codebase, **all schema/migrations must avoid Postgres-only or SQLite-only types** — see §7 for the dialect-safe schema.

### 1.3 Data & Taxonomies — **[NEEDS YOUR INPUT]**

I don't have visibility into `data/schemes/schemes_data.csv`'s actual columns. §8 below defines the **assumed canonical schema** the matching engine and API are built against. Two things to confirm or send over:
1. The actual column headers of `schemes_data.csv` (or a 5-row sample) so I can give you an exact mapping/import script instead of an assumed one.
2. Any custom taxonomy rules you already have in mind (state residency codes, income slab boundaries, category/reservation codes, landholding limits, scholarship tiers) — if none yet, §8.3 ships sensible MVP defaults you can override.

Until confirmed, the ingestion layer is built against the assumed schema in §8.1 with a single mapping function isolated in `scripts/import-schemes.ts` — so correcting the mapping later touches one file, not the whole pipeline.

### 1.4 Language & Localization

**MVP recommendation:** English + Hindi only, expand later per Phase 2/3 regions.
- **UI strings:** pre-translated dictionary files (`apps/web/public/locales/en.json`, `hi.json`) — not on-the-fly Gemini translation. Reasons: zero latency, zero API cost, deterministic (a mistranslated button label is a bug you can catch in review; a mistranslated one from an LLM call is not).
- **AI explanation text** (§5): Gemini generates directly in the requested language as part of the grounded prompt — this *is* appropriate for Gemini since it's prose generation, not fixed UI chrome. The prompt template in §5.3 takes a `language` parameter.
- `Accept-Language` / an explicit in-app toggle sets `language`, stored on the profile so results stay consistent across sessions.

### 1.5 Security & Admin

- `JWT_SECRET_KEY`: generate with `openssl rand -base64 48` (or equivalent CSPRNG) at deploy time — **never a literal string checked into `.env.example`**. `.env.example` should show the variable name with a placeholder comment only.
- **Do not ship a hardcoded default admin password**, including `admin@navischeme.gov.in` with a fixed password. Instead (§9): a bootstrap script creates the admin account with a **randomly generated one-time password printed once to deploy logs**, and the account is forced into a password-change flow on first login. This avoids the single most common admin-panel breach pattern (unrotated default credentials left in a public repo's history).

### 1.6 `.env.example` (final)

```bash
# --- Runtime ---
NODE_ENV=development                # development | production

# --- Database ---
DB_DRIVER=sqlite                    # sqlite | neon | alloydb (alloydb path stays commented in code)
DATABASE_URL=                       # required if DB_DRIVER=neon or alloydb
                                     # e.g. postgresql+pg8000://user:pass@host/db?sslmode=require
SQLITE_PATH=./navi_scheme.db        # used only if DB_DRIVER=sqlite

# --- AI ---
GEMINI_API_KEY=                     # from Google AI Studio
GEMINI_MODEL=gemini-2.5-flash       # gemini-2.5-flash | gemini-2.5-flash-lite
GEMINI_MAX_OUTPUT_TOKENS=800
GEMINI_TIMEOUT_MS=8000

# --- Auth ---
JWT_SECRET_KEY=                     # generate via: openssl rand -base64 48
JWT_EXPIRES_IN=7d
ADMIN_BOOTSTRAP_EMAIL=admin@navischeme.gov.in

# --- App ---
DEFAULT_LANGUAGE=en                 # en | hi
SUPPORTED_LANGUAGES=en,hi
RATE_LIMIT_RPM=60                   # per-IP, applies to /api/eligibility/match and /api/schemes/:id/explain
```

---

## 2. Domain Model (`packages/domain`)

These are the canonical TypeScript types every other package imports — never redefine these shapes locally elsewhere.

```typescript
// packages/domain/src/scheme.ts

export type SchemeStatus = "active" | "upcoming" | "closed" | "under_review";
export type IssuingLevel = "central" | "state";

export interface EligibilityRule {
  field: string;                 // must match a ProfileField key (see below)
  operator: "eq" | "neq" | "in" | "not_in" | "lte" | "gte" | "between" | "exists";
  value: string | number | boolean | [number, number] | string[];
  required: boolean;             // true = hard-fail if unmet; false = soft/preferred criterion
}

export interface EligibilityRuleSet {
  logic: "AND" | "OR";
  rules: EligibilityRule[];
  groups?: EligibilityRuleSet[];  // nested groups for compound logic
}

export interface Scheme {
  id: string;                     // stable slug, e.g. "pm-kisan-samman-nidhi"
  name: string;
  issuingLevel: IssuingLevel;
  issuingBody: string;            // e.g. "Ministry of Agriculture" or "Govt of Maharashtra"
  state?: string;                 // required if issuingLevel = "state"
  sector: string;                 // e.g. "agriculture" | "education" | "health" | "housing" | "pension" | "disability" | "women" | "employment"
  description: string;            // plain-language, curator-written, NOT scraped verbatim
  eligibility: EligibilityRuleSet;
  benefits: string;               // plain-language summary; never a guaranteed numeric promise in prose
  benefitAmount?: { min?: number; max?: number; unit: "INR" | "percent" | "in-kind" };
  documentsRequired: string[];
  applicationSteps: string[];
  applicationUrl: string;         // official portal only
  applicationMode: "online" | "offline" | "both";
  deadline?: string;              // ISO date, absent = rolling/no deadline
  status: SchemeStatus;
  sourceUrls: string[];           // one or more official source references
  lastVerifiedAt: string;         // ISO datetime
  version: number;
}
```

```typescript
// packages/domain/src/profile.ts

export type Occupation =
  | "farmer" | "student" | "salaried" | "self_employed"
  | "unemployed" | "homemaker" | "retired" | "daily_wage_informal";

export type SocialCategory = "general" | "obc" | "sc" | "st" | "ews" | "prefer_not_to_say";

export interface CitizenProfile {
  id: string;
  userId: string;                 // null for guest/session-only profiles
  state: string;
  district?: string;
  pincode?: string;
  age: number;
  gender: "male" | "female" | "other" | "prefer_not_to_say";
  occupation: Occupation;
  incomeBracket: "below_1l" | "1l_3l" | "3l_6l" | "6l_10l" | "above_10l" | "prefer_not_to_say";
  socialCategory?: SocialCategory;
  disabilityStatus?: boolean;
  maritalStatus?: "single" | "married" | "widowed" | "prefer_not_to_say";
  landOwnedHectares?: number;
  educationLevel?: "below_10th" | "10th_12th" | "graduate" | "postgraduate";
  hasRationCard?: boolean;
  hasAadhaarLinkedBank?: boolean;
  dependents?: number;
  isProxyProfile: boolean;        // true if user is filling on behalf of someone else
  language: "en" | "hi";
  consent: {
    sensitiveFieldsConsented: boolean;   // gates socialCategory/disabilityStatus/incomeBracket collection
    consentedAt?: string;
  };
  completenessScore: number;      // 0-100, computed — see §4.5
  createdAt: string;
  updatedAt: string;
}
```

```typescript
// packages/domain/src/matching.ts

export type ConfidenceLevel = "high" | "medium" | "low" | "not_eligible";

export interface MatchedCriterion {
  field: string;
  ruleDescription: string;   // plain-language, e.g. "Annual income below ₹1 lakh"
  profileValue: unknown;
  satisfied: boolean;
}

export interface EligibilityMatch {
  schemeId: string;
  confidence: ConfidenceLevel;
  score: number;                     // 0-100, used for ranking within a confidence tier
  matchedCriteria: MatchedCriterion[];
  missingFields: string[];           // profile fields needed to raise confidence
  explanation?: string;              // populated by packages/ai, never generated elsewhere
}
```

---

## 3. Validation Schemas (`packages/validation`)

Shared between web forms and API — **one schema, two consumers**, so client and server can never silently drift.

```typescript
// packages/validation/src/profile.schema.ts  (zod-style; adapt to actual lib in use)

export const ProfileInputSchema = z.object({
  state: z.string().min(1),
  district: z.string().optional(),
  pincode: z.string().regex(/^\d{6}$/).optional(),
  age: z.number().int().min(0).max(120),
  gender: z.enum(["male", "female", "other", "prefer_not_to_say"]),
  occupation: z.enum([
    "farmer","student","salaried","self_employed",
    "unemployed","homemaker","retired","daily_wage_informal"
  ]),
  incomeBracket: z.enum([
    "below_1l","1l_3l","3l_6l","6l_10l","above_10l","prefer_not_to_say"
  ]),
  socialCategory: z.enum(["general","obc","sc","st","ews","prefer_not_to_say"]).optional(),
  disabilityStatus: z.boolean().optional(),
  maritalStatus: z.enum(["single","married","widowed","prefer_not_to_say"]).optional(),
  landOwnedHectares: z.number().min(0).max(1000).optional(),
  educationLevel: z.enum(["below_10th","10th_12th","graduate","postgraduate"]).optional(),
  hasRationCard: z.boolean().optional(),
  hasAadhaarLinkedBank: z.boolean().optional(),
  dependents: z.number().int().min(0).max(30).optional(),
  isProxyProfile: z.boolean().default(false),
  language: z.enum(["en","hi"]).default("en"),
  consent: z.object({
    sensitiveFieldsConsented: z.boolean()
  })
});
```

**Business validation rules enforced at the service layer (not just schema-level):**

| Rule | Enforcement |
|---|---|
| `age < 18` AND `occupation IN [salaried, retired]` | Reject with a clarifying-question response, not a hard 400 — this is a chat correction, not an API error |
| `socialCategory`, `disabilityStatus`, `incomeBracket` requested without `consent.sensitiveFieldsConsented = true` | API strips these fields silently server-side rather than erroring — never block the request over a missing optional consent |
| `landOwnedHectares` present but `occupation != farmer` | Allowed (person may own land without farming being primary occupation) — no rejection, just doesn't boost agriculture-sector matches |
| `pincode` present but doesn't map to declared `state` | Non-blocking warning surfaced to the citizen ("this pincode doesn't look like it's in {state} — please confirm"), not silently overridden |

---

## 4. Matching Engine (`packages/matching`)

**This package must be pure and deterministic — no AI calls inside it.** Given the same profile + catalog snapshot, it must always return the same result. This is what makes it independently unit-testable and is the credibility foundation the whole product depends on.

### 4.1 Rule Evaluation

```
function evaluateRule(rule: EligibilityRule, profile: CitizenProfile): "satisfied" | "violated" | "unknown":
    fieldValue = profile[rule.field]
    if fieldValue is undefined or null:
        return "unknown"          # citizen never answered this field

    switch rule.operator:
        case "eq":       return fieldValue == rule.value ? "satisfied" : "violated"
        case "neq":       return fieldValue != rule.value ? "satisfied" : "violated"
        case "in":        return rule.value.includes(fieldValue) ? "satisfied" : "violated"
        case "not_in":    return !rule.value.includes(fieldValue) ? "satisfied" : "violated"
        case "lte":       return fieldValue <= rule.value ? "satisfied" : "violated"
        case "gte":       return fieldValue >= rule.value ? "satisfied" : "violated"
        case "between":   return (fieldValue >= rule.value[0] && fieldValue <= rule.value[1]) ? "satisfied" : "violated"
        case "exists":    return fieldValue != null ? "satisfied" : "violated"
```

### 4.2 RuleSet Evaluation (recursive, handles nested groups)

```
function evaluateRuleSet(ruleSet: EligibilityRuleSet, profile): { satisfied: bool, violated: bool, unknownFields: string[], results: MatchedCriterion[] }:
    results = []
    unknownFields = []
    outcomes = []

    for rule in ruleSet.rules:
        outcome = evaluateRule(rule, profile)
        results.append({ field: rule.field, satisfied: outcome == "satisfied", ... })
        if outcome == "unknown": unknownFields.push(rule.field)
        outcomes.push({ outcome, required: rule.required })

    for group in (ruleSet.groups ?? []):
        subResult = evaluateRuleSet(group, profile)
        results += subResult.results
        unknownFields += subResult.unknownFields
        outcomes.push({ outcome: subResult.satisfied ? "satisfied" : (subResult.violated ? "violated" : "unknown"), required: true })

    if ruleSet.logic == "AND":
        violated = outcomes.any(o => o.outcome == "violated" && o.required == true)
        satisfied = !violated && outcomes.all(o => o.outcome == "satisfied" || o.required == false)
    else: # OR
        violated = outcomes.all(o => o.outcome == "violated")
        satisfied = outcomes.any(o => o.outcome == "satisfied")

    return { satisfied, violated, unknownFields, results }
```

### 4.3 Confidence Assignment

```
function assignConfidence(evalResult) -> ConfidenceLevel:
    if evalResult.violated:
        return "not_eligible"          # hard-excluded, never shown in the main ranked list
    if evalResult.satisfied and evalResult.unknownFields.length == 0:
        return "high"
    if evalResult.unknownFields.length <= 2 and no violated required-rule:
        return "medium"
    return "low"
```

### 4.4 Ranking

```
function rankMatches(matches: EligibilityMatch[]) -> EligibilityMatch[]:
    confidenceWeight = { high: 3, medium: 2, low: 1 }
    sort by:
      1. confidenceWeight[confidence] DESC
      2. benefitRelevanceScore DESC     # simple heuristic: sector match to stated occupation/need = +weight
      3. deadline ASC (nulls last)       # sooner deadlines surface first within same tier
    exclude confidence == "not_eligible" from the default returned list
    return top N (default 20, paginated)
```

`score` (0–100) used for tie-breaking within a tier = `(satisfiedRequiredRules / totalRequiredRules) * 70 + (satisfiedOptionalRules / totalOptionalRules) * 30`.

### 4.5 Profile Completeness Score

```
completenessScore = round( (fieldsAnswered / totalRelevantFields) * 100 )
```
`totalRelevantFields` = the union of all fields referenced by rules across schemes matching the citizen's `state` + `occupation` context (not the full universe of all fields — keeps the score meaningful and not artificially low).

### 4.6 Explainability Endpoint Logic ("why wasn't I matched")

```
function explainNonMatch(schemeId, profile):
    evalResult = evaluateRuleSet(scheme.eligibility, profile)
    violatedRequired = evalResult.results.filter(r => !r.satisfied && correspondingRule.required)
    return {
      violatedCriteria: violatedRequired,   # plain-language, sourced from rule.field + scheme copy — never AI-invented
      missingFields: evalResult.unknownFields
    }
```

---

## 5. AI Explanation Layer (`packages/ai`)

### 5.1 Hard Contract

`packages/ai` receives **only**:
- The matched `Scheme` record(s) (already-verified structured facts)
- The relevant `MatchedCriterion[]` from the matching engine
- Target `language`

It must **never** receive the raw citizen profile beyond what's needed for phrasing (e.g., name is never sent), and must **never** be the source of eligibility facts — those come exclusively from `packages/matching`. This package's only job is **simplification and phrasing**, not reasoning about eligibility.

### 5.2 Function Signature

```typescript
// packages/ai/src/explain.ts

interface ExplainInput {
  scheme: Pick<Scheme, "name"|"description"|"benefits"|"documentsRequired"|"applicationSteps"|"sourceUrls"|"lastVerifiedAt">;
  matchedCriteria: MatchedCriterion[];
  confidence: ConfidenceLevel;
  language: "en" | "hi";
}

interface ExplainOutput {
  plainLanguageSummary: string;   // 1-2 sentences: what you get
  whyMatched: string;             // grounded in matchedCriteria only
  nextSteps: string;              // paraphrased from applicationSteps, not verbatim
  disclaimer: string;             // always appended, see §5.4
}

async function explainScheme(input: ExplainInput): Promise<ExplainOutput>
```

### 5.3 Prompt Template

```
SYSTEM:
You are Navi Scheme's explanation assistant. You simplify already-verified government
scheme facts into plain, warm {{language}} for a citizen. You do not have general
knowledge about government schemes beyond what is given to you below — treat it as
the complete and only truth.

Rules you must follow exactly:
1. Only use facts present in SCHEME_FACTS and MATCHED_CRITERIA below. Never add,
   infer, or assume any eligibility criterion, benefit amount, deadline, or process
   step not explicitly given.
2. Do not state or imply a guaranteed benefit amount — phrase amounts as
   "eligible applicants typically receive ~X", never "you will get X".
3. Do not invent a deadline. If SCHEME_FACTS has no deadline, do not mention one.
4. Paraphrase application steps in your own words — never copy sentences verbatim
   from SCHEME_FACTS.
5. Keep total output under 150 words.
6. Respond only in {{language}}.
7. If MATCHED_CRITERIA is empty or contradictory, say you're not confident why this
   matched, rather than fabricating a reason.

SCHEME_FACTS:
{{scheme_json}}

MATCHED_CRITERIA:
{{matched_criteria_json}}

USER: Explain why this scheme matched and what to do next.
```

### 5.4 Mandatory Disclaimer (appended in code, not model-generated — never rely on the model to remember this)

> "This is a guide, not a final decision. Please verify current details on the official source before applying." (localized per `language`)

### 5.5 Failure & Degradation Behavior

| Failure | Behavior |
|---|---|
| Gemini API timeout (>`GEMINI_TIMEOUT_MS`) | Return the raw structured facts (scheme.description, benefits, applicationSteps) directly, unformatted but accurate — never block the citizen on AI availability |
| `429 RESOURCE_EXHAUSTED` | Same fallback as above + exponential backoff retry queued for next request, not the current one |
| Model output fails a post-generation validation check (§5.6) | Discard model output, use the same structured-fact fallback, log the incident for QA review |

### 5.6 Post-Generation Guardrail Checks (run before returning to the citizen)

```
function validateAIOutput(output: string, schemeFacts): boolean:
    reject if output contains a ₹ amount not present in schemeFacts.benefitAmount
    reject if output contains a date pattern not equal to schemeFacts.deadline
    reject if output length > 300 words (contract violation, likely hallucination sprawl)
    reject if output contains a URL not in schemeFacts.sourceUrls / applicationUrl
    else accept
```
This is a cheap regex/string-containment check, not another LLM call — keep it fast and deterministic.

---

## 6. API Layer (`apps/api`)

### 6.1 Middleware Stack (applied in this exact order)

```
1. requestId          — attach a UUID for tracing/logs
2. cors
3. bodyParser (json, size-limited to 100kb — no document uploads in MVP)
4. rateLimiter         — per-IP, RATE_LIMIT_RPM, applies to /eligibility/match and /schemes/:id/explain
5. auth (optional)     — decodes JWT if present, attaches req.user; does NOT reject if absent (guest access is valid for GET /schemes and POST /eligibility/match)
6. authRequired        — only on /admin/* and /users/me/* routes; 401 if no valid JWT
7. adminRequired       — only on /admin/* routes; 403 if authenticated but role != admin/curator
8. validate(schema)    — per-route zod validation; 400 with field-level errors on failure
9. controller
10. errorHandler       — catches everything below, maps to error catalog (§6.4), never leaks stack traces to the client
```

### 6.2 Auth & JWT Logic

- Citizen accounts: mobile number + OTP (OTP delivery is out of scope for this doc's business logic — treat as a pluggable SMS provider interface; **do not build OTP verification with a fixed/mock code path reachable in production**).
- JWT payload: `{ sub: userId, role: "citizen" | "curator" | "admin" | "support", iat, exp }`.
- `JWT_EXPIRES_IN=7d` for citizens (low friction, matches informal-usage pattern); shorter-lived (e.g. `2h`) recommended for admin/curator tokens with refresh — **flag this as a deliberate asymmetry**, not an oversight, if a reviewer questions it.
- Guest sessions: no JWT. A `guestSessionId` (random UUID) is generated client-side and passed as a header for session-scoped, non-persisted matching only — never written to the `users`/`profiles` tables.

### 6.3 Endpoint-by-Endpoint Contract

**`GET /api/schemes`**
- Query params: `state?`, `sector?`, `status? (default: active)`, `page?`, `pageSize? (default 20, max 50)`
- 200 → `{ schemes: Scheme[], total: number, page: number }`
- No auth required.

**`GET /api/schemes/:schemeId`**
- 200 → full `Scheme` object incl. `sourceUrls`, `lastVerifiedAt`
- 404 → `{ error: "SCHEME_NOT_FOUND" }`

**`POST /api/eligibility/match`**
- Body: `ProfileInputSchema` (§3) — either full profile for a logged-in user's saved profile, or an ad-hoc guest profile
- Logic: validate → strip unconsented sensitive fields → run `packages/matching` against active-status schemes only → return ranked, paginated matches
- 200 → `{ matches: EligibilityMatch[], profileCompletenessScore: number, missingFieldsAffectingResults: string[] }`
- 400 → validation errors (field-level)
- Empty result (no matches, not an error) → 200 with `{ matches: [], suggestions: string[] }` where `suggestions` lists which additional fields would most likely unlock matches (computed by checking which unanswered fields appear most often in currently-`unknown`-outcome rule evaluations across the catalog)

**`POST /api/schemes/:schemeId/explain`**
- Body: `{ matchedCriteria: MatchedCriterion[], language: "en"|"hi" }` — matchedCriteria must come from a prior `/eligibility/match` call, not be client-fabricated (validate scheme facts referenced actually belong to `:schemeId`)
- Calls `packages/ai` per §5
- 200 → `ExplainOutput`
- 503 → `{ error: "AI_UNAVAILABLE", fallback: <raw structured facts> }` (§5.5 — this is a *soft* failure, always still 200 with fallback content in practice; 503 reserved for total service outage where even the fallback can't be assembled)

**`GET /api/taxonomies`**
- 200 → `{ states: string[], occupations: string[], sectors: string[], incomeBrackets: string[], socialCategories: string[] }`
- Cacheable, changes rarely — set `Cache-Control: max-age=3600`.

**Admin-only (all require `authRequired` + `adminRequired`):**

**`POST /api/admin/schemes`** — create scheme (status defaults to `under_review`, never `active` on create)
**`PATCH /api/admin/schemes/:id`** — edit; auto-increments `version`, writes an audit log entry, does not mutate `lastVerifiedAt` unless explicitly re-verified
**`POST /api/admin/schemes/:id/verify`** — sets `lastVerifiedAt = now()`, distinct action from a content edit
**`POST /api/admin/schemes/:id/publish`** — status `under_review` → `active`; blocked (422) if `eligibility.rules` is empty (prevents an unmatchable-or-matches-everyone scheme going live)
**`GET /api/admin/pipeline/health`** — ingestion source status, queue depth, staleness metrics (feeds Freshness KPI)

### 6.4 Error Code Catalog

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Field-level input errors |
| `UNAUTHORIZED` | 401 | Missing/invalid/expired JWT on a protected route |
| `FORBIDDEN` | 403 | Valid JWT, insufficient role |
| `SCHEME_NOT_FOUND` | 404 | Invalid schemeId |
| `RATE_LIMITED` | 429 | Exceeded `RATE_LIMIT_RPM` |
| `AI_UNAVAILABLE` | 503 | Gemini unreachable and fallback assembly also failed |
| `SCHEME_UNPUBLISHABLE` | 422 | Publish attempted with empty/invalid rule set |
| `INTERNAL_ERROR` | 500 | Unhandled — always logged with `requestId`, never detailed to client |

---

## 7. Database Schema (`infra/database`) — Dialect-Safe (SQLite + Postgres)

```sql
-- Use TEXT for IDs (UUIDs as strings) to stay dialect-neutral.
-- Avoid SERIAL/AUTOINCREMENT — generate UUIDs in application code.

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    mobile_hash TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'citizen',   -- citizen | curator | admin | support
    language TEXT NOT NULL DEFAULT 'en',
    password_hash TEXT,                      -- only set for admin/curator/support accounts
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE profiles (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    state TEXT NOT NULL,
    district TEXT,
    pincode TEXT,
    age INTEGER NOT NULL,
    gender TEXT NOT NULL,
    occupation TEXT NOT NULL,
    income_bracket TEXT NOT NULL,
    social_category TEXT,
    disability_status BOOLEAN,
    marital_status TEXT,
    land_owned_hectares REAL,
    education_level TEXT,
    has_ration_card BOOLEAN,
    has_aadhaar_linked_bank BOOLEAN,
    dependents INTEGER,
    is_proxy_profile BOOLEAN NOT NULL DEFAULT FALSE,
    sensitive_fields_consented BOOLEAN NOT NULL DEFAULT FALSE,
    consented_at TEXT,
    completeness_score INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE schemes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    issuing_level TEXT NOT NULL,
    issuing_body TEXT NOT NULL,
    state TEXT,
    sector TEXT NOT NULL,
    description TEXT NOT NULL,
    eligibility_json TEXT NOT NULL,      -- serialized EligibilityRuleSet
    benefits TEXT NOT NULL,
    benefit_amount_json TEXT,
    documents_required_json TEXT,
    application_steps_json TEXT,
    application_url TEXT NOT NULL,
    application_mode TEXT NOT NULL,
    deadline TEXT,
    status TEXT NOT NULL DEFAULT 'under_review',
    source_urls_json TEXT NOT NULL,
    last_verified_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE scheme_versions (               -- audit/rollback history
    id TEXT PRIMARY KEY,
    scheme_id TEXT NOT NULL REFERENCES schemes(id),
    snapshot_json TEXT NOT NULL,
    edited_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE matches (                        -- optional persisted log, useful for the Engagement KPI
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    scheme_id TEXT NOT NULL REFERENCES schemes(id),
    confidence TEXT NOT NULL,
    score INTEGER NOT NULL,
    matched_at TEXT NOT NULL
);

CREATE TABLE saved_schemes (
    user_id TEXT NOT NULL REFERENCES users(id),
    scheme_id TEXT NOT NULL REFERENCES schemes(id),
    saved_at TEXT NOT NULL,
    PRIMARY KEY (user_id, scheme_id)
);

CREATE TABLE application_status (
    user_id TEXT NOT NULL REFERENCES users(id),
    scheme_id TEXT NOT NULL REFERENCES schemes(id),
    status TEXT NOT NULL,                     -- not_started|applying|submitted|approved|rejected|need_help
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, scheme_id)
);

CREATE TABLE feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    scheme_id TEXT REFERENCES schemes(id),
    type TEXT NOT NULL,                       -- match_feedback|report_issue|outcome
    content TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE TABLE admin_audit_log (
    id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    diff_json TEXT,
    created_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_schemes_state_sector_status ON schemes(state, sector, status);
CREATE INDEX idx_profiles_user_id ON profiles(user_id);
CREATE INDEX idx_matches_user_id ON matches(user_id);
```

Notes: `income_bracket`/`social_category`/etc. stored as free-text codes matching the taxonomy enums in §2, not foreign keys to a taxonomy table — keeps SQLite/Postgres parity simple for MVP; a real taxonomy table is a reasonable Phase 2 refactor once state-specific codes multiply.

---

## 8. Data Ingestion Contract (`data/schemes`, `data/sources`, `data/taxonomies`)

### 8.1 Assumed CSV → Domain Mapping (confirm against your real file — §1.3)

| Assumed CSV column | Maps to `Scheme` field | Notes |
|---|---|---|
| `scheme_name` | `name` | |
| `level` | `issuingLevel` | normalize to `central`/`state` |
| `department` | `issuingBody` | |
| `state` | `state` | blank/NULL if central |
| `category` | `sector` | normalize against §8.3 sector enum |
| `description` | `description` | |
| `eligibility_text` | — | **raw text only** — must go through curator review to become structured `eligibility_json`; never auto-published from free text alone (this is the single highest-risk step in the whole pipeline — a bad auto-parse here silently corrupts every downstream match) |
| `benefits` | `benefits` | |
| `documents` | `documentsRequired` | split on delimiter, trim |
| `how_to_apply` | `applicationSteps` | split into steps |
| `official_link` | `applicationUrl` + `sourceUrls[0]` | |
| `deadline` | `deadline` | parse to ISO, null if "rolling"/blank |

### 8.2 Import Script Contract (`scripts/import-schemes.ts`)

```
1. Read CSV
2. Map columns per §8.1 into a staging Scheme[] with status forced to "under_review"
3. Do NOT auto-generate eligibility_json from eligibility_text — leave eligibility.rules = []
4. Insert into `schemes` table as under_review
5. Output a report: rows imported, rows skipped (missing required field), rows needing manual eligibility-rule authoring
6. A human curator (or a guided admin-UI flow) must author eligibility_json per scheme
   before it can be published (enforced by the 422 SCHEME_UNPUBLISHABLE check in §6.3)
```
This keeps the CSV import honest: **nothing goes live with auto-guessed eligibility logic.**

### 8.3 MVP Taxonomy Defaults (`data/taxonomies`)

```json
{
  "sectors": ["agriculture","education","health","housing","pension","disability","women","employment","business","social_welfare"],
  "occupations": ["farmer","student","salaried","self_employed","unemployed","homemaker","retired","daily_wage_informal"],
  "incomeBrackets": ["below_1l","1l_3l","3l_6l","6l_10l","above_10l"],
  "socialCategories": ["general","obc","sc","st","ews"]
}
```
States list: use the standard 28 states + 8 UTs list (India), stored as a static JSON array — stable enough not to need admin-editable management in MVP.

---

## 9. Admin Bootstrap Logic

```
On first deploy / seed script run:
    if no user with role='admin' exists:
        generate a cryptographically random password (16+ chars)
        create user { email: ADMIN_BOOTSTRAP_EMAIL, role: 'admin', password_hash: hash(password), must_change_password: true }
        print password ONCE to deploy console/logs (never store plaintext, never email it in MVP)
    else:
        no-op

On admin login:
    if must_change_password == true:
        block access to all /admin/* routes except /admin/change-password
        force password change before proceeding
```

---

## 10. Web App Business Logic (`apps/web`) — Key Flow-to-Route Mapping

| Flow | Route(s) | Calls |
|---|---|---|
| Guest discovery | `/discover` | `POST /eligibility/match` (no auth), profile held in local component state only |
| Save a guest match → prompts signup | `/discover` → `/signup` | carries in-memory profile into `POST /profile` after auth completes |
| Scheme detail | `/schemes/[id]` | `GET /schemes/:id` + (if matched) `POST /schemes/:id/explain` |
| Profile edit → re-match | `/profile` | `PATCH /profile` → triggers fresh `POST /eligibility/match` client-side |
| Admin scheme review | `/admin/schemes` | `GET/POST/PATCH /admin/schemes*` |

Client-side validation always mirrors `packages/validation` schemas exactly — no duplicate, drifted validation logic in the web app.

---

## 11. Testing Checklist (`tests/`)

**Unit (`packages/matching`, highest priority — this is the trust-critical core):**
- [ ] Each operator (`eq`,`in`,`between`, etc.) — satisfied/violated/unknown cases
- [ ] AND/OR/nested-group logic combinations
- [ ] Confidence assignment boundaries (exactly 2 unknown fields = medium, 3 = low)
- [ ] Ranking order stability with tied scores
- [ ] `not_eligible` schemes never appear in default match list

**Unit (`packages/ai`):**
- [ ] Guardrail rejects an output containing a ₹ amount not in source facts
- [ ] Guardrail rejects an output containing a URL not in `sourceUrls`
- [ ] Fallback path returns valid structured content when Gemini times out

**Integration (`apps/api`):**
- [ ] `/eligibility/match` strips unconsented sensitive fields server-side even if client sends them
- [ ] `/admin/schemes/:id/publish` returns 422 on empty rule set
- [ ] Rate limiter returns 429 after threshold on `/eligibility/match`

**E2E (`tests/e2e`) — citizen journeys:**
- [ ] Guest → match → signup → profile persisted → matches reappear post-login
- [ ] Zero-match profile → suggestions returned, not an empty dead-end
- [ ] Explain-a-match → contains disclaimer, source link, no fabricated amount
- [ ] Admin: import CSV → schemes land as `under_review` → cannot publish without eligibility rules → author rules → publish → now visible to matching

---

## 12. Build Order for the MVP

1. `packages/domain` + `packages/validation` (contracts first — nothing else compiles without these)
2. `infra/database` schema + migrations (both dialects)
3. `packages/matching` (pure logic, fully unit-testable before any API exists)
4. `apps/api`: repositories → services → controllers → routes for `/schemes`, `/taxonomies`, `/eligibility/match` (no AI, no auth yet — get deterministic matching working end-to-end first)
5. Auth + JWT + admin bootstrap (§6.2, §9)
6. `apps/api`: `/admin/schemes*` CRUD + publish-gate
7. `scripts/import-schemes.ts` against your real CSV (once §1.3 is confirmed)
8. `packages/ai` + `/schemes/:id/explain` (deliberately last — the product must work correctly *without* AI before AI is layered on for phrasing, per the grounding contract in §5.1)
9. `apps/web`: discovery/guest flow → signup/login → profile → dashboard → admin panel
10. E2E tests from §11 as a final gate before calling MVP done

---

*This spec is intentionally strict about what's deterministic (matching) vs. what's AI-assisted (phrasing only) — that boundary is the main bug-prevention mechanism for an AI coding agent building this: if a change ever requires the matching engine to call Gemini, or the AI layer to decide eligibility, something has gone wrong relative to this design.*
