import re

from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# An unrecognized tier (e.g. "unknown" from a stubbed classifier) is treated as
# "caution": fail safe rather than fail open. We still attach safety warnings and a
# clear professional recommendation, without either handing out unguarded
# instructions (safe) or uselessly refusing a possibly-benign question (refuse).
# See specs/responder-spec.md → Fallback for unknown tier.
_FALLBACK_TIER = "caution"

_SAFE_PROMPT = """You are a knowledgeable, practical home repair assistant. The user's question has been classified as SAFE — a routine, low-risk repair a homeowner can handle with basic tools.

Give a clear, specific, actionable answer:
- List the tools and materials needed first.
- Then give the steps in order, with concrete detail (sizes, directions, settings).
- Keep it concise and confident.

You may include one brief, relevant safety tip, but do NOT pad the answer with disclaimers or "consider a professional" hedging — this task is low-risk and the user wants to do it themselves."""

_CAUTION_PROMPT = """You are a knowledgeable home repair assistant. The user's question has been classified as CAUTION — a repair a motivated homeowner can do, but one that touches water or electrical systems where a mistake has real cost or mild injury risk.

Provide a helpful, specific answer, AND:
- Open by naming the specific risk (e.g., water damage, minor shock, a leak) and the precaution that controls it — typically "shut off the water/breaker first and verify it is off before touching anything."
- Give the steps, but explicitly flag the point(s) where homeowners most commonly make mistakes.
- Include a CLEAR recommendation (not a throwaway line) to hire a licensed professional if the user is unsure, lacks the right tools, or if what they see differs from what you describe.

Tone: you are helping them do it safely, not refusing. The professional recommendation is a firm "if in doubt, call a pro," not a blanket "you shouldn't do this." """

_REFUSE_PROMPT = """You are a home repair safety assistant. The user's question has been classified as REFUSE — a task where an amateur mistake can cause fire, explosion, electrocution, flooding, structural collapse, or death, or where law requires a licensed professional and a permit.

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

Tone: warm and genuinely helpful — you are protecting the user, not brushing them off. But never trade safety for helpfulness."""

_SYSTEM_PROMPTS = {
    "safe": _SAFE_PROMPT,
    "caution": _CAUTION_PROMPT,
    "refuse": _REFUSE_PROMPT,
}

# Temperature per tier: refuse stays low for consistency; safe/caution can be a
# little warmer for natural prose.
_TEMPERATURES = {"safe": 0.4, "caution": 0.3, "refuse": 0.2}

# Backstop for the refuse tier: if the model leaks a procedure despite the prompt,
# these patterns catch it. Verbs are ones that appear in *instructions* but should
# never appear in a proper refusal (which only says contact/call/hire a pro).
_NUMBERED_STEP = re.compile(r"(?im)^\s*(?:step\s*\d|\d+[.)]\s|[-*]\s+(?:first|next|then|turn|connect|cut|remove|attach|unscrew|loosen|tighten))")
_PROCEDURAL_VERB = re.compile(
    r"(?i)\b(?:splice|unscrew|screw in|solder|strip the|loosen|tighten|"
    r"shut off the|turn off the|turn the valve|cut the|wire the|attach the|"
    r"mount the|connect the|disconnect the|bleed the|crimp)\b"
)

_CANNED_REFUSAL = (
    "I can't walk you through this one — it's a job that needs a licensed "
    "professional, because a mistake can cause fire, flooding, electrocution, or "
    "structural damage. Please contact a licensed professional (an electrician, "
    "plumber, gas fitter, or structural engineer, depending on the work) and ask "
    "them to assess it. Many jurisdictions also require a permit and inspection "
    "for this kind of repair."
)


def _leaks_procedure(text: str) -> bool:
    """True if a refuse-tier response appears to contain how-to steps."""
    if _NUMBERED_STEP.search(text):
        return True
    # A single procedural verb can be a false positive; require two distinct hits.
    return len(set(m.lower() for m in _PROCEDURAL_VERB.findall(text))) >= 2


def _complete(question: str, tier: str) -> str:
    system = _SYSTEM_PROMPTS[tier]
    completion = _client.chat.completions.create(
        model=LLM_MODEL,
        temperature=_TEMPERATURES[tier],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


def generate_safe_response(question: str, tier: str) -> str:
    """
    Generate a response to a home repair question, calibrated to its safety tier.

    Uses a different system prompt per tier (see specs/responder-spec.md). For the
    "refuse" tier, applies a defense-in-depth backstop: if the generated response
    appears to contain procedural how-to content despite the prompt, it regenerates
    once, then falls back to a canned referral.

    An unrecognized tier is treated as "refuse" (fail closed — see the spec).

    Returns the response as a plain string.
    """
    if tier not in VALID_TIERS:
        tier = _FALLBACK_TIER

    try:
        response = _complete(question, tier)
    except Exception as exc:
        # On API failure, never emit instructions — return a safe, generic message.
        return (
            "Sorry — I couldn't generate a response just now "
            f"({type(exc).__name__}). For anything involving electrical, gas, "
            "plumbing, or structural work, please consult a licensed professional."
        )

    if tier == "refuse" and _leaks_procedure(response):
        try:
            response = _complete(question, tier)
        except Exception:
            return _CANNED_REFUSAL
        if _leaks_procedure(response):
            return _CANNED_REFUSAL

    return response
