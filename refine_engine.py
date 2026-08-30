"""Prompt-refinement helpers.

Pure functions (no Streamlit, no network) so they can be unit-tested: build the
comparison context sent to the vision model, and parse its verdict back out.
"""
import re

DECISIONS = ("IMPROVE", "REVERT", "DONE")

REFINE_SYSTEM = (
    "You are refining a text-to-image PROMPT so that the image it generates matches a "
    "TARGET image as closely as possible.\n\n"
    "You are shown, in order: the TARGET image(s), then (if present) the PREVIOUS attempt, "
    "then the NEWEST attempt (the last image). Judge how well the NEWEST attempt matches the "
    "TARGET, compared with the previous attempt and the target.\n\n"
    "Respond in EXACTLY this format, nothing before or after:\n"
    "ASSESSMENT: <2-4 sentences on what still differs from the target, and whether the newest "
    "attempt improved or regressed versus the previous one>\n"
    "DECISION: IMPROVE | REVERT | DONE\n"
    "PROMPT: <the full standalone prompt to use for the NEXT generation>\n\n"
    "Decision rules:\n"
    "- IMPROVE: the newest attempt is the best so far but can get closer; give a refined prompt "
    "that fixes the remaining differences from the target.\n"
    "- REVERT: the newest attempt is WORSE than an earlier one; take the earlier better prompt "
    "(see the history below) and change it a DIFFERENT way to close the gap.\n"
    "- DONE: the newest attempt already matches the target well and further prompt tweaks are "
    "unlikely to help; repeat the current best prompt in the PROMPT field.\n"
    "- PROMPT must always be a complete image-generation prompt, never instructions or commentary."
)


def format_history(history, limit=4):
    """history: list of {prompt, assessment}. Compact text of the last few attempts."""
    if not history:
        return "(no previous attempts yet)"
    lines = []
    start = max(0, len(history) - limit)
    for i, h in enumerate(history[start:], start=start + 1):
        p = (h.get("prompt") or "").strip().replace("\n", " ")
        if len(p) > 400:
            p = p[:400] + "…"
        note = (h.get("assessment") or "").strip().replace("\n", " ")
        lines.append(f"Attempt {i}: PROMPT: {p}\n   → {note}")
    return "\n".join(lines)


def build_user_message(current_prompt, history, n_targets=1, has_prev=False):
    order = f"The first {n_targets} image(s) are the TARGET"
    if has_prev:
        order += ", the next-to-last image is the PREVIOUS attempt, and the last image is the NEWEST attempt."
    else:
        order += ", and the last image is the NEWEST attempt."
    base = current_prompt.strip() if current_prompt else "(none yet — infer a prompt that would produce the TARGET)"
    return (
        f"{order}\n\n"
        f"CURRENT best prompt (this produced the newest attempt):\n{base}\n\n"
        f"History of attempts (oldest → newest):\n{format_history(history)}\n\n"
        "Assess the newest attempt against the target and respond in the required format."
    )


def parse_verdict(text, fallback_prompt=""):
    """Forgiving parse. Returns {decision, prompt, assessment, raw}."""
    raw = text or ""
    assessment, prompt = "", ""
    decision = "IMPROVE"

    m = re.search(r"ASSESSMENT:\s*(.+?)(?=\n\s*DECISION:|\n\s*PROMPT:|$)", raw, re.S | re.I)
    if m:
        assessment = m.group(1).strip()

    m = re.search(r"DECISION:\s*(IMPROVE|REVERT|DONE)", raw, re.I)
    if m:
        decision = m.group(1).upper()

    m = re.search(r"PROMPT:\s*(.+)$", raw, re.S | re.I)
    if m:
        prompt = m.group(1).strip()

    if not prompt:
        # Unformatted output: keep current prompt if DONE, else treat body as the prompt.
        prompt = fallback_prompt if decision == "DONE" else (raw.strip() or fallback_prompt)
    if not assessment:
        assessment = "(model did not return a structured assessment)"
    return {"decision": decision, "prompt": prompt, "assessment": assessment, "raw": raw}
