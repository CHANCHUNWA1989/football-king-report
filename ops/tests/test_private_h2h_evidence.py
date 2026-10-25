"""Offline same-response complete h2h binding; no network or real odds."""
import copy
from datetime import datetime, timedelta, timezone
import importlib
import unittest
from unittest.mock import patch

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def event():
    return {"id":"synthetic-e1", "sport_key":"soccer_epl",
            "home_team":"Home", "away_team":"Away",
            "commence_time":(NOW+timedelta(hours=2)).isoformat(),
            "bookmakers":[{"key":"synthetic-book", "markets":[
                {"key":"h2h", "last_update":(NOW-timedelta(minutes=2)).isoformat(),
                 "outcomes":[{"name":"Home","price":2.1},
                             {"name":"Draw","price":3.3},
                             {"name":"Away","price":3.4}]}]}]}


class PrivateH2HEvidenceTests(unittest.TestCase):
    def api(self):
        return importlib.import_module('ops.private_h2h_evidence')

    def bind(self, events=None, **kwargs):
        return self.api().bind_response([event()] if events is None else events,
                                       league='epl',sport='soccer_epl',captured=NOW,**kwargs)

    def test_complete_response_binds_all_three_sides_without_mutating(self):
        events=[event()];saved=copy.deepcopy(events)
        result=self.bind(events)
        self.assertEqual(len(result['quotes']),3)
        self.assertEqual(result['rejected'],{})
        accepted,rejected=self.api().verify_bound_quotes(result['quotes'],now=NOW)
        self.assertEqual(accepted,result['quotes']);self.assertEqual(rejected,{})
        self.assertEqual(events,saved)
        self.assertTrue(all(q['source_verified'] is False for q in accepted))
        self.assertTrue(all(q['quote_id_kind']=='DERIVED_COMPOSITE_NOT_PROVIDER_NATIVE' for q in accepted))
        self.assertTrue(all(q['evidence']['independently_verified'] is False for q in accepted))

    def test_bad_arguments_raise_before_binding(self):
        for captured in (None,False,NOW.replace(tzinfo=None),'2026-10-25'):
            with self.subTest(captured=captured), self.assertRaises(ValueError):
                self.api().bind_response([event()],league='epl',sport='soccer_epl',captured=captured)
        with self.assertRaises(ValueError):
            self.api().bind_response([event()],league='epl',sport='wrong',captured=NOW)

    def test_incomplete_ambiguous_or_nonstandard_market_yields_no_rows(self):
        base=event()
        cases=[]
        for outcomes in ([{'name':'Home','price':2}],
                         [{'name':'Home','price':2},{'name':'Draw','price':3},{'name':'Other','price':4}],
                         base['bookmakers'][0]['markets'][0]['outcomes']*2):
            x=copy.deepcopy(base);x['bookmakers'][0]['markets'][0]['outcomes']=outcomes;cases.append(x)
        x=copy.deepcopy(base);x['bookmakers'][0]['markets'][0]['outcomes'][0]['point']=0;cases.append(x)
        x=copy.deepcopy(base);x['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=True;cases.append(x)
        x=copy.deepcopy(base);x['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=float('nan');cases.append(x)
        for x in cases:
            with self.subTest(case=x):self.assertEqual(self.bind([x])['quotes'],[])

    def test_market_clock_required_and_strictly_not_future(self):
        for update in (None,NOW+timedelta(microseconds=1),NOW-timedelta(minutes=20,microseconds=1)):
            x=event();m=x['bookmakers'][0]['markets'][0]
            if update is None:del m['last_update']
            else:m['last_update']=update.isoformat()
            x['bookmakers'][0]['last_update']=NOW.isoformat()
            self.assertEqual(self.bind([x])['quotes'],[])
        x=event();x['bookmakers'][0]['markets'][0]['last_update']=(NOW-timedelta(minutes=20)).isoformat()
        self.assertEqual(len(self.bind([x])['quotes']),3)

    def test_exact_source_identity_and_duplicate_events_quarantined(self):
        for changes in ({'id':''},{'id':1},{'sport_key':'other'},{'sport_key':None},
                        {'home_team':'Away'},{'home_team':' '}):
            x=event();x.update(changes);self.assertEqual(self.bind([x])['quotes'],[])
        self.assertEqual(self.bind([event(),event()])['quotes'],[])

    def test_duplicate_book_or_h2h_market_cannot_leave_first_wins(self):
        x=event();x['bookmakers']*=2;self.assertEqual(self.bind([x])['quotes'],[])
        x=event();x['bookmakers'][0]['markets']*=2;self.assertEqual(self.bind([x])['quotes'],[])

    def test_scope_limits_do_not_truncate_into_positive(self):
        self.assertEqual(self.bind([event()]*501)['quotes'],[])
        x=event();x['bookmakers']*=101;self.assertEqual(self.bind([x])['quotes'],[])
        x=event();x['bookmakers'][0]['markets'] += [{'key':'other'}]*20
        self.assertEqual(self.bind([x])['quotes'],[])

    def test_kickoff_window_boundaries(self):
        for delta in (timedelta(minutes=10),timedelta(days=7),timedelta(seconds=-1)):
            x=event();x['commence_time']=(NOW+delta).isoformat()
            self.assertEqual(self.bind([x])['quotes'],[])
        x=event();x['commence_time']=(NOW+timedelta(minutes=10,microseconds=1)).isoformat()
        self.assertEqual(len(self.bind([x])['quotes']),3)

    def test_each_row_semantic_tamper_cannot_leave_accepted_group(self):
        rows=self.bind()['quotes'];saved=copy.deepcopy(rows)
        changes={'fixture_id':'other','league':'laliga','sport_key':'soccer_spain_la_liga',
                 'home':'Other','away':'Other','source':'other-book','provider':'other',
                 'market':'spreads','selection':'Other','line':.25,'decimal_odds':2.2,
                 'observed_utc':(NOW-timedelta(minutes=3)).isoformat(),
                 'captured_utc':(NOW-timedelta(seconds=1)).isoformat(),
                 'kickoff_utc':(NOW+timedelta(hours=3)).isoformat(),
                 'source_verified':True,'independently_calibrated':True,
                 'lineup_checked':True,'quote_id_kind':'NATIVE'}
        for k,v in changes.items():
            changed=copy.deepcopy(rows);changed[0][k]=v
            with self.subTest(field=k):
                accepted,_=self.api().verify_bound_quotes(changed,now=NOW)
                self.assertEqual(accepted,[])
        self.assertEqual(rows,saved)

    def test_evidence_tamper_duplicates_and_missing_sides_fail_closed(self):
        rows=self.bind()['quotes']
        for edit in ('hash','flag','extra'):
            changed=copy.deepcopy(rows)
            if edit=='hash':changed[0]['evidence']['sha256']='0'*64
            elif edit=='flag':changed[0]['evidence']['independently_verified']=True
            else:changed[0]['evidence']['caller_approved']=True
            self.assertEqual(self.api().verify_bound_quotes(changed,now=NOW)[0],[])
        self.assertEqual(self.api().verify_bound_quotes(rows[:2],now=NOW)[0],[])
        self.assertEqual(self.api().verify_bound_quotes(rows+[rows[0]],now=NOW)[0],[])

    def test_consumer_rechecks_now_age_and_kickoff(self):
        rows=self.bind()['quotes']
        for now in (NOW-timedelta(microseconds=1),NOW+timedelta(minutes=19),NOW+timedelta(hours=3)):
            self.assertEqual(self.api().verify_bound_quotes(rows,now=now)[0],[])
        self.assertEqual(len(self.api().verify_bound_quotes(rows,now=NOW+timedelta(minutes=18))[0]),3)

    def test_one_bad_scope_does_not_poison_unrelated_complete_fixture(self):
        bad=event();bad['id']='bad';bad['bookmakers'][0]['markets'][0]['outcomes'].pop()
        result=self.bind([bad,event()]);self.assertEqual(len(result['quotes']),3)
        self.assertTrue(result['rejected'])

    def test_numeric_boolean_equivalents_do_not_fake_false_evidence(self):
        rows=self.bind()['quotes']
        for value in (0,0.0,None,'false',True):
            changed=copy.deepcopy(rows);changed[0]['evidence']['independently_verified']=value
            self.assertEqual(self.api().verify_bound_quotes(changed,now=NOW)[0],[])

    def test_extreme_malformed_and_wrong_types_reject_without_unexpected_exceptions(self):
        for value in (10**400,float('inf'),False,'2.0',None):
            x=event();x['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=value
            self.assertEqual(self.bind([x])['quotes'],[])
        for field in ('commence_time',):
            x=event();x[field]=datetime(1,1,1,tzinfo=timezone(timedelta(hours=14)))
            self.assertEqual(self.bind([x])['quotes'],[])
        x=event();x['bookmakers'][0]['markets'][0]['last_update']='0001-01-01T00:00:00+14:00'
        self.assertEqual(self.bind([x])['quotes'],[])
        for rows in (None,{},'bad'):
            self.assertEqual(self.api().verify_bound_quotes(rows,now=NOW)[0],[])

    def test_distinct_complete_books_survive_bad_book_and_utc_equivalent_strings_verify(self):
        x=event();bad=copy.deepcopy(x['bookmakers'][0]);bad['key']='bad';bad['markets'][0]['outcomes'].pop()
        x['bookmakers'].append(bad)
        result=self.bind([x]);self.assertEqual(len(result['quotes']),3)
        rows=result['quotes'];saved=copy.deepcopy(rows)
        for row in rows:
            for field in ('observed_utc','captured_utc','kickoff_utc'):
                row[field]=datetime.fromisoformat(row[field]).astimezone(timezone(timedelta(hours=8))).isoformat()
        self.assertEqual(len(self.api().verify_bound_quotes(rows,now=NOW)[0]),3)
        self.assertNotEqual(rows,saved)

    def test_consumer_unknown_metadata_and_non_json_clocks_are_not_silently_ignored(self):
        rows=self.bind()['quotes']
        changed=copy.deepcopy(rows);changed[0]['unbound_metadata']='not accepted'
        self.assertEqual(self.api().verify_bound_quotes(changed,now=NOW)[0],[])
        for key in ('observed_utc','captured_utc','kickoff_utc'):
            changed=copy.deepcopy(rows);changed[0][key]=datetime.fromisoformat(changed[0][key])
            self.assertEqual(self.api().verify_bound_quotes(changed,now=NOW)[0],[])

    def test_global_capacity_rejects_complete_response_or_aggregate_wholesale(self):
        rows=self.bind()['quotes']
        with patch.object(self.api(),'MAX_ROWS',2):
            self.assertEqual(self.bind()['quotes'],[])
            self.assertEqual(self.api().verify_bound_quotes(rows,now=NOW)[0],[])


if __name__=='__main__':unittest.main()
