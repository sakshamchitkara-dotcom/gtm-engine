"""Offline email verification: valid / risky / invalid.

ponytail: no SMTP/MX probing (slow, gets you blocklisted). Rules only; plug a
verifier API into verify() if bounce rate matters more than cost.
"""
import re

SYNTAX = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
                    r"@([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")

ROLE_LOCALS = {
    "info", "sales", "support", "admin", "contact", "hello", "team", "marketing", "office",
    "help", "billing", "hr", "jobs", "careers", "press", "noreply", "no-reply", "webmaster",
    "postmaster", "abuse", "accounts", "enquiries", "service",
}

DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "temp-mail.org",
    "yopmail.com", "trashmail.com", "getnada.com", "sharklasers.com", "dispostable.com",
    "throwawaymail.com", "maildrop.cc", "fakeinbox.com",
}

TYPOS = {
    "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gmail.co": "gmail.com", "gamil.com": "gmail.com",
    "gnail.com": "gmail.com", "gmail.con": "gmail.com", "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com",
    "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com", "outlok.com": "outlook.com",
    "outllok.com": "outlook.com", "iclod.com": "icloud.com",
}


def verify(email):
    """Returns (status, reason). status is valid | risky | invalid."""
    email = (email or "").strip().lower()
    if not SYNTAX.match(email):
        return "invalid", "bad syntax"
    local, domain = email.split("@")
    if domain in TYPOS:
        return "invalid", f"typo domain, did you mean {TYPOS[domain]}"
    if domain in DISPOSABLE:
        return "invalid", "disposable domain"
    if local in ROLE_LOCALS:
        return "risky", "role-based address"
    return "valid", ""
