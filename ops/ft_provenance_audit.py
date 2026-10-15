"""Conservative metadata checks for research-only score agreements."""
import re
from urllib.parse import urlparse

SHA256=re.compile(r"^[a-fA-F0-9]{64}$")

def provenance_status(agreement):
    urls=agreement.get("source_urls")
    hashes=agreement.get("raw_sha256")
    if not isinstance(urls,list) or not isinstance(hashes,list):
        return "MISSING_PROVENANCE"
    if len(urls)<2 or len(hashes)<2 or len(urls)!=len(hashes):
        return "INSUFFICIENT_PROVENANCE"
    hosts=[]
    for url,digest in zip(urls,hashes):
        if not isinstance(url,str) or not isinstance(digest,str):
            return "INVALID_PROVENANCE"
        parsed=urlparse(url)
        if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
            return "INVALID_PROVENANCE"
        if not SHA256.fullmatch(digest):
            return "INVALID_PROVENANCE"
        hosts.append(parsed.hostname.lower())
    if len(set(hosts))<2:
        return "NON_INDEPENDENT_HOSTS"
    return "METADATA_PRESENT_UNVERIFIED"
