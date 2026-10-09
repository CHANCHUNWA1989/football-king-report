"""Conservative league-scoped team aliases for joining two independent feeds.

Only explicit, well-known alternate names are permitted; never fuzzy match,
remove suffixes globally, infer team IDs, or mix leagues. Ambiguous names stay
unmatched and can be reviewed from `identity_coverage.json`.
"""
import unicodedata


def folded(value):
    if not isinstance(value, str):
        return ""
    letters = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in letters if c.isalnum() and not unicodedata.combining(c))


# Curated, high-confidence alternate spellings / common club names.
# Do not add a nickname shared by different clubs in the same league.
ALIASES = {
    "epl": {
        "manchestercity": ("man city", "manchester city fc"),
        "manchesterunited": ("man united", "man utd", "manchester united fc"),
        "tottenhamhotspur": ("tottenham", "spurs", "tottenham hotspur fc"),
        "wolverhamptonwanderers": ("wolves", "wolverhampton wanderers fc"),
        "newcastleunited": ("newcastle", "newcastle united fc"),
        "westhamunited": ("west ham", "west ham united fc"),
        "brightonandhovealbion": ("brighton", "brighton & hove albion", "brighton and hove albion fc"),
        "nottinghamforest": ("nott'm forest", "nottingham forest fc"),
        "crystalpalace": ("crystal palace fc",),
        "leedsunited": ("leeds", "leeds united fc"),
        "astonvilla": ("aston villa fc",),
        "liverpool": ("liverpool fc",),
        "arsenal": ("arsenal fc",),
        "chelsea": ("chelsea fc",),
        "everton": ("everton fc",),
        "fulham": ("fulham fc",),
        "bournemouth": ("afc bournemouth",),
    },
    "championship": {
        "sheffieldwednesday": ("sheff wed", "sheffield wednesday fc"),
        "sheffieldunited": ("sheff utd", "sheffield united fc"),
        "westbromwichalbion": ("west brom", "wba", "west bromwich albion fc"),
        "queensparkrangers": ("qpr", "queens park rangers"),
        "prestonnorthend": ("preston", "preston north end fc"),
        "blackburnrovers": ("blackburn", "blackburn rovers fc"),
        "norwichcity": ("norwich", "norwich city fc"),
        "swanseacity": ("swansea", "swansea city fc"),
        "coventrycity": ("coventry", "coventry city fc"),
        "stoke city": ("stoke", "stoke city fc"),
        "bristolcity": ("bristol city fc",),
        "hullcity": ("hull", "hull city fc"),
        "oxfordunited": ("oxford", "oxford united fc"),
        "ipswichtown": ("ipswich", "ipswich town fc"),
        "middlesbrough": ("boro", "middlesbrough fc"),
    },
    "bundesliga": {
        "bayernmunchen": ("fc bayern munchen", "fc bayern münchen", "bayern munich", "bayern münchen", "fc bayern munich"),
        "borussiadortmund": ("bvb", "borussia dortmund 09", "bvb 09"),
        "bayer04leverkusen": ("bayer leverkusen", "bayer 04"),
        "rb leipzig": ("rasenballsport leipzig", "rb leipzig"),
        "eintrachtfrankfurt": ("frankfurt", "eintracht frankfurt fc"),
        "borussiamonchengladbach": ("borussia mönchengladbach", "borussia monchengladbach", "gladbach"),
        "vflwolfsburg": ("wolfsburg", "vfl wolfsburg"),
        "vfb stuttgart": ("stuttgart", "vfb stuttgart"),
        "scfreiburg": ("freiburg", "sc freiburg"),
        "tsg1899hoffenheim": ("hoffenheim", "tsg hoffenheim", "tsg 1899 hoffenheim"),
        "fcaugsburg": ("augsburg", "fc augsburg"),
        "fsvmainz05": ("mainz 05", "1 fsv mainz 05", "mainz"),
        "fckoln": ("fc köln", "1 fc köln", "1 fc koln", "cologne", "köln", "koln"),
        "fcunionberlin": ("union berlin", "1 fc union berlin", "1. fc union berlin"),
        "svwerderbremen": ("werder bremen", "sv werder bremen"),
        "hamburgersv": ("hamburg", "hamburger sv", "hsv"),
        "sc paderborn 07": ("paderborn", "sc paderborn", "sc paderborn 07"),
        "fcschalke04": ("schalke 04", "fc schalke 04"),
        "svelversberg": ("elversberg", "sv 07 elversberg", "sv elversberg"),
    },
    "laliga": {
        "realmadrid": ("real madrid cf", "real madrid club de futbol"),
        "fcbarcelona": ("barcelona", "barça", "fc barcelona"),
        "atleticodemadrid": ("atletico madrid", "atlético madrid", "atletico de madrid"),
        "athleticclub": ("athletic bilbao", "athletic club bilbao"),
        "realsociedad": ("real sociedad de futbol", "real sociedad"),
        "realbetis": ("real betis balompie", "betis"),
        "villarreal": ("villarreal cf",),
        "valencia": ("valencia cf",),
        "sevilla": ("sevilla fc",),
        "deportivoalaves": ("alaves", "deportivo alavés"),
        "rcdespanyol": ("espanyol", "rcd espanyol"),
        "rcdmallorca": ("mallorca", "rcd mallorca"),
        "celta de vigo": ("celta vigo", "rc celta de vigo", "celta"),
        "osasuna": ("ca osasuna",),
        "getafe": ("getafe cf",),
        "girona": ("girona fc",),
    },
    "seriea": {
        "internazionale": ("inter milan", "inter", "fc internazionale milano", "inter milano"),
        "milan": ("ac milan", "associazione calcio milan"),
        "juventus": ("juventus fc", "juve"),
        "napoli": ("ssc napoli", "s s c napoli"),
        "roma": ("as roma", "a s roma"),
        "lazio": ("ss lazio", "s s lazio"),
        "atalanta": ("atalanta bc", "atalanta bergamasca calcio"),
        "fiorentina": ("acf fiorentina", "ac fiorentina"),
        "bologna": ("bologna fc",),
        "torino": ("torino fc",),
        "genoa": ("genoa cfc",),
        "udinese": ("udinese calcio",),
        "hellasverona": ("verona", "hellas verona fc"),
        "parma": ("parma calcio",),
        "como": ("como 1907",),
        "lecce": ("us lecce",),
    },
    "ligue1": {
        "parissaintgermain": ("paris saint-germain", "paris st germain", "psg", "paris saint germain"),
        "olympiquedemarseille": ("marseille", "olympique marseille"),
        "olympiquelyonnais": ("lyon", "olympique lyonnais"),
        "asmonaco": ("monaco", "as monaco fc"),
        "losclille": ("lille", "lille osc"),
        "ogcnice": ("nice", "ogc nice"),
        "rcstrasbourg": ("strasbourg", "rc strasbourg alsace"),
        "staderennais": ("rennes", "stade rennais fc"),
        "rclens": ("lens", "rc lens"),
        "stadedereims": ("reims", "stade de reims"),
        "toulouse": ("toulouse fc",),
        "fc nantes": ("nantes", "fc nantes"),
        "montpellier": ("montpellier hsc",),
        "brest": ("stade brestois", "stade brestois 29"),
    },
}


def alias_index():
    index = {}
    for league, dictionary in ALIASES.items():
        league_map = {}
        for canonical, alternatives in dictionary.items():
            c = folded(canonical)
            for spell in (canonical, *alternatives):
                f = folded(spell)
                if not f:
                    raise ValueError("BLANK_TEAM_ALIAS")
                prior = league_map.get(f)
                if prior is not None and prior != c:
                    raise ValueError("AMBIGUOUS_CURATED_ALIAS_" + league + "_" + f)
                league_map[f] = c
        index[league] = league_map
    return index


INDEX = alias_index()


def team_id(league, name):
    value = folded(name)
    if not value or not isinstance(league, str):
        return ""
    return INDEX.get(league, {}).get(value, value)


def same_team(league, first, second):
    a, b = team_id(league, first), team_id(league, second)
    return bool(a and b and a == b)
