"""Reuse one ambiguity quarantine contract through actual multi-market consumers."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_quote_gate import extract
from private_multi_market_audit import audit
from verified_market_pipeline import analyze as pipeline
from integrated_market_consensus import analyze as consensus
from opt_in_multi_market_sample import collect_sample

CAPTURE='2026-10-25T12:00:00Z'
NOW=datetime(2026,10,25,12,tzinfo=timezone.utc)


def fixture():
    return {'id':'private-event','sport_key':'soccer_epl','home_team':'Home','away_team':'Away',
            'commence_time':'2026-10-25T16:00:00Z','bookmakers':[{'key':'private-book','markets':[
                {'key':'h2h','last_update':CAPTURE,'outcomes':[
                    {'name':'Home','price':2.1},{'name':'Draw','price':3.2},{'name':'Away','price':3.4}]},
                {'key':'spreads','last_update':CAPTURE,'outcomes':[
                    {'name':'Home','point':-.25,'price':1.9},{'name':'Away','point':.25,'price':1.95}]},
                {'key':'totals','last_update':CAPTURE,'outcomes':[
                    {'name':'Over','point':2.5,'price':1.9},{'name':'Under','point':2.5,'price':1.95}]}]}]}


def case():
    return {'fixture':{'event_id':'private-event','league':'soccer_epl','home':'Home','away':'Away'}}


def split_books():
    event=fixture();first=copy.deepcopy(event['bookmakers'][0]);second=copy.deepcopy(first)
    for left,right in zip(first['markets'],second['markets']):
        left['outcomes']=left['outcomes'][:-1];right['outcomes']=right['outcomes'][-1:]
        right['last_update']='2026-10-25T11:59:30Z'
    event['bookmakers']=[first,second]
    return event


class MultiMarketScopeConsumerTests(unittest.TestCase):
    def test_complete_markets_remain_counted_and_private(self):
        result=audit([fixture()],CAPTURE)
        self.assertEqual(result['complete_prematch_bookmaker_lines_by_market'],
                         {'h2h':1,'spreads':1,'totals':1})
        for forbidden in ('private-book','private-event','decimal_odds','1.95'):
            self.assertNotIn(forbidden,json.dumps(result))
        self.assertFalse(result['independent_model_ev_verified'])
        self.assertEqual(result['production_recommendations'],'DISABLED')

    def test_different_blocks_cannot_be_spliced_into_complete_markets(self):
        book_event=split_books()
        market_event=copy.deepcopy(book_event)
        a,b=market_event['bookmakers'];a['markets']+=b['markets'];market_event['bookmakers']=[a]
        for event in (book_event,market_event):
            for reverse in (False,True):
                candidate=copy.deepcopy(event)
                if reverse:
                    candidate['bookmakers'].reverse()
                    for book in candidate['bookmakers']:
                        book['markets'].reverse()
                data=[candidate]
                result=audit(data,CAPTURE)
                self.assertEqual(result['complete_prematch_bookmaker_lines_by_market'],
                                 {'h2h':0,'spreads':0,'totals':0})
                self.assertEqual(result['status'],'HOLD')
                downstream=pipeline(case(),data,now=NOW)
                self.assertEqual(downstream['matched_verified_quotes'],0)
                self.assertFalse(downstream['decision']['gate_checks']['market_validated'])
                self.assertEqual(consensus(case(),data,now=NOW)['research_consensus_groups'],0)

    def test_conflicting_extra_side_invalidates_whole_line(self):
        for index in range(3):
            event=fixture();market=event['bookmakers'][0]['markets'][index]
            extra=copy.deepcopy(market['outcomes'][0]);extra['price']=1.888
            market['outcomes'].append(extra)
            result=audit([event],CAPTURE)
            self.assertEqual(result['complete_prematch_bookmaker_lines_by_market'][market['key']],0)

    def test_distinct_signed_home_lines_are_not_collapsed(self):
        event=fixture();spread=event['bookmakers'][0]['markets'][1]
        spread['outcomes'] += [{'name':'Home','point':.25,'price':1.95},
                               {'name':'Away','point':-.25,'price':1.9}]
        result=audit([event],CAPTURE)
        self.assertEqual(result['complete_prematch_bookmaker_lines_by_market']['spreads'],2)
        spread['outcomes'].append({'name':'Home','point':-.25,'price':1.8})
        result=audit([event],CAPTURE)
        self.assertEqual(result['complete_prematch_bookmaker_lines_by_market']['spreads'],1)

    def test_opt_in_sampler_uses_same_gate_without_new_requests(self):
        catalog={'quota':{'used':100,'remaining':250},'supported':{'epl':True},'active':{'epl':True}}
        with patch('opt_in_multi_market_sample.verify',return_value=catalog) as verify, \
             patch('opt_in_multi_market_sample.retrieve',return_value=([split_books()],
                   {'used':103,'remaining':247,'last':3})) as retrieve:
            result=collect_sample('synthetic-key','epl',now=NOW)
        verify.assert_called_once();retrieve.assert_called_once()
        self.assertEqual(retrieve.call_args.kwargs['params']['markets'],'h2h,spreads,totals')
        self.assertEqual(result['complete_prematch_bookmaker_lines_by_market'],
                         {'h2h':0,'spreads':0,'totals':0})
        self.assertFalse(result['raw_prices_persisted'])
        self.assertEqual(result['production_recommendations'],'DISABLED')


if __name__=='__main__':
    unittest.main()
