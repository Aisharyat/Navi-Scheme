# Navi Scheme — Business Logic & Product Specification
### (Business Analyst Document — MVP through Phase 4)

---

## 0. Purpose of This Document

This document translates the Navi Scheme idea and phased plan into concrete, buildable logic: every screen, every flow (positive and negative), the complete behavior contract for the AI agent, and the admin system that keeps the whole thing trustworthy. It is written so an engineering team could pick it up and start building the MVP (Phase 1) without needing to re-derive product decisions.

Guiding principle throughout: **trust is the product**. A citizen acts on this information — misses a deadline, submits wrong documents, or gives up because of a wrong scheme match — for real. Every flow below is designed around "what happens when this goes wrong," not just the happy path.

---

## 1. Personas

| Persona | Profile | Core need | Constraint |
|---|---|---|---|
| Rural applicant | Farmer/laborer, basic smartphone, regional language, low data | "Am I eligible for anything I don't know about?" | Low literacy with English/forms, intermittent connectivity |
| Urban lower-income | Gig worker/small trader, decent smartphone use | "Which specific scheme fits my situation, and how do I apply without getting scammed by agents?" | Distrust of official portals, time-poor |
| Student | 16–25, applying for scholarships | "What am I eligible for this academic year, and when's the deadline?" | Deadline-sensitive, exam-cycle bound |
| Elderly/pension seeker | 60+, often assisted by a family member | Pension, health scheme eligibility | May not operate the device themselves — flows must work "on behalf of" |
| Caregiver/family member | Adult child managing parent's or relative's benefits | Manage multiple profiles | Needs multi-profile support |
| Government/NGO field worker | Uses the tool to help many citizens | Fast bulk lookups, no login friction | Needs a "quick check" mode without full onboarding |
| Admin/Scheme Curator | Internal ops team | Keep the catalog accurate and current | Needs to move fast without breaking trust |

---

## 2. Information Architecture (Sitemap)

```
/ (Landing — pre-login)
 ├─ /try (Guest chat — no login)
 ├─ /schemes (Public browsable catalog, SEO-friendly)
 │    └─ /schemes/:id (Public scheme detail page)
 ├─ /login
 ├─ /signup
 ├─ /forgot-password
 │
 ├─ /app (post-login shell)
 │    ├─ /app/dashboard
 │    ├─ /app/chat  (core AI conversation)
 │    ├─ /app/matches (ranked scheme list)
 │    ├─ /app/matches/:id (personalized scheme detail — eligibility explained against THIS profile)
 │    ├─ /app/saved
 │    ├─ /app/tracker (self-reported application status)
 │    ├─ /app/notifications
 │    ├─ /app/profile
 │    ├─ /app/profile/family (multi-profile / dependents)
 │    ├─ /app/settings (language, channel prefs, privacy, delete data)
 │    └─ /app/help
 │
 └─ /admin
      ├─ /admin/dashboard (KPIs: coverage, accuracy, engagement, freshness)
      ├─ /admin/schemes (CMS + ingestion queue)
      ├─ /admin/schemes/:id/versions
      ├─ /admin/pipeline (ingestion health)
      ├─ /admin/rules (eligibility rule builder)
      ├─ /admin/users
      ├─ /admin/support-queue
      ├─ /admin/flagged-responses (AI QA)
      └─ /admin/audit-log
```

---

## 3. Pre-Login Experience

### 3.1 Landing Page (Dashboard Before Login)

**Purpose:** convert a skeptical, possibly low-trust visitor into either a guest-chat user or a signup, within seconds — no jargon, no wall of text.

**Sections:**
1. Hero: single input box — *"Tell me a bit about yourself — I'll find schemes you may be eligible for."* (this doubles as the guest-chat entry point)
2. Trust markers: "X schemes tracked", "Sourced only from official government portals", "No fees, no middlemen" — directly counters the #1 fear (scam agents)
3. Quick category tiles (Farmer, Student, Woman, Senior Citizen, Person with Disability, Business Owner) — one-tap into guest chat with a pre-filled intent
4. Language selector, prominent, top of page (not buried in settings)
5. "How it works" — 3-step visual: Tell us about you → Get matched schemes with sources → Apply with step-by-step help
6. Footer: About, Data & Privacy policy, Contact/Grievance, list of official data sources used

