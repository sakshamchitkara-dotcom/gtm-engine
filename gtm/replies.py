"""Rule-based reply classifier and the funnel/suppression updates each label triggers.

ponytail: regex rules, first match wins. Swap classify() for a model call if
the "other" bucket gets big; apply() stays the same.
"""
import re

from . import compliance
from .store import STAGES

RULES = [  # order matters: "not interested" must hit negative before interested
    ("unsubscribe", r"unsubscribe|remove me|opt[ -]?out|take me off|stop (emailing|contacting|sending|messaging)"
                    r"|do not (contact|email)|don'?t (contact|email) me"),
    ("ooo", r"out of (the )?office|\booo\b|on (vacation|holiday|leave|pto|parental leave)|auto(matic)?[- ]?reply"
            r"|limited access to (my )?email|away until"),
    ("referral", r"(right|best|better) (person|contact)|reach out to|(talk|speak) (to|with) (my|our)"
                 r"|looping in|cc'?ing|forward(ing|ed)? (this|you) to|who handles|is in charge of"),
    ("negative", r"not interested|no thanks|no,? thank you|not a (good )?fit|we('re| are) (all )?set"
                 r"|already (use|have|using|work with)|not for us|not relevant"),
    ("not_now", r"not (right )?now|next (quarter|year|month)|circle back|check back|later this year|bad timing"
                r"|timing (is|isn'?t)|no budget|revisit|in a (few|couple( of)?) (months|weeks)|after q[1-4]"),
    ("interested", r"interested|let'?s (chat|talk|connect|meet)|book (a|some)|calendar|sounds (good|great)"
                   r"|tell me more|send (me )?(more|info|details)|\bdemo\b|happy to (chat|talk)|what times?"
                   r"|(are|is) you (free|available)"),
]
_COMPILED = [(label, re.compile(rx, re.I)) for label, rx in RULES]
LABELS = [label for label, _ in RULES] + ["other"]
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def classify(text):
    for label, rx in _COMPILED:
        if rx.search(text or ""):
            return label
    return "other"


def apply(store, email, text):
    """Classify a reply and update the store. Returns (label, note)."""
    email = email.strip().lower()
    label = classify(text)
    store.add_event(email, f"reply:{label}")
    if label == "unsubscribe":
        compliance.unsubscribe(store, email)
        return label, "suppressed, touches cancelled, stage=lost"
    if label == "ooo":
        return label, "no change, cadence continues"
    store.clear_touches(email)  # a human answered: stop automation, rep takes over
    if label == "negative":
        _advance(store, email, "lost")
        return label, "stage=lost"
    _advance(store, email, "replied")
    if label == "referral":
        referred = sorted({m.group(0).lower() for m in EMAIL_RE.finditer(text)} - {email})
        return label, "referred to " + (", ".join(referred) if referred else "(no address found)")
    return label, "stage=replied, rep follow-up"


def _advance(store, email, stage):
    """Move forward only: a reply never drags a lead in 'meeting' back to 'replied'."""
    rec = store.lead(email)
    if rec is None:
        return
    if stage == "lost" or (rec["stage"] != "lost" and STAGES.index(stage) > STAGES.index(rec["stage"])):
        store.set_stage(email, stage)
