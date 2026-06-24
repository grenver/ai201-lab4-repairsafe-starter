from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# Fail closed, never open: an unparseable/invalid response defaults to "caution"
# (an unnecessary warning) rather than "safe" (which could walk a user into a
# refuse-tier repair). See specs/classifier-spec.md → Fallback behavior.
_FALLBACK_TIER = "caution"

_SYSTEM_PROMPT = """You are a safety classifier for a home repair Q&A assistant. Classify each question into exactly one tier:

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
Tier: <safe|caution|refuse>"""


def _parse_response(text: str) -> dict:
    """Extract tier and reason from the raw LLM response.

    Scans for the line beginning with "Tier:" (case-insensitive) and the line
    beginning with "Reasoning:". The tier is emitted last so it stays
    unambiguous even if the reasoning wraps. Returns the conservative fallback
    if no valid tier line is found.
    """
    tier = None
    reason = None

    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("tier:"):
            candidate = stripped[len("tier:"):].strip().lower()
            if candidate in VALID_TIERS:
                tier = candidate
        elif lowered.startswith("reasoning:"):
            reason = stripped[len("reasoning:"):].strip()

    if tier is None:
        return {
            "tier": _FALLBACK_TIER,
            "reason": "Could not parse a valid tier from the classifier; applied conservative default.",
        }

    if not reason:
        # Tier parsed but no labeled reasoning — fall back to the raw text so the
        # caller still gets some explanation.
        reason = text.strip() or "No reasoning provided."

    return {"tier": tier, "reason": reason}


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    Sends a single chat completion to the Groq LLM (no tools, no history),
    parses the tier and reasoning out of the response, and validates the tier
    against VALID_TIERS. On any API error, unparseable response, or invalid
    tier, fails closed to "caution".

    See specs/classifier-spec.md for the prompt, output format, and edge cases.

    Returns a dict with:
      - "tier"   : str — one of "safe", "caution", "refuse"
      - "reason" : str — a brief explanation of why this tier was assigned
    """
    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Classify this home repair question:\n\n{question}",
                },
            ],
            temperature=0,
        )
    except Exception as exc:
        return {
            "tier": _FALLBACK_TIER,
            "reason": f"Classifier request failed ({type(exc).__name__}); applied conservative default.",
        }

    raw = completion.choices[0].message.content or ""
    return _parse_response(raw)