### 3.2 Guest Chat (Try Before Signup)

- Fully functional matching conversation without an account.
- **Limit:** guest sessions get a capped number of matches shown in full detail (e.g., top 3) and a soft paywall-free nudge: *"Create a free account to save these matches and get notified when new schemes launch for you."*
- Guest session data is held in-browser/session only; nothing is persisted server-side against an identity until the user signs up (privacy-by-default).
- **Negative flow:** guest tries to bookmark/track → prompted to sign up, with the in-progress profile carried over into the signup flow (no re-entry of data).

### 3.3 Sign-Up Flow

**Trigger:** "Save my matches" / "Get notified" / direct signup click.

**Steps:**
1. Enter mobile number (India-first: mobile number is the primary identifier, not email)
2. OTP sent via SMS
3. Enter OTP → verified → basic profile carried over from guest session (if any) → land on `/app/dashboard`

**Positive path:** OTP correct within time window → account created → welcome micro-onboarding (2–3 optional profile questions to sharpen matches).

**Negative flows:**
| Case | System response |
|---|---|
| Invalid mobile number format | Inline validation before OTP send attempt |
| OTP not received | "Resend OTP" after 30s cooldown; fallback to voice-call OTP after 2 failed SMS attempts |
| Wrong OTP entered | Clear error, 3 attempts before temporary lockout (5 min) — anti-brute-force |
| Number already registered | Redirect to login with message, offer "forgot access" |
| User abandons mid-OTP | Guest session data preserved for the browser session so they can resume without retyping |

### 3.4 Login Flow

- Primary: mobile number + OTP (matches how most citizens already use government/UPI apps — familiar pattern, lowers friction).
- Optional secondary: email + password for users who prefer it (e.g., field workers logging in on shared devices infrequently).

**Negative flows:** unregistered number → prompt to sign up instead of a dead-end error; repeated OTP failures → temporary lock + support link; device/browser change → normal OTP re-verification, no extra friction (avoid over-engineering security at the cost of accessibility for this audience).

---

## 4. Onboarding / Profile Building

Two parallel intake modes feed the **same underlying profile schema** — the user picks whichever they're comfortable with:

