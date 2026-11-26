import unittest
from unittest.mock import patch
from live_core_low_score_calibration import GRID,BASE,observations,assess,select,report,parse


class LowScoreCalibrationTests(unittest.TestCase):
    def test_grid_contract(self):
        self.assertEqual(len(GRID),15)
        self.assertIn(BASE,GRID)

    def test_same_date_no_leakage(self):
        rows=[("2020-09-01",f"H{i}",f"A{i}",1,1) for i in range(50)]
        rows += [("2020-09-02","H1","A1",0,0),("2020-09-02","H2","A2",2,1)]
        before=observations(rows)
        rows[-2]=("2020-09-02","H1","A1",9,0)
        after=observations(rows)
        self.assertEqual(len(before),2)
        self.assertEqual([r[:2] for r in before],[r[:2] for r in after])

    def test_overlap_rejected(self):
        rows=[("2020-09-01","A","B",1,0)]
        with self.assertRaisesRegex(ValueError,"TEMPORAL_OVERLAP"):
            report(rows,rows)

    def test_selection_and_pin_fail_closed(self):
        with self.assertRaises(ValueError):select([(1.,1.,0,0)])
        with self.assertRaises(ValueError):parse(b"{}","2020-21")
        with self.assertRaises(ValueError):assess([(1.,1.,0,0)],(2.,0.))

    def test_frozen_choice_and_hold(self):
        rows=[("2020-09-01","A","B",1,0)]
        later=[("2021-09-01","A","B",0,0)]
        with patch("live_core_low_score_calibration.observations",side_effect=[[(1.,1.,1,0)]*100,[(1.,1.,0,0)]]):
            with patch("live_core_low_score_calibration.select",return_value=BASE) as selection:
                r=report(rows,later)
        selection.assert_called_once()
        self.assertEqual(r["selected_config"],BASE)
        self.assertFalse(r["objective_improved"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["verified_forward_sample_credit"],0)
