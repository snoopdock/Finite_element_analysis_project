import base64
import unittest
from audit_engine.semantic_audit.ae32c.github_publication import GitHubAPIError, GitHubRefCASStore
from audit_engine.semantic_audit.ae32c.publication import _empty, build_run_record, digest

REPO="snoopdock/Finite_element_analysis_project"
SOURCE="a"*40
OTHER="b"*40

def make_record(n=1, revision=SOURCE, outcome="SUCCEEDED"):
    return build_run_record(repository=REPO, source_revision=revision,
        source_snapshot_id="1"*64, graph_snapshot_id="2"*64,
        rule_registry_sha256="3"*64, finding_ledger_sha256="4"*64,
        configuration_sha256="5"*64, workflow_run_id=n,
        run_number=n, run_attempt=1, outcome=outcome)

class FakeGitHub:
    def __init__(self):
        self.refs={"heads/stage1/section-uuids":SOURCE}
        self.commits={SOURCE:{"tree":{"sha":"ts"}}}
        self.trees={"ts":[]}; self.blobs={}; self.i=0
        self.fail_patch=False; self.move_source=None
    def ident(self,p):
        self.i+=1; return p+str(self.i)
    def request(self,m,p,b=None):
        root="/repos/"+REPO
        if p.startswith(root+"/git/ref/heads/"):
            ref=p[len(root+"/git/ref/"):]
            if m=="GET":
                if ref not in self.refs: raise GitHubAPIError(404,"missing")
                return {"object":{"sha":self.refs[ref]}}
            if m=="PATCH":
                if self.fail_patch:
                    self.fail_patch=False; raise GitHubAPIError(422,"race")
                commit=self.commits[b["sha"]]
                if self.refs.get(ref) not in commit["parents"]:
                    raise GitHubAPIError(422,"not fast forward")
                self.refs[ref]=b["sha"]
                if self.move_source: self.refs["heads/stage1/section-uuids"]=self.move_source
                return {}
        if p==root+"/git/refs" and m=="POST":
            ref=b["ref"].removeprefix("refs/")
            if ref in self.refs: raise GitHubAPIError(422,"exists")
            self.refs[ref]=b["sha"]; return {}
        if p.startswith(root+"/git/commits/") and m=="GET": return self.commits[p.rsplit("/",1)[1]]
        if p.startswith(root+"/git/trees/") and m=="GET": return {"tree":self.trees[p.rsplit("/",1)[1].split("?",1)[0]]}
        if p.startswith(root+"/git/blobs/") and m=="GET": return {"content":base64.b64encode(self.blobs[p.rsplit("/",1)[1]]).decode()}
        if p==root+"/git/blobs" and m=="POST":
            s=self.ident("b"); self.blobs[s]=base64.b64decode(b["content"]); return {"sha":s}
        if p==root+"/git/trees" and m=="POST":
            s=self.ident("t")
            merged={x["path"]:dict(x) for x in self.trees.get(b.get("base_tree"), [])}
            for item in b["tree"]:
                merged[item["path"]]=dict(item)
            self.trees[s]=list(merged.values())
            return {"sha":s}
        if p==root+"/git/commits" and m=="POST":
            s=self.ident("c"); self.commits[s]={"tree":{"sha":b["tree"]},"parents":b["parents"]}; return {"sha":s}
        raise AssertionError((m,p))

class GitHubCASStoreTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeGitHub()
        self.store=GitHubRefCASStore(self.api,REPO,"stage1/section-uuids",
                                    max_inline_history=3, archive_batch_size=2)
    def test_persist_and_reload(self):
        self.assertTrue(self.store.publish(make_record())["current_effective"])
        second=GitHubRefCASStore(self.api,REPO,"stage1/section-uuids")
        self.assertEqual(second.current()["record_sha256"],make_record()["record_sha256"])
    def test_stale_source_history_only(self):
        self.api.refs["heads/stage1/section-uuids"]=OTHER
        self.api.commits[OTHER]={"tree":{"sha":"ts"}}
        self.assertEqual(self.store.publish(make_record())["decision"],"HISTORICAL_ONLY")
        self.assertIsNone(self.store.current())
    def test_source_move_during_commit_not_current(self):
        self.api.move_source=OTHER
        result=self.store.publish(make_record())
        self.assertFalse(result["current_effective"])
        self.assertIsNone(self.store.current())
    def test_failed_and_non_push_are_history_only(self):
        self.assertEqual(self.store.publish(make_record(outcome="FAILED"))["decision"],"HISTORICAL_ONLY")
        self.assertEqual(self.store.publish(make_record(2),event_name="pull_request")["decision"],"HISTORICAL_ONLY")
        self.assertIsNone(self.store.current())
    def test_generation_collision_rejected(self):
        self.store.publish(make_record(3))
        self.assertEqual(self.store.publish(make_record(3))["decision"],"REJECTED")
        self.assertEqual(self.store.current()["generation"],[3,1])
    def test_history_compaction_preserves_chain_and_bounds_inline_state(self):
        for n in range(1, 9):
            self.store.publish(make_record(n))
        head=self.store._get_ref(self.store.publication_branch)
        state=self.store._read_state_at(head)
        self.assertEqual(len(state["history"]), 2)
        self.assertEqual(state["history_archive"]["record_count"], 6)
        self.assertEqual(state["history_archive"]["segment_count"], 3)
        commit=self.api.commits[head]
        tree=self.api.trees[commit["tree"]["sha"]]
        archived=[x for x in tree if x["path"].startswith("state/history/segment-")]
        self.assertEqual(len(archived), 3)
        self.assertEqual(self.store.current()["generation"], [8, 1])

    def test_legacy_backlog_archives_multiple_segments_in_one_cas_commit(self):
        head=self.store._ensure_publication_ref()
        state=_empty(REPO)
        state["history"]=[
            {"record":make_record(n), "decision":"PUBLISHED",
             "reason":"fresh_successful_run", "authorized_source_revision":SOURCE}
            for n in range(1, 9)
        ]
        state["current"]=make_record(8)
        state["last_generation"]=[8, 1]
        state["authorized_source_revision"]=SOURCE
        state["state_sha256"]=digest({k:v for k,v in state.items() if k!="state_sha256"})
        seeded=self.store._commit_state(head,state)
        self.api.refs["heads/ae32c-publication-state"]=seeded

        result=self.store.publish(make_record(9))
        self.assertEqual(result["decision"],"PUBLISHED")
        current_head=self.store._get_ref(self.store.publication_branch)
        compacted=self.store._read_state_at(current_head)
        self.assertEqual(len(compacted["history"]),3)
        self.assertEqual(compacted["history_archive"]["record_count"],6)
        self.assertEqual(compacted["history_archive"]["segment_count"],3)
        tree=self.api.trees[self.api.commits[current_head]["tree"]["sha"]]
        segments=[x for x in tree if x["path"].startswith("state/history/segment-")]
        self.assertEqual(len(segments),3)
        self.assertEqual(self.store.current()["generation"],[9,1])

    def test_tampered_archive_segment_fails_closed(self):
        for n in range(1, 5):
            self.store.publish(make_record(n))
        head=self.store._get_ref(self.store.publication_branch)
        commit=self.api.commits[head]
        tree=self.api.trees[commit["tree"]["sha"]]
        archive=next(x for x in tree if x["path"].startswith("state/history/segment-"))
        self.api.blobs[archive["sha"]]=b'{"tampered":true}'
        with self.assertRaisesRegex(Exception, "publication_history_archive_identity_invalid"):
            self.store.current()

    def test_cas_conflict_retries(self):
        self.api.fail_patch=True
        self.assertEqual(self.store.publish(make_record())["decision"],"PUBLISHED")
        self.assertEqual(self.store.current()["generation"],[1,1])

if __name__=="__main__": unittest.main()
