"""Legacy OpenLigaDB entrypoint lockdown regression, synthetic/no HTTP only."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from inplay_openligadb_one_shot import (
    main as legacy_main, capture_once, replay_saved,
)
from inplay_openligadb_league_pacing import paced_capture_once
from inplay_openligadb_conditional_capture import main as conditional_main

from test_inplay_openligadb_one_shot import EVENT_ID,NOW,URL,raw,fake_getter
from test_inplay_openligadb_conditional_capture import valid_match,match_getter


class LegacyHTTPRouteLockdownTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"private"
        self.root.mkdir(mode=0o700)

    def test_legacy_manual_cli_refuses_and_never_calls_old_pacer(self):
        output=io.StringIO()
        with patch("inplay_openligadb_league_pacing.paced_capture_once",
                   side_effect=AssertionError("OLD_PACER_MUST_NOT_RUN")) as paced:
            with patch("inplay_openligadb_one_shot._fetch_one",
                       side_effect=AssertionError("NO_HTTP")) as transport:
                with contextlib.redirect_stdout(output):
                    with self.assertRaises(SystemExit) as ended:
                        legacy_main(["--match-id",str(EVENT_ID),
                                     "--private-root",str(self.root),
                                     "--manual-one-shot"])
        self.assertEqual(ended.exception.code,2)
        report=json.loads(output.getvalue())
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["reason"],"LEGACY_FULL_MATCH_CLI_DISABLED")
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertEqual(report["certified_forward_samples"],0)
        self.assertFalse(report["eligible_for_model_input"])
        paced.assert_not_called()
        transport.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_legacy_manual_cli_cannot_gain_access_with_season_group_flags(self):
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                legacy_main(["--match-id",str(EVENT_ID),
                             "--private-root",str(self.root),"--manual-one-shot",
                             "--season","2026","--group-order","8"])
        self.assertEqual(stopped.exception.code,2)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_raw_capture_default_real_transport_is_disabled_even_with_valid_root(self):
        with patch("inplay_openligadb_one_shot._fetch_one",
                   side_effect=AssertionError("UNCONDITIONAL_GET_FORBIDDEN")) as transport:
            result=capture_once(EVENT_ID,self.root,now=lambda:NOW)
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["reason"],"DIRECT_HTTP_GET_DISABLED_USE_CONDITIONAL_CLI")
        self.assertEqual(result["production_recommendations"],"DISABLED")
        transport.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_legacy_shared_rate_wrapper_default_get_is_disabled_no_marker(self):
        with patch("inplay_openligadb_one_shot._fetch_one",
                   side_effect=AssertionError("NO_HTTP")) as transport:
            report=paced_capture_once(EVENT_ID,self.root,now=lambda:NOW)
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["reason"],"DIRECT_FULL_MATCH_FETCH_DISABLED")
        self.assertEqual(report["requests_attempted"],0)
        self.assertFalse(report["eligible_for_model_input"])
        transport.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_existing_injected_synthetic_raw_capture_still_works(self):
        calls=[]
        result=capture_once(EVENT_ID,self.root,getter=fake_getter(calls),
                            now=lambda:NOW)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertEqual(calls,[URL])
        self.assertTrue(result["local_original_response_bytes_readback_verified"])
        self.assertFalse(result["publisher_identity_authenticated"])
        self.assertEqual(result["certified_forward_samples"],0)
        replay=replay_saved(self.root,result["archive_sha256_unattested"],
                            now=NOW)
        self.assertEqual(replay["status"],"RESEARCH_ONLY")

    def test_existing_injected_synthetic_pacing_still_works(self):
        calls=[]
        result=paced_capture_once(EVENT_ID,self.root,
                                  getter=fake_getter(calls),now=lambda:NOW)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertEqual(calls,[URL])
        self.assertTrue(result["shared_host_league_pacing_applied"])
        self.assertFalse(result["source_authenticated"])

    def test_only_conditional_manual_entrypoint_dispatches_to_guarded_function(self):
        out=io.StringIO()
        deny={
            "status":"HOLD",
            "reason":"CHANGE_NOT_DEMONSTRATED",
            "production_recommendations":"DISABLED",
            "eligible_for_model_input":False,
            "certified_forward_samples":0,
        }
        with patch("inplay_openligadb_conditional_capture.conditional_capture_once",
                   return_value=deny) as conditional:
            with contextlib.redirect_stdout(out):
                with self.assertRaises(SystemExit) as ended:
                    conditional_main(["--match-id",str(EVENT_ID),
                                      "--season","2026","--group-order","8",
                                      "--private-root",str(self.root),
                                      "--manual-changed-only"])
        self.assertEqual(ended.exception.code,2)
        conditional.assert_called_once_with(EVENT_ID,2026,8,str(self.root))
        self.assertEqual(json.loads(out.getvalue())["reason"],"CHANGE_NOT_DEMONSTRATED")

    def test_conditional_manual_cli_rejects_old_flags_without_request(self):
        out=io.StringIO()
        with patch("inplay_openligadb_conditional_capture.conditional_capture_once",
                   side_effect=AssertionError("NOT_REACHED")) as conditional:
            with contextlib.redirect_stderr(out):
                with self.assertRaises(SystemExit) as ended:
                    conditional_main(["--match-id",str(EVENT_ID),
                                      "--private-root",str(self.root),
                                      "--manual-one-shot"])
        self.assertEqual(ended.exception.code,2)
        conditional.assert_not_called()

    def test_no_legacy_exit_can_promote_markets_odds_or_forecast(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit):
                legacy_main(["--match-id",str(EVENT_ID),
                             "--private-root",str(self.root),
                             "--manual-one-shot"])
        report=json.loads(output.getvalue())
        self.assertNotIn("odds",report)
        self.assertNotIn("roi",report)
        self.assertFalse(report["positive_ev_verified"])
        self.assertIsNone(report["recommendation"])


if __name__=="__main__":
    unittest.main()
