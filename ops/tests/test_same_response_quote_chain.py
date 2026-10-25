"""Exercise the live collector/screener/public-summary path without network calls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from ops.all_market_private_feed import collect
from ops.all_market_screen import screen
from ops.private_artifact_guard import sanitize
from ops.private_summary_archive import prepare

NOW = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)


def response():
    return [{"id": "private-event-1", "sport_key": "soccer_epl",
             "home_team": "Private Home", "away_team": "Private Away",
             "commence_time": (NOW+timedelta(hours=2)).isoformat(),
             "bookmakers": [{"key": "private-book", "markets": [{
                 "key": "h2h", "last_update": (NOW-timedelta(seconds=30)).isoformat(),
                 "outcomes": [{"name":"Private Home","price":2.1234},
                              {"name":"Draw","price":3.4567},
                              {"name":"Private Away","price":4.5678}]}]}]}]


class SameResponseQuoteChainTests(unittest.TestCase):
    def collected(self, events=None):
        catalog={"quota":{"used":1,"remaining":499},
                 "supported":{"epl":True},"active":{"epl":True}}
        with patch('ops.all_market_private_feed.verify',return_value=catalog) as verify, \
             patch('ops.all_market_private_feed.retrieve',return_value=(response() if events is None else events,
                   {"used":2,"remaining":498})) as retrieve:
            doc=collect('synthetic-test-key',now=NOW)
        verify.assert_called_once()
        retrieve.assert_called_once()
        self.assertEqual(retrieve.call_args.kwargs['params']['markets'],'h2h')
        return doc

    def test_same_response_to_verified_content_screen_and_safe_archive(self):
        doc=self.collected()
        self.assertEqual(len(doc['quotes']),3)
        result=screen(doc,now=NOW)
        self.assertEqual(result['counts']['RESEARCH_ONLY'],3)
        self.assertEqual(result['quote_evidence_validation']['accepted_quotes'],3)
        self.assertFalse(result['quote_evidence_validation']['independently_verified'])
        # Exact existing workflow metadata propagation, then the real public guards.
        result.update(input_status=doc['collector_status'],coverage=doc['coverage'],
                      requested_markets=doc['requested_markets'])
        public=sanitize(result,{})
        merged,changed=prepare(None,public,now=NOW)
        self.assertTrue(changed)
        self.assertEqual(merged['counts']['RESEARCH_ONLY'],3)
        self.assertEqual(merged['counts']['VERIFIED_VALUE'],0)
        self.assertEqual(merged['production_recommendations'],'DISABLED')
        self.assertFalse(merged['quotes_are_executable'])
        serialized=json.dumps(merged)
        for private in ('private-event','private-book','Private Home','Private Away',
                        '2.1234','3.4567','4.5678','source_quote_id'):
            self.assertNotIn(private,serialized)
        for q in doc['quotes']:
            self.assertNotIn(q['evidence']['sha256'],serialized)

    def test_consumer_rejects_changes_between_collection_and_screen(self):
        original=self.collected()
        mutations={'decimal_odds':2.5,'selection':'Private Away','source':'other-book',
                   'fixture_id':'other-event','league':'championship','sport_key':'soccer_efl_champ',
                   'home':'other-home','away':'other-away','line':.25,
                   'observed_utc':(NOW-timedelta(seconds=20)).isoformat(),
                   'captured_utc':(NOW-timedelta(seconds=1)).isoformat(),
                   'kickoff_utc':(NOW+timedelta(hours=3)).isoformat(),
                   'quote_id_kind':'NATIVE', 'source_verified':True}
        for key,value in mutations.items():
            with self.subTest(field=key):
                doc=copy.deepcopy(original);doc['quotes'][0][key]=value
                out=screen(doc,now=NOW)
                self.assertEqual(out['counts']['RESEARCH_ONLY'],0)
                self.assertEqual(out['quote_evidence_validation']['accepted_quotes'],0)
                self.assertEqual(out['counts']['VERIFIED_VALUE'],0)
        forged=copy.deepcopy(original)
        forged['quotes'][0]['evidence']['independently_verified']=True
        self.assertEqual(screen(forged,now=NOW)['counts']['RESEARCH_ONLY'],0)

    def test_partial_duplicate_and_book_time_fallback_do_not_enter_chain(self):
        bad=[]
        partial=response();partial[0]['bookmakers'][0]['markets'][0]['outcomes'].pop();bad.append(partial)
        duplicate=response();duplicate.append(copy.deepcopy(duplicate[0]));bad.append(duplicate)
        missing_id=response();missing_id[0]['id']='';bad.append(missing_id)
        fallback=response();book=fallback[0]['bookmakers'][0]
        book['last_update']=book['markets'][0].pop('last_update');bad.append(fallback)
        for events in bad:
            with self.subTest(events=events):
                doc=self.collected(events)
                self.assertEqual(doc['quotes'],[])
                self.assertEqual(screen(doc,now=NOW)['counts']['RESEARCH_ONLY'],0)

    def test_stale_consumer_schema_and_forged_flags_do_not_pass_content_gate(self):
        doc=self.collected()
        self.assertEqual(screen(doc,now=NOW+timedelta(minutes=21))['counts']['RESEARCH_ONLY'],0)
        for change in ({'schema':'unrecognized'}, {'production_recommendations':'ENABLED'}):
            forged=dict(doc,**change)
            self.assertEqual(screen(forged,now=NOW)['counts']['RESEARCH_ONLY'],0)

    def test_legacy_screen_cli_remains_available(self):
        # A separate interpreter exercises imports as a file, not only as a package.
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'empty.json';dest=Path(directory)/'out.json'
            source.write_text('{"quotes": []}')
            completed=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'all_market_screen.py'),
                                      '--input',str(source),'--output',str(dest)],
                                     cwd=directory,capture_output=True,text=True,timeout=10)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(json.loads(dest.read_text())['counts']['VERIFIED_VALUE'],0)

    def test_missing_evidence_cannot_downgrade_new_rows_into_legacy_input(self):
        doc=self.collected()
        del doc['schema'];del doc['source']
        for quote in doc['quotes']:
            del quote['evidence']
        out=screen(doc,now=NOW)
        self.assertEqual(out['status'],'HOLD')
        self.assertEqual(out['counts']['RESEARCH_ONLY'],0)
        self.assertEqual(out['quote_evidence_validation']['accepted_quotes'],0)


if __name__=='__main__':
    unittest.main()
