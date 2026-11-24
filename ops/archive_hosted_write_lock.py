"""Fail-closed hosted archive write lock for unapproved research cutover.

The real remote archive ref exists, but neither enforceable archive custody,
branch protection nor independent reviewer authorization has been proven.
Until an independently reviewed future code change introduces an actual hosted
policy verifier, *no official writer entrypoint may perform network writes*.

This is deliberately NOT overridable by environment variables, CLI flags or
a writable JSON receipt. A pinned branch name/Git SHA is NOT authorization.
"""

class HostedArchiveWriteHold(ValueError):
    """Bounded no-write rejection without secrets or endpoint details."""


def require_independent_hosted_archive_custody():
    """Never authorize an official remote archive push from this Draft pilot."""
    raise HostedArchiveWriteHold("HOSTED_ARCHIVE_WRITE_BLOCKED_PENDING_INDEPENDENT_POLICY")
