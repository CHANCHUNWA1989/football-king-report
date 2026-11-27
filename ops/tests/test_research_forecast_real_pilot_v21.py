import copy
import unittest
from ops.research_forecast_real_pilot_v21 import pins,REPO,REPO_ID,WORKFLOW

def example():
    return dict(id=123,run_attempt=1,path=WORKFLOW,head_branch="main",
        event="workflow_run",status="completed",conclusion="success",referenced_workflows=[],
        head_sha="a"*40,repository=dict(id=REPO_ID,full_name=REPO),
        head_repository=dict(id=REPO_ID,full_name=REPO))
class RunPinTests(unittest.TestCase):
    def test_direct_run(self):
        self.assertEqual(pins(example(),"123","1"),("a"*40,"a"*40))
    def test_reject_wrong_identity(self):
        for field,value in (("id",124),("run_attempt",2),("path","other.yml"),
              ("head_branch","research"),("event","pull_request"),("conclusion","failure"),
              ("referenced_workflows",[{}]),("head_sha","x"*40),
              ("head_repository",dict(id=1,full_name=REPO))):
            with self.subTest(field=field):
                m=example();m[field]=value
                with self.assertRaises(ValueError):pins(m,"123","1")
