"""Does request_text authorize deletion?

1. Deterministic multilingual rules (EN/ES/PT/FR/JA/KO + DE/IT/NL keywords).
2. Explicit non-deletion requests (access, copy/portability, correction, login help,
   invoices, marketing opt-out) are NOT_APPLICABLE even when they contain "remove".
3. A CLASSIFY_REQUEST "non-deletion" activity for the subject's account corroborates (2).
4. Only texts the rules cannot decide go to the model, PII-scrubbed and cached.
"""
from __future__ import annotations

import re

from .config import INTENT_MODEL, INTENT_THINKING
from .guardrails import FLAG_INTENT_CONFLICT, FLAG_INTENT_LLM, scrub_pii

DELETION_RE = re.compile(
    r"\b(delet\w*|eras\w*|remov\w* (?:my|the|this|any|all|every|records|personal|profile)|"
    r"close (?:my|this|the) account|closed? (?:it|my account)|account[- ]deletion|"
    r"permanent(?:ly)? delet\w*|forget me|(?:been|was|were|fully|already) removed|is gone|"
    r"no longer exists?)\b"
    r"|supprim\w*|suppression|eliminaci\w*|elimin\w*|borr\w+ mi|exclus[ãa]o|exclu\w*|apag\w*|"
    r"削除|삭제|删除|löschen|lösch\w*|cancella\w*|verwijder\w*",
    re.I)

NON_DELETION_RE = re.compile(
    r"marketing lists? only|only (?:from|the) marketing|stop (?:the |sending )?promotional|unsubscribe|"
    r"opt(?:-| )?out of marketing|"
    r"\bonly\s+(?:remove|unsubscribe|take)\s+(?:me\s+)?(?:from\s+)?(?:the\s+)?marketing\s+lists?\b|"
    r"(?:send|give|provide|need|want|like) (?:me )?a copy|copy of (?:the information|last year)|"
    r"download my (?:account )?(?:data|information)|portable format|"
    r"what (?:personal )?(?:information|data) (?:you|do you) hold|tell me what personal|"
    r"(?:change|update|correct) (?:the |my )?(?:email|phone|mobile|address|surname|name)|"
    r"misspelled|out of date|reset(?:ting)? (?:the |my )?(?:login|password)|can't access my profile|"
    r"invoices?\b|"
    # "only from the marketing list(s)" in ES/PT/FR/DE/IT; not after a negation ("pas seulement")
    r"(?<!\bnot )(?<!\bno )(?<!\bpas )(?<!\bnão )(?<!\bnicht )(?<!\bnon )"
    r"\b(?:solo|sólo|solamente|únicamente|unicamente|apenas|somente|uniquement|seulement|nur|soltanto)\b"
    r"[^.]{0,40}\bmarketing\b",
    re.I)

# Negations attached to the deletion verb are different from an independent marketing opt-out.
# These bounded prefixes support the languages covered by DELETION_RE without treating "not only"
# as a negation. Clause boundaries are applied before checking each deletion match.
NEGATED_DELETION_PREFIXES = (
    re.compile(r"\b(?:do not|don't|dont|does not|doesn't|did not|didn't|will not|won't|would not|wouldn't|never|without)\b(?:\W+\w+){0,6}\W*$", re.I),
    re.compile(r"\bnot\s+(?:a\s+)?(?:request|asking|requesting|seeking|wanting|intending)\b(?:\W+\w+){0,5}\W*$", re.I),
    re.compile(r"\bno\s+(?:quiero|deseo|solicito|pido|necesito)\b(?:\W+\w+){0,5}\W*$", re.I),
    re.compile(r"\b(?:não|nao)\s+(?:quero|desejo|solicito|peço|peco|preciso)\b(?:\W+\w+){0,5}\W*$", re.I),
    re.compile(r"\b(?:je\s+)?ne\b(?:\s+\w+){0,3}\s+pas\s*$", re.I),
    re.compile(r"\b(?:ich\s+)?möchte\b(?:\W+\w+){0,3}\bnicht\b\s*$", re.I),
    re.compile(r"\bnicht\b\s*$", re.I),
    re.compile(r"\bnon\s+(?:voglio|desidero|chiedo|intendo)\b(?:\W+\w+){0,5}\W*$", re.I),
)
CLAUSE_BOUNDARY_RE = re.compile(r"[;.!?\n]|\b(?:but|however|pero|mais|aber|ma)\b", re.I)

