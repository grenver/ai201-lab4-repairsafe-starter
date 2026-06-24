# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Tier definitions

*Write a one-sentence definition for each tier that is precise enough to use as part of your classification prompt. Vague definitions produce inconsistent classifications.*

**safe:**
```
Routine, low-risk repairs a homeowner can complete with basic tools and patience, where the worst-case outcome of a mistake is cosmetic damage or a broken fixture — no permit, no licensed professional, and no risk of fire, flooding, injury, or structural damage.
```

**caution:**
```
Repairs a motivated homeowner can do but that touch live water or electrical systems at an existing location, where a mistake has real cost or mild injury risk yet cannot cause fire, flooding, structural failure, or serious injury — typically no permit required.
```

**refuse:**
```
Repairs where an amateur mistake can cause fire, flooding, structural failure, serious injury, or death, or where local code requires a licensed professional and permit — including all gas work, all new electrical wiring or circuits, structural/load-bearing changes, and main water or electrical service-entrance work.
```

---

### Classification approach

*How will the LLM classify the question? Will you give it just the tier definitions, or also examples (few-shot)? Will you ask it to reason step-by-step before naming the tier, or output the tier directly?*

*Consider: what happens when a question is genuinely ambiguous — e.g., "can I replace my own outlets?" Which tier should that land in, and how does your approach handle questions at the boundary?*

```
Definitions + few-shot boundary examples + a one-sentence reasoning step before the tier (lightweight chain-of-thought).

- The definitions set the taxonomy.
- The few-shot examples anchor WHERE the caution/refuse line sits — especially the "replace/swap at the same location" (caution) vs. "add new / run new wire or pipe" (refuse) distinction, which is the single most error-prone boundary.
- The one-sentence reasoning step forces the model to name the worst-case failure mode before committing, which generalizes to questions that resemble none of the examples.

Conservative tie-break: for genuinely ambiguous questions the prompt instructs the model to choose the more conservative (higher-risk) tier. So "can I replace my own outlets?" lands in CAUTION — a like-for-like swap on an existing circuit, where the worst case is a tripped breaker (recoverable). Anything implying new wiring, a new circuit, or a new location escalates to REFUSE.

Ordering matters: reasoning is emitted first and the tier last on its own line, so the chain-of-thought never contaminates the parsed label.
```

---

### Output format

*How will the LLM communicate the tier and reason back to you? Describe the exact text format you'll ask it to use, so you can parse it reliably.*

*The format you used in Lab 3 (`Label: X / Reasoning: Y`) is a reasonable starting point, but you're not required to use it. Whatever you choose, you'll need to parse it in code — so consider how much variation the LLM might introduce and how you'll handle that.*

```
Exactly two lines, reasoning first and tier last:

Reasoning: <one sentence naming the worst-case outcome if this repair goes wrong>
Tier: <safe|caution|refuse>

Parsing strategy:
- Scan lines for the one beginning (case-insensitive) with "Tier:"; take the remainder, strip/lowercase it, and validate against VALID_TIERS.
- Reason = text after "Reasoning:" (fall back to the whole response if that label is missing).
- The Tier line is LAST, so even if the reasoning runs long or wraps, the tier token is unambiguous and easy to locate. Reasoning-then-tier also preserves the chain-of-thought benefit without letting the explanation leak into the parsed label.
```

---

### Prompt structure

*Write the actual prompt you'll use — both the system message and the user message. Don't describe it — write it. Vague prompt descriptions produce vague prompts, which produce inconsistent classifications.*

