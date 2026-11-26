import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
import io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_historical_smoke import fetch,INDEX_LIMIT,MAX_BYTES,ROOT
from deep_handicap_league_runner import run
from deep_handicap_league_benchmark import parse,LEAGUES

class LeagueRunnerGuardTests(unittest.TestCase):
    def test_explicit_index_scope_only(self):
        with patch("deep_handicap_historical_smoke.build_opener") as opener:
            for path,limit,kw in [
                ("data/matches/2/27.json",INDEX_LIMIT,{}),
                ("data/matches/2/27.json",INDEX_LIMIT,{"league_indexes":1}),
                ("data/matches/2/27.json",INDEX_LIMIT,{"league_indexes":True,"full_group":True}),
                ("data/events/3857254.json",MAX_BYTES,{"league_indexes":True}),
                ("data/matches/2/28.json",INDEX_LIMIT,{"league_indexes":True})]:
                with self.assertRaises(ValueError):fetch(path,limit,**kw)
            opener.assert_not_called()
            res=opener.return_value.open.return_value.__enter__.return_value
            res.status=200
            res.geturl.return_value=ROOT+"data/matches/2/27.json"
            res.read.return_value=b"[]"
            self.assertEqual(fetch("data/matches/2/27.json",INDEX_LIMIT,league_indexes=True),b"[]")
            res.read.assert_called_once_with(INDEX_LIMIT+1)
    def test_runner_requires_expected_denominator_and_disabled(self):
        def result(raw,c):
            n,m=LEAGUES[c]
            return dict(reason="RETROSPECTIVE_HYPOTHETICAL_MARGIN_ONLY",private_metrics={},
                        train_count=n,holdout_count=m,evaluated_count=m,
                        production_recommendations="DISABLED",true_forward_sample_count=0)
        with patch("deep_handicap_league_runner.fetch",return_value=b"[]"),patch("deep_handicap_league_runner.evaluate",side_effect=result),redirect_stdout(io.StringIO()):
            self.assertEqual(run(),0)
        def bad(raw,c):
            r=result(raw,c);r["evaluated_count"]-=1;return r
        with patch("deep_handicap_league_runner.fetch",return_value=b"[]"),patch("deep_handicap_league_runner.evaluate",side_effect=bad),redirect_stdout(io.StringIO()):
            self.assertEqual(run(),1)
