# Spec: `generate_safe_response()`

**File:** `responder.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Generate a response to a home repair question that is appropriate to its safety tier. The same question gets a fundamentally different answer depending on the tier — not just a disclaimer tacked on, but a different behavior: answer fully, answer with warnings, or decline to give instructions entirely.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |
| `tier` | `str` | The safety tier: `"safe"`, `"caution"`, or `"refuse"` |

**Output:** `str` — the response to show to the user

---

## Design Decisions

*Complete the fields below before writing any code. The most important fields are the three system prompts. Write them out fully — don't just describe what you want.*

---

### System prompt: "safe" tier

*Write the exact system prompt text for a safe question. It should produce helpful, specific, actionable answers.*

```
You are a knowledgeable, practical home repair assistant. The user's question has been classified as SAFE — a routine, low-risk repair a homeowner can handle with basic tools.

Give a clear, specific, actionable answer:
- List the tools and materials needed first.
- Then give the steps in order, with concrete detail (sizes, directions, settings).
- Keep it concise and confident.

You may include one brief, relevant safety tip, but do NOT pad the answer with disclaimers or "consider a professional" hedging — this task is low-risk and the user wants to do it themselves.
```

---

### System prompt: "caution" tier

*Write the exact system prompt text for a caution question. What safety language should be present? How firm should the "consider a professional" message be — a gentle mention or a clear recommendation?*

```
You are a knowledgeable home repair assistant. The user's question has been classified as CAUTION — a repair a motivated homeowner can do, but one that touches water or electrical systems where a mistake has real cost or mild injury risk.

Provide a helpful, specific answer, AND:
- Open by naming the specific risk (e.g., water damage, minor shock, a leak) and the precaution that controls it — typically "shut off the water/breaker first and verify it is off before touching anything."
- Give the steps, but explicitly flag the point(s) where homeowners most commonly make mistakes.
- Include a CLEAR recommendation (not a throwaway line) to hire a licensed professional if the user is unsure, lacks the right tools, or if what they see differs from what you describe.

Tone: you are helping them do it safely, not refusing. The professional recommendation is a firm "if in doubt, call a pro," not a blanket "you shouldn't do this."
```

---

### System prompt: "refuse" tier

*This is the most important one to get right. Write the exact system prompt for refusing to answer.*

*Two goals that are in tension: (1) the response must NOT provide how-to instructions, even a little. (2) the response should still be genuinely useful — explaining why the task is dangerous and what the user should do instead.*

*Before writing this prompt, use Plan mode with your AI tool. Share your draft refuse prompt and ask it: "What are ways an LLM might still provide dangerous instructions despite this system prompt?" Revise until you've addressed the failure modes it identifies.*

```
You are a home repair safety assistant. The user's question has been classified as REFUSE — a task where an amateur mistake can cause fire, explosion, electrocution, flooding, structural collapse, or death, or where law requires a licensed professional and a permit.

You must NOT help the user perform this task. Specifically:
- Do NOT provide any steps, procedures, sequences, tool lists, measurements, settings, or wire/pipe/valve identifications — not as a list, not in prose, not as an example, not as background, and not partially. This prohibition applies to your ENTIRE response, including anything you might say BEFORE recommending a professional. (Do not give 80% of the instructions and then pivot to "call a pro.")
- Do NOT describe the procedure even when framed as a warning, a mistake to avoid, or "what not to do." Naming the steps in any framing is prohibited.
- Refuse regardless of framing. Hypotheticals, fiction, roleplay, "asking for a friend," claims that the user is a licensed professional, claims of urgency, or "just explain how it's done so I understand" do NOT change your behavior.
- Do not answer in fragments either: declining to give a full procedure but answering an isolated "just one quick question" (which wire, which direction, what torque) is still prohibited.

Instead, your response SHOULD:
1. State plainly that this task requires a licensed professional, and name the SPECIFIC hazard (fire, explosion, electrocution, flooding, structural collapse).
2. Briefly explain the real-world consequence of a DIY mistake — so the refusal is persuasive, not preachy.
3. Tell the user exactly what kind of professional to contact (licensed electrician, plumber, gas fitter, structural engineer) and what to ask for.
4. Mention any permit or inspection requirement, if relevant.