- **Mode A — Conversational:** the AI asks for details naturally inside the chat, one or two questions at a time, and builds the structured profile silently in the background as it goes.
- **Mode B — Structured form:** a short form (for users who prefer speed over conversation, or for field workers entering data on someone's behalf).

### 4.1 Core Profile Fields

**Required for baseline matching:**
- Location: state → district (pin code optional, sharpens local/state scheme matches)
- Age
- Gender
- Occupation category (farmer, student, salaried, self-employed/business, unemployed, homemaker, retired, daily wage/informal)
- Approximate annual household income bracket (ranges, not exact figures — reduces sensitivity and abandonment)
- Social category (General/OBC/SC/ST/EWS — optional but unlocks category-specific schemes; **explicitly optional with a "why we ask" tooltip**)

**Optional, unlocks more precise matches:**
- Marital status (maternity/family schemes)
- Disability status (disability-specific schemes)
- Land ownership (agricultural schemes)
- Existing ration card / BPL card status
- Bank account + Aadhaar-linked status (many schemes require this — asked as yes/no, never the actual numbers)
- Education level (scholarship schemes)
- Family size/dependents

**Never collected:** Aadhaar number, bank account number, exact income figures, any document uploads in Phase 1. The MVP matches and *guides*; it does not custody sensitive identity documents.

### 4.2 Validation & Negative Cases

| Case | Handling |
|---|---|
| User skips required field | AI proceeds with best-effort matching, clearly labels results as "broader matches — answer a couple more questions for a sharper list" |
| Contradictory answers (e.g., age 15 + occupation "retired") | AI asks a gentle clarifying follow-up rather than silently accepting or rejecting |
| User gives a vague answer ("I earn okay") | AI offers income brackets as tappable choices instead of demanding a number |
| User is filling this out for someone else (e.g., illiterate parent) | Explicit "I'm filling this for someone else" toggle at profile start — changes address terms from "you" to "they" throughout the AI's language |
| Location can't be determined | AI defaults to central/national schemes only, prompts for state before showing state schemes |

### 4.3 Consent & Privacy

- One clear consent screen before any sensitive-category field (income, social category, disability) is asked, explaining: *what it's used for (matching only), how long it's kept, and that it's never sold or shared.*
- A visible, single-tap "Delete my data" option exists from day one (builds trust, and aligns with India's DPDP Act expectations even at MVP stage).
- No dark patterns: skipping optional/sensitive fields must never block core functionality.

---

## 5. Post-Login Dashboard

**Purpose:** an at-a-glance home base — not a data-entry chore, not a wall of scheme cards.

### 5.1 Dashboard Layout
1. **Top strip:** greeting + profile completeness meter ("Your profile is 60% complete — answer 2 more questions to unlock 4 more schemes")
2. **Primary CTA:** "Continue conversation" / "Ask something new" — the chat is always one tap away, never buried
3. **Your top matches** (3–5 cards): scheme name, one-line benefit, eligibility confidence badge (see §6.4), "Apply" / "View details"
4. **Deadlines coming up** (if any matched scheme has a closing date)
5. **Notifications preview** (new/changed schemes since last visit)
6. **Saved schemes** shortcut
7. **Application tracker** shortcut (self-reported progress)

### 5.2 Matched Schemes Section (`/app/matches`)
- Full ranked list, filterable by category (Central/State, sector: agriculture/education/health/housing/pension/etc.)
- Each card shows: match confidence, why matched (top 2 matching criteria in plain language), source citation, last-verified date

### 5.3 Saved/Bookmarked Schemes
- User can save schemes they're not ready to apply for yet; these get priority in the notification engine if terms change.

### 5.4 Application Tracker
- **Self-reported** (MVP has no live government API integration — that's Phase 4). States: *Not started → Applying → Submitted → Approved → Rejected → Need help.*
- If "Rejected" or "Need help" is selected, AI proactively offers to troubleshoot (common rejection reasons for that scheme, sourced from the scheme's known documentation).

### 5.5 Notifications Center
- New scheme launched matching profile; existing matched scheme changed (eligibility, deadline, benefit amount); deadline reminders; profile-completion nudges.

### 5.6 Profile & Settings
- Edit profile (triggers re-matching), manage dependents/family profiles, language, notification channel preferences, delete account/data.

---

## 6. Core Conversational Flow (The AI Agent)

### 6.1 Entry Points
- New guest visit ("Tell me about yourself")
- Logged-in "Ask something new" from dashboard
- Deep-link from a notification ("A new scheme for farmers in Maharashtra just launched — want to check?")
- Category tile tap (pre-fills intent, e.g., "I'm a student")

### 6.2 Turn-by-Turn Flow

1. **Greeting + intent capture** — open-ended: "Tell me a bit about your situation, or tap a category to start."
2. **Profile gap-filling** — AI checks what it already knows (from account) vs. what's missing for a *meaningful* first match; asks only what's needed, 1–2 questions per turn, never a long form disguised as chat.
3. **Preliminary match pass** — as soon as enough signal exists (location + one more field), AI can surface a *provisional* short list, clearly labeled "based on what you've told me so far."
4. **Refinement** — AI asks targeted follow-ups only where they would change the result set (e.g., only asks about land ownership if agricultural schemes are in play).
5. **Final ranked list with explanation** — see §6.5 for response composition rules.
6. **Next-step guidance** — for each scheme the user shows interest in: required documents, where to apply (official portal/office), estimated processing time, common pitfalls — all sourced, not invented.
7. **Follow-up loop** — user can ask "what about my mother?" (triggers dependent-profile flow), "why not X scheme?" (triggers explainability, §6.6), or just end the session (state persists for next login).

### 6.3 Clarifying Question Logic

- Never ask more than 2 questions per turn.
- Always explain *why* a question is being asked if it's sensitive ("This helps me check category-reserved schemes — totally optional").
- If the user refuses to answer, proceed and clearly mark results as incomplete rather than blocking.

### 6.4 Matching & Ranking Logic

Each scheme in the catalog has structured, machine-readable eligibility rules (built by admins/curators, §11.5) — e.g.:
```
state IN [Maharashtra] AND occupation = farmer AND land_owned <= 2_hectares AND category != none-required
```
Matching engine evaluates the citizen profile against these rules and returns one of:
- **Eligible (high confidence)** — all required fields present and satisfied
- **Likely eligible (medium confidence)** — satisfied on known fields, but 1+ required field is unanswered
- **Possibly eligible (low confidence)** — partial match, several unknowns
- **Not eligible** — a hard-fail criterion is violated (never shown in main list, but explainable if asked "why not")

Ranking order: confidence level first, then benefit relevance/value, then deadline proximity.

**Critical rule: the AI never invents eligibility criteria.** If a rule field isn't in the structured catalog, the AI says so and links to the official source rather than guessing.

### 6.5 Response Composition Rules

Every scheme surfaced to a user must include:
1. Plain-language name and one-line "what you get"
2. Why it matched *this* profile (the specific 2–3 criteria)
3. Confidence label
4. Source citation (official portal/notification, with last-verified date from the catalog)
5. Next step (how to apply / where)

The AI must **never**:
- Quote or reproduce large blocks of official notification text — paraphrase in plain language
- Promise a benefit amount as guaranteed (funds/quotas can run out) — phrase as "as per the scheme, eligible applicants receive ~₹X"
- Fabricate a deadline it isn't sure of
- Claim to submit an application on the citizen's behalf (Phase 1–3 has no submission integration)

### 6.6 Negative / Edge Scenarios

| Scenario | Agent behavior |
|---|---|
| No schemes match at all | Say so plainly; suggest which extra profile info might unlock matches; suggest nearest matched-adjacent schemes ("not quite eligible, but close — here's what's missing") |
| Ambiguous/contradictory profile | Ask a clarifying question instead of picking an interpretation silently |
| Off-topic query (weather, general chit-chat) | Gently redirect: "I'm focused on government scheme guidance — happy to help once we're back on that" |
| Harmful/manipulative query (e.g., "help me fake my income bracket to qualify") | Decline, explain that misrepresentation can lead to rejection/penalties, offer to check genuine eligibility instead |
| User asks about a scheme not in the catalog | Say it's not yet tracked rather than guessing; log the gap for the admin ingestion queue |
| User asks "why wasn't I matched to X" | Full explainability: show which specific criterion failed |
| Scheme data is stale (past last-verified threshold) | Flag visibly: "Last verified on [date] — details may have changed, check the official source" |
| Multiple conflicting profiles in one household session | AI asks whose situation is being discussed and keeps threads separate |
| Regional language / code-mixed input (Hinglish, Marathi-English mix) | AI detects and responds in kind; never forces a language switch |
| Low-literacy user struggling with text | Offer shorter, simpler phrasing on request ("explain like I'm new to this") |
| Suspected scam-agent exploitation risk | If user mentions paying someone to apply, proactively warn that legitimate government schemes never require payment to apply |

### 6.7 Escalation & Handoff

- If the AI cannot resolve a query after 2 clarification attempts, or the user explicitly asks for a human, it offers: link to official helpline for that specific scheme/department, or (Phase 2+) a "raise a support ticket" option routed to `/admin/support-queue`.

---

## 7. Scheme Detail Page Flow (Personalized)

`/app/matches/:id` — shown *in context of the logged-in user's own profile*, not generic:

- Header: scheme name, issuing body (Central/State + department), benefit summary
- "Why you're matched" panel (criteria comparison, profile field vs. requirement, tick/cross)
- Full eligibility criteria (plain language, sourced)
- Required documents checklist (user can tick off what they already have)
- Step-by-step application guide (portal link, office address if offline-only, helpline)
- Deadline (if any) with countdown
- "Mark as Applied" → feeds the Application Tracker
- "Report an issue" (wrong info, broken link, outdated) → feeds admin QA queue
- Source + last-verified date, always visible, never hidden behind a tooltip

---

## 8. Notification & Freshness Engine

### 8.1 Triggers
- New scheme published matching a user's saved profile
- Existing matched/saved scheme's terms changed (amount, eligibility, deadline)
- Deadline approaching (7-day / 1-day reminder) for a saved or applied scheme
- Profile-completion nudge if match quality is capped by missing data

### 8.2 Channels
- Phase 1: in-app + web push
- Phase 2: WhatsApp (primary channel for this audience — no app install needed), SMS fallback for feature phones

### 8.3 Negative Flows
- User opts out of notifications entirely → deadline reminders for *already-saved* schemes still degrade gracefully to in-app-only, not fully silenced without an explicit second confirmation (avoid the user silently missing a deadline they cared about)
- Notification about a scheme that later turns out to be a data error → immediate correction push with clear "we made an error, here's the correction" — transparency over silence

---

## 9. Feedback & Trust Loop

Three lightweight feedback surfaces feed the accuracy KPI directly:

1. **Per-match feedback:** thumbs up/down + optional reason on any scheme match ("not actually eligible", "I already knew this", "info was wrong")
2. **Report an issue:** on any scheme detail page — routes to admin QA queue with the scheme ID and the specific field disputed
3. **Application outcome self-report:** did applying actually work? This is the closest proxy to real-world impact and directly informs the "schemes matched vs. applications self-reported" success metric.

---

## 10. AI Agent — Complete Behavior Specification

### 10.1 Grounding Principle
The agent **only reasons over the verified, structured scheme catalog** (retrieval-augmented, not open-web generation) for anything factual about eligibility, benefits, deadlines, or process. General conversational ability (understanding the user, asking clarifiers, empathetic phrasing) can be more flexible; **facts about schemes cannot.**

### 10.2 System Prompt Pillars
1. You are a neutral, factual navigator of government welfare schemes — not a government representative, not a legal/financial advisor.
2. Every factual claim about a scheme must trace to the structured catalog; if it's not there, say so — never fill gaps with plausible-sounding guesses.
3. Speak in plain, warm, respectful language — no bureaucratic jargon, no condescension.
4. Default to the user's chosen language/register; mirror code-mixed input naturally.
5. Ask minimally, only what changes the outcome.
6. Never request documents/IDs/OTPs/bank details inside chat — redirect to the official portal for any actual submission.
7. Flag uncertainty and staleness honestly rather than projecting false confidence.

### 10.3 Persona & Tone
Helpful local guide, not a call-center script — patient, non-judgmental about income/category disclosures, encouraging without being falsely optimistic about outcomes.

### 10.4 Language & Locale
MVP: Hindi + English + at least 1–2 major regional languages tied to pilot states, with a clear roadmap to expand per Phase 2 rollout regions.

### 10.5 Guardrails
- No legal or financial advice beyond what the scheme documentation states
- No fabricated deadlines, amounts, or contact numbers
- No impersonation of any government body or official
- No processing of payments, ever
- No collection of Aadhaar/bank numbers or document uploads in Phase 1–2
- Refuses requests to help falsify eligibility information, explains why

### 10.6 Memory Scope
- Within a session: full conversational context.
- Across sessions (logged-in users): structured profile + past matches + saved/tracked schemes. Guest sessions: no persistence beyond the browser session.

### 10.7 Sensitive Field Handling
Income bracket, social category, disability status: collected only after explicit inline consent, used exclusively for matching logic, never surfaced to any other user, never used for anything beyond eligibility computation, deletable on request at any time.

### 10.8 Failure Modes & Fallbacks
- Catalog has no data for the user's state → says so, shows central schemes only, logs the gap for admin follow-up
- Model is uncertain about a rule interpretation → asks the user or defers to "check the official source" rather than resolving ambiguity silently
- Backend/matching service down → chat degrades to "I'm having trouble matching right now, try again shortly" rather than hallucinating an answer

---

## 11. Admin Portal — Complete Specification

### 11.1 Roles

| Role | Access |
|---|---|
| Super Admin | Full access, user management, role assignment |
| Scheme Curator | Review/approve ingested schemes, edit scheme records, manage eligibility rules |
| Data Ops (Pipeline Monitor) | Monitors ingestion pipeline health, source reliability, failed scrapes |
| Support Agent | Handles escalated user queries and reported issues |
| Analyst | Read-only access to KPI dashboards |

### 11.2 Scheme Ingestion & Curation Workflow

```
[Automated ingestion from official sources]
        ↓
   Staging queue (raw extracted data, unverified)
        ↓
[Curator review]  → duplicate check against existing catalog
        ↓                    ↓
   Approve & structure   Reject / merge / flag for manual research
        ↓
[Eligibility rule builder] (structured, testable rules attached)
        ↓
   Publish → live in matching engine + versioned
        ↓
[Scheduled re-verification] (periodic re-check against source; flags if source page changed)
```

Sources for MVP (Phase 1): a curated, deliberately limited set of official portals + synthetic/sample data for demo/testing, expanding to a broader automated pipeline in Phase 2 per the plan.

### 11.3 Scheme CMS Fields
Name, issuing body (Central/State/Department), sector/category, description (plain language, curator-written, not copy-pasted), full eligibility rule set (structured, see §6.4 syntax), benefit details, required documents, application process steps, official source URL(s), deadline (if any), status (Active/Upcoming/Closed/Under Review), last-verified date, version history.

### 11.4 Pipeline Health Dashboard
Sources monitored, last successful pull per source, failed/broken source pages, schemes pending review (queue depth + age), average time from detection → publish (this feeds the **Freshness** KPI directly).

### 11.5 Eligibility Rule Builder
A no-code/low-code rule editor (field, operator, value; AND/OR groups) so curators — not engineers — can encode and test eligibility logic, with a "test against sample profile" tool before publishing (prevents rule bugs from reaching citizens).

### 11.6 Analytics Dashboard (mapped to stated KPIs)
- **Coverage:** schemes catalogued (by state/sector), states with "meaningful coverage" (defined threshold, e.g. >X schemes catalogued)
- **Accuracy:** % of matches with positive feedback, open "report an issue" tickets, resolution time
- **Engagement:** query volume, repeat-usage rate, matched-vs-self-reported-applied gap
- **Freshness:** average lag between scheme going live/changing and catalog reflecting it

### 11.7 User Management & Support Queue
View (aggregated, privacy-respecting) user segments for coverage planning; handle escalated chat sessions and "report an issue" tickets with SLA tracking.

### 11.8 Audit Log & Compliance
Every scheme edit, rule change, and publish action logged with curator identity + timestamp (accountability for factual accuracy — critical given real-world stakes).

### 11.9 Admin Negative/Error Flows
| Case | Handling |
|---|---|
| Duplicate scheme detected from two sources | Merge workflow, curator picks canonical source |
| Two official sources conflict on a detail | Flagged for manual research, scheme marked "under review" (not shown to users) until resolved |
| Source site down/unreachable | Pipeline dashboard flags it; last-known-good data stays live but marked with an older "last verified" date, never silently dropped |
| Rule builder logic error (e.g., contradictory AND conditions making a scheme unmatchable) | Test-against-sample-profile step catches this before publish |
| Curator publishes incorrect data | Version history allows instant rollback; "report an issue" from users acts as a second safety net |

---

## 12. Data Model (Core Entities)

- **User**: id, mobile (hashed), auth state, language pref, notification prefs, created_at
- **Profile**: user_id, location, age, gender, occupation, income_bracket, category, disability_status, dependents[], consent_flags{}
- **Scheme**: id, name, issuing_body, sector, description, eligibility_rules (structured), benefits, documents_required[], application_steps[], source_url, deadline, status, last_verified_at, version
- **Match**: user_id, scheme_id, confidence_level, matched_criteria[], matched_at
- **SavedScheme**: user_id, scheme_id, saved_at
- **ApplicationStatus** (self-reported): user_id, scheme_id, status_enum, updated_at
- **Feedback**: user_id, scheme_id, type (match-feedback/report-issue/outcome), content, status, created_at
- **Notification**: user_id, scheme_id, trigger_type, channel, sent_at, read_at
- **AdminAuditLog**: admin_id, action, entity_type, entity_id, before/after diff, timestamp

---

## 13. Non-Functional Requirements

- **Privacy/security:** DPDP-Act-aligned consent flows, encryption at rest for profile data, no sensitive documents stored, hashed mobile numbers, explicit data-deletion path
- **Accessibility:** works on low-end Android devices, low-bandwidth/text-only fallback mode, large-tap-target UI, screen-reader friendly
- **Multilingual:** UI + AI responses in local languages, not just translated labels
- **Performance:** initial match response within a few seconds even on 3G
- **Reliability:** matching engine gracefully degrades (never hallucinates) if catalog/backend service is unavailable
- **Scalability:** ingestion pipeline and catalog architecture designed to grow from a handful of pilot states to nationwide coverage without a redesign

---

## 14. MVP Scope (Phase 1) — In vs. Out

**In scope:**
- Web conversational interface (guest + logged-in)
- Structured scheme catalog: curated set (synthetic + a limited set of real public schemes across a pilot state or two, plus major central schemes)
- Full eligibility matching + explainability + citation
- Dashboard (pre- and post-login), profile management, saved schemes, self-reported tracker
- Basic admin CMS + rule builder + manual curation workflow
- Feedback loop (thumbs up/down, report issue)

**Explicitly out of scope for MVP (deferred to later phases per the plan):**
- WhatsApp bot (Phase 2)
- Automated/continuous ingestion pipeline at scale (Phase 2)
- Proactive notifications (Phase 2)
- Non-scheme civic domains — electricity/water/healthcare (Phase 3)
- Direct government portal/API integration for applications and grievances (Phase 4, partnership-dependent)

---

## 15. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| AI hallucinates eligibility criteria | Citizen wrongly believes they qualify, wastes time/hope | Strict RAG-over-verified-catalog only; never free-generate facts |
| Stale scheme data | Citizen applies to a closed/changed scheme | Visible last-verified date, scheduled re-verification, freshness KPI tracked |
| Sensitive data mishandling (income, category, disability) | Trust breach, legal exposure | Explicit consent, minimal necessary collection, easy deletion |
| Scam agents impersonating the platform | Financial harm to citizens | Repeated in-product messaging: "applying is always free," proactive warning if user mentions paying someone |
| Low adoption in the least-connected communities (the group who needs it most) | Core mission failure | Phase 2 WhatsApp channel + low-bandwidth mode explicitly designed for this |
| Curator backlog causing stale/incomplete catalog | Coverage KPI stalls | Pipeline health dashboard + queue-age alerts |

---

## 16. Success Metrics — Instrumentation

| KPI | How it's measured |
|---|---|
| Coverage | Count of active schemes in catalog by state/sector; count of states above meaningful-coverage threshold |
| Accuracy | % positive match feedback; volume/resolution time of "report an issue" tickets |
| Engagement | Query volume, repeat session rate, ratio of "applications self-reported" to "schemes matched" |
| Freshness | Avg. time between scheme live/change and catalog reflecting it (pipeline dashboard) |

---

*End of document. This spec is intended to evolve — as Phase 1 ships and real user feedback comes in, the flows above (especially §6 conversational edge cases and §11 curation workflow) should be revisited first, since they carry the most trust risk.*
