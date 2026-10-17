"""Opt-in, bounded research-only public source discovery. No live prices or odds."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import time

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

def fetch_catalog(*, opener=urlopen, sleep=time.sleep, attempts=2):
    """Retry only transient network failures; cap total attempts and memory."""
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError("INVALID_ATTEMPTS")
    request = Request(URL, headers={"User-Agent": "ResearchCatalog/1.0 research-only (contact: github.com/CHANCHUNWA1989)"})
    for index in range(attempts):
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                return parse_catalog(response.read(MAX_BYTES + 1))
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or index + 1 == attempts:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if index + 1 == attempts:
                raise
        sleep(min(2 ** index, 2))
    raise RuntimeError("UNREACHABLE")


def discover():
    return fetch_catalog()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Opt in to one public catalog request")
    args = parser.parse_args()
    if not args.fetch:
        parser.error("No automatic network requests; pass --fetch explicitly")
    print(json.dumps({"source": URL, "research_only": True, "items": discover()}, ensure_ascii=False))
