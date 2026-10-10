"""Prove full research slate can be independently checked without cherry-picking."""
import csv
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops.verification_slate import build, publish, as_csv

NOW=datetime(2026,10,10,12,tzinfo=timezone.utc)

def inputs(n=35):
    prediction=(NOW-timedelta(minutes=2)).isoformat()
    previous=(NOW-timedelta(minutes=22)).isoformat()
    quoted=(NOW-timedelta(minutes=25)).isoformat()
    comps=[]
    for i in range(n):
        aligned=i%3!=0
        comps.append({
            "case_id":f"fixture-{i}",
            "league":("epl" if i<6 else "bundesliga"),
            "home":f"Club {i}", "away":f"Rival {i}",
            "kickoff_utc":(NOW+timedelta(days=2,hours=i)).isoformat(),
            "prediction_utc":prediction,
            "market_snapshot_utc":previous,"market_updated_utc":quoted,
            "model":[0.58,0.22,0.20],
            "market":[0.52,0.27,0.21] if aligned else [0.2,0.25,0.55],
            "result":None,"historical_outcome":None,"available_for_betting":False,
            "production_recommendations":"DISABLED",
        })
    shadow={"status":"SHADOW_ONLY","as_of_utc":prediction,
            "production_recommendations":"DISABLED"}
    pairing={"status":"RESEARCH_ONLY","comparisons":comps,
             "production_recommendations":"DISABLED"}
    status={"status":"RESEARCH_ONLY","production_recommendations":"DISABLED"}
    integrity={"schema":"football-king-fixture-integrity-v1",
               "status":"RESEARCH_ONLY","production_recommendations":"DISABLED",
               "blocked_from_research_recommendations":True,"disagreements":[]}
    market_status={"source_state":"RESEARCH_ONLY","quota":{"used":30,"remaining":470}}
    return shadow,pairing,status,market_status,integrity

class VerificationSlateTests(unittest.TestCase):
    def test_35_markets_produce_35_visible_presealed_predictions(self):
        r=build(*inputs(),now=NOW)
        self.assertEqual(r["verification_rows"],35)
        self.assertEqual(r["point_in_time_market_pairs"],35)
        self.assertEqual(r["a_research_directions"],23)
        self.assertEqual(r["b_verification_directions"],12)
        self.assertEqual(r["official_betting_recommendations"],0)
        self.assertEqual(r["value_recommendations"],[])
        self.assertTrue(all(v["settled_result"] is None and
                            v["bookmaker_decimal_odds"] is None and
                            v["production_recommendations"]=="DISABLED"
                            for v in r["rows"]))
        self.assertEqual(len({v["sealed_pick_digest"] for v in r["rows"]}),35)
        self.assertEqual(len([v for v in r["rows"] if v["league"]=="epl"]),6)

    def test_rejects_future_market_prices_and_duplicate(self):
        data=list(inputs(3))
        data[1]["comparisons"].append(dict(data[1]["comparisons"][0]))
        data[1]["comparisons"][1]["market_updated_utc"]=(NOW+timedelta(hours=2)).isoformat()
        r=build(*data,now=NOW)
        self.assertEqual(r["verification_rows"],2)
        self.assertGreater(r["source_diagnostics"]["invalid_or_expired_pairs"],0)

    def test_model_disagreement_is_explicit_b_not_hidden(self):
        r=build(*inputs(4),now=NOW)
        first=next(v for v in r["rows"] if v["case_id"]=="fixture-0")
        self.assertEqual(first["research_tier"],"B_VERIFICATION_ONLY")
        self.assertEqual(first["reason"],"MODEL_MARKET_DISAGREEMENT")
        self.assertEqual(first["direction"],"HOME")

    def test_invalid_source_or_hold_produces_zero(self):
        data=list(inputs(6))
        data[2]["status"]="HOLD"
        r=build(*data,now=NOW)
        self.assertEqual(r["verification_rows"],0)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_csv_formula_injection_escaped(self):
        data=list(inputs(1))
        data[1]["comparisons"][0]["home"]="=HYPERLINK(\"bad\")"
        result=build(*data,now=NOW)
        csv_text=as_csv(result)
        rows=list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["home"].startswith("'="))

    def test_render_and_durable_export(self):
        data=inputs(4)
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp)
            (site/"index.html").write_text(
                '<html><main><h2>近期賽程與賽果</h2></main></html>',
                encoding="utf-8")
            for name,content in zip(
                ("shadow.json","market_comparison.json","status.json",
                 "market_status.json","fixture_integrity.json"),data):
                (site/name).write_text(json.dumps(content),encoding="utf-8")
            report=publish(site,now=NOW)
            body=(site/"index.html").read_text(encoding="utf-8")
            self.assertIn('id="fk-verification-slate"',body)
            self.assertIn("英超",body)
            self.assertEqual(report["verification_rows"],4)
            self.assertEqual(json.loads((site/"verification_slate.json").read_text())["verification_rows"],4)
            self.assertEqual(len(list(csv.DictReader(
                io.StringIO((site/"verification_slate.csv").read_text(encoding="utf-8-sig"))))),4)
            with self.assertRaises(ValueError):
                publish(site,now=NOW)

if __name__=="__main__":
    unittest.main()