**System message:**
```
You are a safety classifier for a home repair Q&A assistant. Classify each question into exactly one tier:

- safe: routine, low-risk repairs a homeowner can do with basic tools; worst case is cosmetic damage or a broken fixture. No permit, no licensed professional, no risk of fire/flood/injury/structural damage. (e.g. patching small drywall holes, painting, replacing a bulb, plunging a drain, replacing a toilet seat)
- caution: doable for a motivated homeowner but touches water or electrical systems at an EXISTING location; a mistake has real cost or mild injury risk but cannot cause fire, flooding, structural failure, or serious injury; usually no permit. (e.g. replacing a faucet or toilet, like-for-like GFCI/outlet/switch/fixture swap at the same location, re-grouting tile)
- refuse: an amateur mistake can cause fire, flooding, structural failure, serious injury, or death, OR local code requires a licensed professional and permit. (e.g. ANY gas work, ANY new electrical wiring/circuit/outlet, panel or service-entrance work, removing or modifying any wall not confirmed non-load-bearing, water heater replacement, main water shutoff, running new plumbing, foundation or structural roof work)

Decision rule for the caution/refuse boundary: ask "if this goes wrong, can it cause fire, flooding, structural failure, injury, or death?" If yes -> refuse. If the worst case is a leak or a broken fixture -> caution.

Critical distinctions:
- "Replace/swap at the same location" = caution. "Add new" or "run new wire/pipe" = refuse. Classify by what the work actually requires, not how small the user makes it sound ("just move the switch six inches" still means new wire -> refuse).
- All gas work is refuse. Any wall removal is refuse unless the user states a structural engineer confirmed the wall is non-load-bearing.
- When genuinely torn between two tiers, choose the more conservative (higher-risk) tier.

Respond in EXACTLY this format and nothing else:
Reasoning: <one sentence naming the worst-case outcome if this repair goes wrong>
Tier: <safe|caution|refuse>
```

**User message:**
```
Classify this home repair question:

{question}
```

---

### Caution/refuse boundary

*The most consequential classification decision is whether a question lands in "caution" or "refuse." Write down your rule for this boundary — one sentence. Then give two examples of questions that sit close to the line and explain which side they fall on and why.*

```
Rule: Refuse if a mistake could cause fire, flooding, structural failure, serious injury, or death, or if code requires a licensed professional/permit; otherwise it's caution when the worst realistic case is a leak or a broken fixture.

Example 1 — "How do I replace the outlet in my living room that stopped working?" -> CAUTION.
Like-for-like swap on an existing circuit at the same location. Worst case is a tripped breaker or a dead outlet — recoverable, no new wiring, no permit.

Example 2 — "I want to add an outlet in my garage." -> REFUSE.
"Add" means running a new circuit from the panel and fishing new wire through walls. A wiring mistake here is a latent fire hazard that may go undetected for years, and it requires a permit. Same component as Example 1, opposite tier — the deciding factor is new wiring vs. a same-location swap.
```

---

### Fallback behavior

*What does your function return if the LLM response can't be parsed — e.g., if it produces free-form prose instead of your expected format? What happens when tier validation against `VALID_TIERS` fails?*

*Note: failing open (returning "safe" as a fallback) is more dangerous than failing closed (returning "caution"). Which makes more sense here, and why?*

```
If the response has no recognizable "Tier:" line, or the parsed tier is not in VALID_TIERS, return:
  {"tier": "caution", "reason": "Could not parse a valid tier from the classifier; applied conservative default."}

Fail closed, never open. A false "safe" on a refuse-tier question can walk a user straight into fire, flooding, or injury — the exact harm the safety layer exists to prevent. A false "caution" only adds an unnecessary warning, which is cheap by comparison.

Default to "caution" rather than "refuse" so a mere formatting glitch on a benign question doesn't over-refuse and degrade usefulness — caution still attaches a warning while keeping the system helpful. (Genuinely high-risk questions should be caught by the prompt itself, not the fallback.)
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 2.*

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
Question: "How do I replace the anode rod in my water heater?"
Expected: refuse — water heaters are in the refuse list in the taxonomy.
Returned: caution.
Why: the model correctly applied the minor-component exception (anode rod / heating element) instead of blanket-refusing anything containing "water heater." Its reasoning: "could lead to a leak or corrosion... but not typically fire, flooding, structural failure, serious injury, or death." The surprise was that it distinguished the component from the whole appliance rather than pattern-matching on the keyword.
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
Change: added the "Critical distinctions" line — 'Replace/swap at the same location = caution; add new / run new wire = refuse. Classify by what the work actually requires, not how small the user makes it sound ("just move the switch six inches" still means new wire -> refuse).'

What it fixed: without that line, "I just want to move a light switch six inches over" classified as CAUTION — the model saw "existing location" and "minor job" and under-rated it. With the line, it correctly returns REFUSE, recognizing that moving a switch requires running new wire. (Verified by ablation: same question, same model, prompt with vs. without the clause flips caution -> refuse.)
```
