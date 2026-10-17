import copy,unittest
from rul_benchmark.evaluation import evaluate,audit_split_manifest,paired_cell_bootstrap_mae
def row(c,t,y,p,**kw):
    return dict(physical_cell_id=c,dataset="fixture_only",role="test",query_cycle=t,true_rul_cycles=y,pred_rul_cycles=p,**kw)
class EvaluationContractTest(unittest.TestCase):
    def test_unequal_prefix_counts_do_not_overweight_one_cell(self):
        r=[row("a",1,99,109),row("a",2,98,108),row("a",3,97,107),row("b",1,49,49)]
        x=evaluate(r);self.assertEqual(x["cell_macro"]["MAE_cycles"],5);self.assertEqual(x["prefix_micro_MAE_cycles"],7.5)
    def test_exact_EOL_revision_and_overestimation(self):
        x=evaluate([row("a",10,90,100),row("a",20,80,80)])
        self.assertEqual(x["cell_macro"]["mean_abs_EOL_revision_cycles"],10)
        self.assertEqual(x["cell_macro"]["mean_positive_overestimate_cycles"],5)
        self.assertEqual(x["cell_macro"]["overestimate_rate"],0.5)
    def test_duplicate_query_and_inconsistent_EOL_rejected(self):
        for data in [[row("a",1,9,9),row("a",1,9,10)],[row("a",1,9,9),row("a",2,9,9)]]:
            with self.assertRaises(ValueError):evaluate(data)
    def test_role_leakage_and_unverified_identity_rejected(self):
        with self.assertRaises(ValueError):audit_split_manifest([dict(physical_cell_id="same",role="train",identity_audit="verified"),dict(physical_cell_id="same",role="test",identity_audit="verified")])
        with self.assertRaises(ValueError):audit_split_manifest([dict(physical_cell_id="x",role="train",identity_audit="unresolved")])
    def test_censoring_zero_and_nonfinite_rejected(self):
        for v in [0,float("nan"),float("inf"),-1]:
            with self.assertRaises(ValueError):evaluate([row("a",1,v,9)])
    def test_interval_contract_and_coverage(self):
        x=evaluate([row("a",1,9,9,lower_rul_cycles=8,upper_rul_cycles=10)])
        self.assertEqual(x["cell_macro"]["interval_coverage"],1)
        with self.assertRaises(ValueError):evaluate([row("a",1,9,9,lower_rul_cycles=8)])
    def test_paired_bootstrap_requires_same_queries(self):
        a=[row("a",1,9,8),row("b",1,19,18)]
        b=[row("a",1,9,7),row("b",1,19,17)]
        r=paired_cell_bootstrap_mae(a,b,n_resamples=100)
        self.assertEqual(r["mean"],-1);self.assertEqual(r["ci"],[-1,-1])
        b[0]["query_cycle"]=2
        with self.assertRaises(ValueError):paired_cell_bootstrap_mae(a,b,n_resamples=100)
    def test_explicit_single_role_and_no_silent_negative_clipping(self):
        a=[row("a",1,9,9),row("b",1,9,9)];a[1]["role"]="validation"
        with self.assertRaises(ValueError):evaluate(a)
        with self.assertRaises(ValueError):evaluate([row("a",1,9,-1)])
if __name__=="__main__":unittest.main()
