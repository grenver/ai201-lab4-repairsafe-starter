import json
from datetime import datetime, timezone
from pathlib import Path

from config import LOG_FILE, LLM_MODEL

# Truncation limits (see specs/auditor-spec.md → "Why these truncation limits?").
_QUESTION_MAX = 300
_RESPONSE_PREVIEW_MAX = 200
# How much of the question to show in the one-line console summary.
_CONSOLE_QUESTION_MAX = 60


def log_interaction(question: str, tier: str, response: str) -> None:
    """
    Append a structured record of this interaction to the audit log.

    Writes one JSON object per line to LOG_FILE ("logs/audit.jsonl") and prints a
    one-line summary to the terminal. Creates the log directory if it doesn't
    exist. See specs/auditor-spec.md for the field and truncation decisions.

    Side effects only; returns None.
    """
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    record = {
        "timestamp": timestamp,
        "tier": tier,
        "question": question[:_QUESTION_MAX],
        "response_preview": response[:_RESPONSE_PREVIEW_MAX],
        "model": LLM_MODEL,
        "response_length": len(response),
    }

    # logs/ may not exist on a fresh clone/deploy or when run from another cwd.
    # Audit logging that silently fails is worse than none, so ensure the dir.
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # One-line terminal summary: aligned tier column + truncated question + length.
    q_preview = question[:_CONSOLE_QUESTION_MAX]
    if len(question) > _CONSOLE_QUESTION_MAX:
        q_preview += "..."
    print(
        f'[{timestamp}] {tier.upper():<7} | "{q_preview}" '
        f"| response {len(response)} chars logged"
    )
