"""Keep caller-authored FT agreement separate from verified model evidence.

Even an allowlisted URL, a digest and two publisher labels cannot authenticate
the original capture, actual kickoff, fixture/period or upstream independence.
The legacy scoring adapter therefore always fails closed. Consistent claims
remain available through observation_record for research diagnostics only.
"""
from urllib.parse import urlsplit
from result_consensus_gate import verify_result

# Collection/schema allowlists only; neither mapping establishes independence.
_OBSERVATION_GROUP_LABELS = {"OpenLigaDB": "openligadb", "OpenFootball": "openfootball"}
_OBSERVATION_HOSTS = {"OpenLigaDB": {"api.openligadb.de"}, "OpenFootball": {"raw.githubusercontent.com"}}

def trusted_origin(provider, url):
    """Legacy name: validate URL shape only, without contacting the publisher."""
    if not isinstance(url, str):
        return False
    try:
        parsed=urlsplit(url)
        return (parsed.scheme=="https" and parsed.hostname in _OBSERVATION_HOSTS.get(provider,set())
                and parsed.username is None and parsed.password is None
                and parsed.port in (None,443)
                and (provider!="OpenFootball" or parsed.path.startswith("/openfootball/football.json/"))
                and (provider!="OpenLigaDB" or parsed.path.startswith("/getmatchdata/")))
    except ValueError:
        return False

def observation_record(sealed, observations):
    """Return sanitized agreement metadata, never a scoreable verified result."""
    if not isinstance(sealed, dict) or not isinstance(observations, list):
        return None
    try:
        fixture_id = sealed["fixture_id"]
        kickoff = sealed["kickoff_utc"]
        # Known collection labels constrain the observation schema only.
        safe_observations = []
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            provider = obs.get("provider_id")
            if (not isinstance(provider, str) or provider not in _OBSERVATION_GROUP_LABELS
                    or obs.get("independent_group_id") != _OBSERVATION_GROUP_LABELS[provider]):
                continue
            # URL/digest syntax is audit metadata, not proof of original bytes.
            source_url = obs.get("source_url")
            raw_sha256 = obs.get("raw_sha256")
            if (not isinstance(source_url, str)
                    or not trusted_origin(provider, source_url)
                    or not isinstance(raw_sha256, str)
                    or len(raw_sha256) != 64
                    or any(ch not in "0123456789abcdef" for ch in raw_sha256)):
                continue
            safe_observations.append(obs)
        verdict = verify_result(fixture_id, kickoff, safe_observations)
        if verdict["status"] != "AGREED_UNVERIFIED":
            return None
        return dict(verdict, recorded_kickoff_utc=kickoff)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return None


def verified_record(sealed, observations):
    """Legacy scoring API: JSON claims cannot supply authenticated evidence.

    This function intentionally accepts no caller-controlled override. A future
    trusted original-evidence verifier needs its own explicitly reviewed path.
    """
    return None
