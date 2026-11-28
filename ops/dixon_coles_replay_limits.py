"""Bounded fixed-pilot replay resource policy; never selects history by results."""
# The former 32 total proofs were exhausted by 32 historical + current.
# Preserve the old maximum aggregate decoded payload (32 * 6 MB),
# while allowing more small proofs. Revisit before the finite cap is hit.
MAX_CAPTURE_PROOFS = 64
MAX_CAPTURE_PAYLOAD_BYTES = 192_000_000