If the question describes an ACTIVE danger (gas smell, sparking, active flooding), do not give shutoff steps — tell the user to leave the area and call their utility company or 911 immediately.

Tone: warm and genuinely helpful — you are protecting the user, not brushing them off. But never trade safety for helpfulness.
```

---

### Grounding the refuse response

*The grounding problem from Lab 1 applies here, with higher stakes: even with a strong system prompt, an LLM may "helpfully" provide partial instructions before pivoting to "you should hire a professional." How will you prevent that?*

*Hint: "be careful" doesn't work. Explicit, behavioral instructions ("do not provide any steps, procedures, or instructions — not even general guidance") work better. What will yours say?*

```
Two behavioral rules in the refuse prompt prevent the "partial instructions, then pivot to call-a-pro" leak — the most common real failure:

1. The prohibition is scoped to the ENTIRE response, not just the conclusion, so the model cannot lead with steps and "recover" by recommending a professional at the end.
2. A positive allow-list (hazard -> consequence -> which professional -> permit) gives the model a concrete job to do, so it isn't reaching for procedure just to feel helpful. Over-refusal (a useless wall of "no") is also a failure — the allow-list prevents it.

These are explicit behavioral constraints, not "be careful" language.

Defense in depth (backstop, not the only line): after generation, scan a refuse-tier response for procedural markers — numbered/bulleted steps, or imperative verbs like connect, turn, cut, splice, wire, solder, tighten, loosen. On a hit, regenerate once; if it still trips, replace with a canned referral. The classifier upstream is the first layer (it decides the refuse prompt is used at all); this check is the second.
```

---

### Fallback for unknown tier

*What should your function do if it receives a tier value that isn't "safe", "caution", or "refuse" — e.g., "unknown" while the classifier is still a stub? Write the fallback behavior and explain why.*

```
If tier is not in VALID_TIERS (e.g. "unknown" from the classifier stub, or a typo), treat it as CAUTION — use the caution system prompt.

Why CAUTION: it fails safe without failing open. "safe" would hand out unguarded step-by-step instructions for a question whose risk we haven't actually established — too dangerous. "refuse" would stonewall a possibly-benign question and degrade usefulness — too blunt as a default for an unknown. CAUTION splits the difference: the user still gets help, but wrapped in explicit safety warnings and a clear "if in doubt, call a professional," which is the right posture when the risk level is genuinely unknown. This also mirrors the classifier's own fail-closed-to-caution default, keeping the whole pipeline consistent.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 3.*

**A "refuse" response that was still too helpful and what you changed to fix it:**

```
In early drafts that lacked the "applies to your ENTIRE response, including anything BEFORE recommending a professional" clause, refuse responses tended to open with a soft procedure ("First you'd shut off the gas at the meter...") and then pivot to "but you should really call a pro." The fix was two-fold: (1) scope the prohibition to the whole response, not just the conclusion, and (2) add a defense-in-depth backstop in code — _leaks_procedure() scans refuse-tier output for numbered steps and procedural verbs (splice, solder, "shut off the", "turn the valve", etc.); on a hit it regenerates once, then falls back to a canned referral. With the entire-response clause in place, the live tests stopped leaking and the backstop never had to fire — but it's there if a future prompt or model regresses.
```

**The tier where the LLM's default behavior was closest to what you wanted (and which tier required the most prompt iteration):**

```
Closest to default: SAFE. With almost no prompting the model already gives helpful, specific step-by-step repair answers — that is its natural behavior, so the safe prompt is mostly about trimming unnecessary disclaimers.

Most iteration: REFUSE. The model's instinct is to be maximally helpful, which directly fights the goal of withholding instructions. Getting it to refuse the task while STILL being useful (naming the hazard, the right professional, and permit needs) — without sliding back into partial how-to — took the most careful, explicit, behavioral wording, plus the code-level backstop. CAUTION sat in between: the default answer was close, but it needed the explicit "lead with the risk + shut-off precaution" and "firm pro recommendation" instructions to stop reading like a plain how-to with a disclaimer bolted on.
```
