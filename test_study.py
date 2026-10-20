import unittest
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import numpy as np
from analyze import entry, sale, crosses_first, fee, prepare_round, TP, SL

class PaperExecutionTests(unittest.TestCase):
    def test_purchase_uses_opposite_bid_and_whole_contracts(self):
        # NO 70c bid implies a YES 30c ask; $1 buys three contracts.
        p,q,spent=entry({"no_dollars":[["0.70","100"]]},"yes",D(1),D(1))
        self.assertEqual((p,q,spent),(D(".30"),D(3),D(".9441")))
    def test_entry_cannot_exceed_displayed_depth(self):
        p,q,spent=entry({"no_dollars":[["0.99","2.4"]]},"yes",D(1),D(1))
        self.assertEqual(q,D(2))
    def test_sale_walks_book_and_charges_fees(self):
        net=sale({"yes_dollars":[["0.40","2"],["0.50","1"]]},"yes",D(3),D(1))
        self.assertEqual(net,D("1.2489"))
    def test_insufficient_liquidity_is_not_a_fill(self):
        self.assertIsNone(sale({"yes_dollars":[[".99","1"]]},"yes",D(3),D(1)))
    def test_take_profit_uses_purchase_gain_and_stop_uses_loss(self):
        bids=np.array([.29,.48,.07,.8])
        self.assertEqual(crosses_first(bids,np.array([.30*1.60,np.inf]),True).tolist(),[1,4])
        self.assertEqual(crosses_first(bids,np.array([.30*.25,-np.inf]),False).tolist(),[2,4])
    def test_fees_round_up_at_six_decimals(self):
        self.assertEqual(fee(D(1),D(".3333"),D(1)),D(".015555"))
    def test_full_replay_distinguishes_exit_gain_from_settlement_win(self):
        # A losing call can have a profitable early sale; execution is the NEXT book.
        r={"ticker":"KXBTC15M-TEST","open_ts":0,"close_ts":630,"call":{"side":"UP","sealed_at":600},"official":{"market":{"status":"finalized","result":"no"}},"fee_observation":{"fee_type":"quadratic","fee_multiplier":1}}
        rows=[]
        for t,bid in zip(range(600,630,5),[".29",".40",".48",".45",".07",".02"]):
            rows.append({"ts":t,"oracle_fetch":{"received_at":t,"requested_at":t},"window":{"secs_left":630-t},"call":{"side":"UP","sealed":True},"book_fetch":{"received_at":t},"book":{"yes_dollars":[[bid,"100"]],"no_dollars":[[".70","100"]]}})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"data/rounds").mkdir(parents=True)
            path=root/"data/rounds/KXBTC15M-TEST.jsonl"
            path.write_text("\n".join(json.dumps(x) for x in rows))
            value,reason=prepare_round(r,root,D(1))
            self.assertIsNone(reason)
            self.assertAlmostEqual(value["returned"][TP.index(60),SL.index(None)],1.2980)
            self.assertAlmostEqual(value["profit"][TP.index(60),SL.index(None)],.3539)
            self.assertEqual(value["exit_at"][TP.index(60),SL.index(None)],615)
            self.assertAlmostEqual(value["returned"][TP.index(None),SL.index(75)],.0558)
            self.assertEqual(value["returned"][0,0],0)
            self.assertFalse(value["settlement_won"])
            # An unobserved 25-second interval must invalidate the path.
            rows=rows[:1]+rows[-1:]
            path.write_text("\n".join(json.dumps(x) for x in rows))
            self.assertEqual(prepare_round(r,root,D(1))[1],"quote_gap_over_20s")

if __name__=="__main__":unittest.main()
