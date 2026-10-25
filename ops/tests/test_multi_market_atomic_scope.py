"""Ambiguous raw source scopes cannot be stitched into plausible quote groups."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_quote_gate import extract

NOW = '2026-10-25T12:00:00Z'


def fixture():
    return {'id':'native-event','sport_key':'soccer_epl','home_team':'Home','away_team':'Away',
            'commence_time':'2026-10-25T16:00:00Z','bookmakers':[{'key':'book-a','markets':[
                {'key':'h2h','last_update':NOW,'outcomes':[
                    {'name':'Home','price':2.1},{'name':'Draw','price':3.1},{'name':'Away','price':3.2}]},
                {'key':'spreads','last_update':NOW,'outcomes':[
                    {'name':'Home','point':-.25,'price':1.9},{'name':'Away','point':.25,'price':1.95}]},
                {'key':'totals','last_update':NOW,'outcomes':[
                    {'name':'Over','point':2.5,'price':1.9},{'name':'Under','point':2.5,'price':1.95}]}]}]}


def run(events):
    return extract(events,captured_utc=NOW,league='soccer_epl',home='Home',away='Away')


class MultiMarketAtomicScopeTests(unittest.TestCase):
    def test_valid_three_markets_and_input_unchanged(self):
        payload=[fixture()];before=copy.deepcopy(payload)
        result=run(payload)
        self.assertEqual(result['quotes_accepted'],7)
        self.assertEqual(result['pre_match_quote_observations'],7)
        self.assertEqual(payload,before)
        self.assertEqual(result['production_recommendations'],'DISABLED')
        self.assertFalse(result['executable_bookmaker_price_verified'])

    def test_every_duplicate_event_copy_is_quarantined_in_any_order(self):
        first=fixture();other=copy.deepcopy(first)
        other['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=2.9
        for payload in ([first,other],[other,first]):
            result=run(payload)
            self.assertEqual(result['quotes_accepted'],0)
            self.assertEqual(result['matched_events'],0)
            self.assertEqual(result['reject_reasons'],{'DUPLICATE_EVENT_ID':2})
        # Another namespace/team claim cannot make a repeated native ID unique.
        other['home_team']='Other'
        self.assertEqual(run([first,other])['quotes_accepted'],0)
        other['home_team']='Home';other['sport_key']='soccer_other'
        self.assertEqual(run([first,other])['quotes_accepted'],0)

    def test_duplicate_bookmaker_isolated_other_book_is_preserved(self):
        event=fixture();duplicate=copy.deepcopy(event['bookmakers'][0])
        good=copy.deepcopy(duplicate);good['key']='book-b'
        event['bookmakers'] += [duplicate,good]
        result=run([event])
        self.assertEqual(result['quotes_accepted'],7)
        self.assertEqual({q['bookmaker'] for q in result['quotes']},{'book-b'})
        self.assertEqual(result['reject_reasons'],{'DUPLICATE_BOOKMAKER':2})

    def test_duplicate_market_blocks_isolate_all_copies_and_keep_other_markets(self):
        event=fixture();markets=event['bookmakers'][0]['markets']
        duplicate=copy.deepcopy(markets[2]);duplicate['last_update']='2026-10-25T11:59:30Z'
        duplicate['outcomes'][0]['price']=1.8;markets.append(duplicate)
        result=run([event])
        self.assertEqual(result['quotes_accepted'],5)
        self.assertNotIn('totals',{q['market'] for q in result['quotes']})
        self.assertEqual(result['reject_reasons'],{'DUPLICATE_MARKET':2})

    def test_split_partial_markets_cannot_be_combined_across_duplicate_blocks(self):
        event=fixture();markets=event['bookmakers'][0]['markets']
        first=copy.deepcopy(markets[2]);second=copy.deepcopy(first)
        first['outcomes']=first['outcomes'][:1];second['outcomes']=second['outcomes'][1:]
        second['last_update']='2026-10-25T11:59:00Z'
        event['bookmakers'][0]['markets']=[first,second]
        for blocks in ([first,second],[second,first]):
            event['bookmakers'][0]['markets']=blocks
            result=run([event])
            self.assertEqual(result['quotes_accepted'],0)
            self.assertEqual(result['reject_reasons'],{'DUPLICATE_MARKET':2})

    def test_duplicate_outcome_contaminates_entire_line_even_if_price_invalid(self):
        for price in (1.88,True,float('nan'),10**400):
            with self.subTest(price_type=type(price).__name__):
                event=fixture();market=event['bookmakers'][0]['markets'][2]
                duplicate=copy.deepcopy(market['outcomes'][0]);duplicate['price']=price
                market['outcomes'].append(duplicate)
                result=run([event])
                self.assertEqual(result['quotes_accepted'],5)
                self.assertEqual(result['reject_reasons'],{'DUPLICATE_QUOTE':3})

    def test_h2h_duplicate_quarantines_all_three_sides(self):
        event=fixture();market=event['bookmakers'][0]['markets'][0]
        market['outcomes'].append(copy.deepcopy(market['outcomes'][0]))
        result=run([event])
        self.assertEqual(result['quotes_accepted'],4)
        self.assertEqual(result['reject_reasons'],{'DUPLICATE_QUOTE':4})

    def test_accepted_quarter_precision_uses_same_group_identity(self):
        event=fixture();market=event['bookmakers'][0]['markets'][2]
        market['outcomes'].append(dict(market['outcomes'][0],point=2.5000000001,price=False))
        result=run([event])
        self.assertEqual(result['quotes_accepted'],5)
        self.assertEqual(result['reject_reasons'],{'DUPLICATE_QUOTE':3})

    def test_totals_bad_line_does_not_poison_other_legal_line(self):
        event=fixture();market=event['bookmakers'][0]['markets'][2]
        extra=[dict(q,point=3.5) for q in market['outcomes']]
        market['outcomes'].append(dict(market['outcomes'][0],price=1.8))
        market['outcomes']+=extra
        result=run([event])
        totals=[q for q in result['quotes'] if q['market']=='totals']
        self.assertEqual(len(totals),2)
        self.assertEqual({q['point'] for q in totals},{3.5})
        self.assertEqual(result['reject_reasons'],{'DUPLICATE_QUOTE':3})

    def test_signed_home_spread_lines_remain_separate(self):
        event=fixture();market=event['bookmakers'][0]['markets'][1]
        opposite=[dict(q,point=-q['point']) for q in market['outcomes']]
        market['outcomes'].append(dict(market['outcomes'][0],price=1.8))
        market['outcomes']+=opposite
        result=run([event])
        spreads=[q for q in result['quotes'] if q['market']=='spreads']
        self.assertEqual([(q['outcome'],q['point']) for q in spreads],[('Home',.25),('Away',-.25)])
        self.assertEqual(result['reject_reasons'],{'DUPLICATE_QUOTE':3})

    def test_multiple_valid_lines_survive_and_partial_diagnostics_remain(self):
        event=fixture();market=event['bookmakers'][0]['markets'][1]
        market['outcomes'] += [dict(q,point=-q['point']) for q in market['outcomes']]
        self.assertEqual(run([event])['quotes_accepted'],9)
        event=fixture();event['bookmakers'][0]['markets'][2]['outcomes'].pop()
        self.assertEqual(run([event])['quotes_accepted'],6)

    def test_malformed_counter_inputs_are_rejected_without_hashing_or_overflow(self):
        for point in ([],{},True,float('nan'),float('inf'),10**400):
            with self.subTest(point_type=type(point).__name__):
                event=fixture();event['bookmakers'][0]['markets'][2]['outcomes'][0]['point']=point
                result=run([event])
                self.assertEqual(result['reject_reasons'],{'INVALID_ASIAN_POINT':1})
                self.assertEqual(result['quotes_accepted'],6)
        for identity in ([],{},True,None):
            event=fixture();event['id']=identity
            self.assertEqual(run([event])['reject_reasons'],{'INVALID_EVENT_ID':1})
            event=fixture();event['bookmakers'][0]['key']=identity
            self.assertEqual(run([event])['reject_reasons'],{'INVALID_BOOKMAKER':1})
            event=fixture();event['bookmakers'][0]['markets'][2]['key']=identity
            self.assertEqual(run([event])['reject_reasons'],{'UNSUPPORTED_MARKET':1})

    def test_duplicate_group_outcome_order_does_not_change_survivors(self):
        event=fixture();market=event['bookmakers'][0]['markets'][2]
        market['outcomes'].append(dict(market['outcomes'][0],price=1.8))
        before=run([event]);market['outcomes'].reverse();after=run([event])
        self.assertEqual(before['quotes'],after['quotes'])
        self.assertEqual(before['reject_reasons'],after['reject_reasons'])


if __name__=='__main__':
    unittest.main()
