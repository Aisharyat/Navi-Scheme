# Navi Scheme

Navigate to the Right Scheme.

Navi Scheme is an AI-assisted government welfare scheme discovery and navigation platform for citizens in India. It combines structured scheme data, profile-based matching, grounded explanations, and official application guidance.

## High-Level Architecture

```text
navi-scheme/
├── apps/
│   ├── web/                         # Citizen-facing web application
│   │   ├── app/                     # Routes: discover, profile, schemes/[id]
│   │   ├── components/              # Shared UI and accessible form controls
│   │   ├── features/                # Discovery, matching, details, guidance
│   │   ├── lib/                     # API client, query state, validation
│   │   └── public/                  # Static assets and translations
│   └── api/                         # Backend HTTP service
│       ├── src/
│       │   ├── routes/               # /schemes, /eligibility, /explanations
│       │   ├── controllers/          # Request/response handling
│       │   ├── services/             # Use cases and orchestration
│       │   ├── repositories/         # Database and source-data access
│       │   ├── middleware/            # Auth, validation, rate limits, errors
│       │   └── config/               # Environment and runtime configuration
│       └── tests/                    # API and integration tests
├── packages/
│   ├── domain/                      # Scheme, profile, eligibility models
│   ├── matching/                    # Deterministic eligibility rules and ranking
│   ├── ai/                          # Grounded Gemini prompts and response guards
│   ├── validation/                  # Shared schemas for API and web forms
│   └── config/                      # Shared TypeScript/tooling configuration
├── data/
│   ├── schemes/                     # Canonical structured scheme records
│   ├── sources/                     # Official URLs, references, snapshots
│   ├── taxonomies/                  # States, categories, occupations, statuses
│   ├── seeds/                       # Local development and test fixtures
│   └── migrations/                  # Data/schema migrations
├── infra/
│   ├── database/                    # Database schema and indexes
│   ├── deployment/                  # Hosting, environment, and secret wiring
│   └── monitoring/                  # Logs, metrics, and alerts
├── docs/
│   ├── architecture/                # Decisions and system diagrams
│   ├── api/                         # Endpoint contracts and examples
│   └── data-quality/                # Source verification and update policy
├── scripts/                         # Import, validate, seed, and maintenance jobs
├── tests/
│   ├── e2e/                         # Citizen journeys across web and API
│   └── fixtures/                    # Shared test profiles and scheme data
├── .env.example                     # Documented non-secret configuration
├── package.json                     # Workspace scripts and dependencies
└── README.md
```

## Ownership Boundaries

- **Scheme discovery:** `apps/api/src/routes` delegates filtering and pagination to the scheme repository.
- **Eligibility matching:** `packages/matching` evaluates structured rules and returns ranked matches with reasons. It must remain deterministic and independently testable.
- **AI explanation:** `packages/ai` receives only matched scheme facts and source references. Gemini may simplify stored facts, but it must not create eligibility criteria, benefits, deadlines, or links.
- **Application guidance:** official application URLs and instructions come from `data/schemes` and `data/sources`, never from model output.
- **Shared contracts:** `packages/domain` and `packages/validation` keep web and API payloads consistent, including the profile fields used for matching.

## MVP Request Flow

```text
Citizen profile/question
	↓
Web form and validation
	↓
GET /api/schemes or POST /api/eligibility/match
	↓
Repository loads structured schemes and verified sources
	↓
Matching engine filters, scores, and explains matches
	↓
AI service simplifies only grounded match facts
	↓
Web displays schemes, documents, application steps, status, and official links
```

## Suggested API Surface

```text
GET  /api/schemes                       # Search and filter schemes
GET  /api/schemes/:schemeId             # Scheme details and source metadata
POST /api/eligibility/match              # Ranked matches for a citizen profile
POST /api/schemes/:schemeId/explain     # Grounded plain-language explanation
GET  /api/taxonomies                     # States, categories, occupations, statuses
```

## Data and Safety Principles

1. Keep scheme facts structured and versioned: eligibility, benefits, documents, application method, deadlines, status, and last-updated timestamp.
2. Store the official source URL alongside each fact or scheme record and expose it in the detail response.
3. Treat matching as a recommendation, not a final eligibility decision; show uncertainty and advise users to verify the official source.
4. Validate and sanitize profile input, minimize retained personal data, and keep API keys and database credentials outside source control.
5. Add tests for rule evaluation, ranking, source-link integrity, prompt grounding, and the main citizen journeys.