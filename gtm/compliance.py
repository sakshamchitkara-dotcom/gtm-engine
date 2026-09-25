"""Who we are allowed to email: suppression list, unsubscribes, GDPR consent."""

# EU/EEA + UK (UK GDPR). Cold outbound to these needs a lawful basis we can show;
# we only treat inbound (the lead came to us) as consent.
GDPR_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV",
    "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO", "GB", "CH",
}
INBOUND_SOURCES = {"demo_request", "webinar", "content", "inbound", "website", "trial"}


def is_suppressed(email, suppressed):
    email = email.lower()
    return email in suppressed or email.rsplit("@", 1)[-1] in suppressed


def check(lead, suppressed):
    """Returns "" if we may contact the lead, else the reason we may not."""
    if is_suppressed(lead.email, suppressed):
        return "suppressed"
    if lead.country in GDPR_COUNTRIES and lead.source not in INBOUND_SOURCES:
        return "gdpr: no consent (outbound source in GDPR region)"
    return ""


def unsubscribe(store, email, reason="unsubscribe"):
    """Suppress, cancel queued touches, and close the lead if we have it."""
    email = email.strip().lower()
    store.suppress(email, reason)
    store.clear_touches(email)
    try:
        store.set_stage(email, "lost")
    except KeyError:
        pass  # unsubscribes can arrive for people we never imported
