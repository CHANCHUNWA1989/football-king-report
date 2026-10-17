"""Opt-in, bounded research-only public source discovery. No live prices or odds."""
import json
from urllib.request import Request, urlopen

URL = "https://www.thesportsdb.com/api/v1/json/123/all_leagues.php"
MAX_BYTES = 2_000_000
TIMEOUT_SECONDS = 8

def parse_catalog(raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
        raise ValueError("CATALOG_SIZE_LIMIT")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("leagues"), list): raise ValueError("INVALID_LEAGUE_CATALOG")
    rows = data["leagues"]
    if len(rows) > 50000:
        raise ValueError("CATALOG_ROW_LIMIT")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("strLeague"); ident = row.get("idLeague")
        if isinstance(name, str) and name.strip() and isinstance(ident, str) and ident.strip() and row.get("strSport") == "Soccer":
            result.append({"id": ident.strip(), "name": name.strip()})
    return sorted(result, key=lambda x: (x["name"], x["id"]))

def discover():
    request = Request(URL, headers={"User-Agent": "ResearchCatalog/1.0 research-only (contact: github.com/CHANCHUNWA1989)"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_BYTES + 1)
    return parse_catalog(raw)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Opt in to one public catalog request")
    args = parser.parse_args()
    if not args.fetch:
        parser.error("No automatic network requests; pass --fetch explicitly")
    print(json.dumps({"source": URL, "research_only": True, "items": discover()}, ensure_ascii=False))
