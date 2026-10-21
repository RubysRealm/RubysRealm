import json
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from analyze import run
from live_analysis import build_input, recent_beneficial, rank_summary, TP, SL
from collect import status

class RollingTests(unittest.TestCase):
    def test_profit_optimal_cap_skips_loss_and_average_uses_only_purchases(self):
        items=[{'price':price,'spent_units':spent,
                'returned_units':[returned]*(len(TP)*len(SL))}
            for price,spent,returned in ((.2,10200,20000),(.3,9300,15000),(.9,9200,0))]
        best=rank_summary(items,0,900)['best']
        self.assertEqual(best['max_buy_cents'],30)
        self.assertEqual(best['average_entry_cents'],25)
        self.assertEqual(best['skipped_by_cap'],1)
        self.assertEqual(best['purchases'],2)
        self.assertEqual(best['net_profit'],1.55)
        # Taking only the 20-cent entry has higher ROI but less total profit.
        self.assertLess(best['roi_pct'],(20000-10200)/10200*100)

    def state(self):
        return {"study_start":0,"study_stop":144000,"last_observation":159990,
            "rounds":{},"samples":0,"error_count":0}

    def test_end_is_current_second_even_after_original_stop_and_without_settlements(self):
        state=self.state()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'state.json').write_text(json.dumps(state))
            a=run(root,Decimal(1),now=160001)
            b=run(root,Decimal(1),now=160002)
        from datetime import datetime
        for i,h in enumerate((12,24,36)):
            p=a['periods'][i];q=b['periods'][i]
            self.assertEqual(datetime.fromisoformat(p['end']).timestamp(),160001)
            self.assertEqual(datetime.fromisoformat(p['start']).timestamp(),160001-h*3600)
            self.assertEqual(datetime.fromisoformat(q['start']).timestamp()-datetime.fromisoformat(p['start']).timestamp(),1)
            self.assertEqual(p['included_call_opportunities'],0)

    def test_pending_is_excluded_future_rounds_never_prepared(self):
        state=self.state()
        state['rounds']={str(t):{'ticker':str(t),'open_ts':t-900,'close_ts':t} for t in (1000,159300,160200)}
        with patch('live_analysis.prepare_round',return_value=(None,'unverified_settlement')) as prepare:
            data=build_input(Path('.'),state,now=160001)
        self.assertEqual([r['close_ts'] for r in data['rounds']],[159300])
        self.assertEqual(prepare.call_count,2)
        self.assertEqual(data['all_time']['observed_rounds'],2)
        self.assertEqual(data['rounds'][0]['excluded'],'unverified_settlement')
        self.assertEqual(data['as_of'],160001)

    def test_continuous_status_has_no_fixed_stop(self):
        state=self.state();state.update(study_stop=None,mode='rolling')
        with patch('collect.time.time',return_value=160001):
            s=status(state,True)
        self.assertEqual(s['mode'],'rolling')
        self.assertIsNone(s['study_stop'])
        self.assertGreater(s['hours_elapsed'],40)

    def test_recent_beneficial_keeps_five_distinct_profitable_setups_without_refresh_duplicates(self):
        def period(caps):
            return [{'hours':12,'start':0,'end':43200,'top_setups':[{'max_buy_cents':c,
                'take_profit_gain_pct':40,'stop_loss_pct':20,'net_profit':c-10} for c in caps]}]
        history,active=recent_beneficial(period([10,20,30,40,50,60]),{},43200)
        self.assertEqual(len(history),5)
        self.assertTrue(all(x['net_profit']>0 for x in history))
        old={'recent_beneficial':history,'beneficial_active_keys':active}
        same,_=recent_beneficial(period([10,20,30,40,50,60]),old,43201)
        self.assertEqual(same,history)
        new,_=recent_beneficial(period([70,20,30,40,50]),old,44100)
        self.assertEqual(new[0]['max_buy_cents'],70)
        self.assertEqual(new[0]['identified_at'],44100)
        self.assertEqual(len(new),5)
        self.assertEqual(len({x['key'] for x in new}),5)

if __name__=='__main__':unittest.main()
