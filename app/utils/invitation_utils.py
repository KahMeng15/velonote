LINK_ONLY_INVITATION_PREFIX = "link-only-invite-"
LINK_ONLY_INVITATION_EMAIL_SUFFIX = "@invitations.local"


def build_link_only_email(token: str) -> str:
    """Return a pseudo-email that marks the invitation as a link-only invite."""
    return f"{LINK_ONLY_INVITATION_PREFIX}{token}{LINK_ONLY_INVITATION_EMAIL_SUFFIX}"


def is_link_only_email(email: str | None) -> bool:
    """Detect whether the stored invitation email is the synthetic link-only marker."""
    return bool(email and email.startswith(LINK_ONLY_INVITATION_PREFIX))