SCHEMA = {
    "type": "object",
    "properties": {"authorizes_deletion": {"type": "boolean"}, "request_type": {"type": "string"}},
    "required": ["authorizes_deletion", "request_type"],
    "additionalProperties": False,
}
PROMPT = ("You classify customer privacy requests for an e-commerce company. Decide whether the "
          "request below asks to delete/erase/close the person's account or personal data. Requests "
          "for access, a copy or export of data, corrections, login help, invoices, or marketing "
          "opt-out only do NOT authorize deletion. Request (identifiers redacted):\n\n{text}")


def classify(text: str, non_deletion_activity: bool, llm=None) -> tuple[bool, list, str]:
    """Return (authorizes_deletion, flags, reason)."""
    flags: list = []
    non_del = bool(NON_DELETION_RE.search(text))
    deletion_matches = list(DELETION_RE.finditer(text))
    deletion = any(not _negated_deletion_match(text, match) and
                   not _marketing_optout_match(text, match) for match in deletion_matches)
    if deletion:
        if non_deletion_activity:
            flags.append(FLAG_INTENT_CONFLICT)       # text wins: it is what authorizes deletion
        return True, flags, "rule:deletion"
    if non_del or deletion_matches:                  # marketing-only or explicitly negated deletion
        return False, flags, "rule:non_deletion" if non_del else "rule:negated_deletion"
    if non_deletion_activity:
        return False, flags, "activity:classify_request"
    if llm is not None and (llm.available_for(INTENT_MODEL) or llm.cache):
        result = llm.json_call(INTENT_MODEL, PROMPT.format(text=scrub_pii(text)), SCHEMA,
                               max_tokens=1024, thinking_level=INTENT_THINKING)
        if result is not None:
            flags.append(FLAG_INTENT_LLM)
            return bool(result["authorizes_deletion"]), flags, f"llm:{result['request_type']}"
    # Fail safe: an unreadable request is not treated as authorization to delete.
    flags.append("INTENT_UNDETERMINED")
    return False, flags, "undetermined"


def _negated_deletion_match(text: str, match: re.Match) -> bool:
    """True only when a deletion cue is syntactically negated in its own clause."""
    prefix = text[max(0, match.start() - 96):match.start()]
    parts = CLAUSE_BOUNDARY_RE.split(prefix)
    prefix = parts[-1]
    return any(pattern.search(prefix) for pattern in NEGATED_DELETION_PREFIXES)


def _marketing_optout_match(text: str, match: re.Match) -> bool:
    """A delete-like verb scoped only to a marketing list is an opt-out, not data deletion."""
    left = max((m.end() for m in CLAUSE_BOUNDARY_RE.finditer(text[:match.start()])), default=0)
    boundary = CLAUSE_BOUNDARY_RE.search(text, match.end())
    right = boundary.start() if boundary else len(text)
    clause = text[left:right]
    if not re.search(r"\bmarketing\b", clause, re.I) or not NON_DELETION_RE.search(clause):
        return False
    before_marketing = clause[:re.search(r"\bmarketing\b", clause, re.I).start()]
    # A named account/data object makes this a separate deletion request with an additional
    # marketing opt-out. Without one, multilingual "delete/remove me only from marketing" stays
    # non-deletion.
    return not re.search(r"\b(?:account|profile|data|information|records?|cuenta|datos?|perfil|"
                         r"compte|données?|profil|conta|perfil|informações?|dados?|konto|profil|"
                         r"informacion|información)\b", before_marketing, re.I)
