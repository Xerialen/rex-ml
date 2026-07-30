import json

from rl.curriculum_io import FileCurriculumClient, read_stage, write_stage
from rl.curriculum_daemon import scan_new
from rl.rewards_gate1 import reward_stage1, reward_stage2


def test_stage_roundtrip(tmp_path):
    assert read_stage(tmp_path) == {"stage": 0, "done": False}
    write_stage(tmp_path, 2, False)
    assert read_stage(tmp_path)["stage"] == 2


def test_client_reports_and_follows_global_stage(tmp_path):
    c = FileCurriculumClient(tmp_path, "w0v0")
    assert c.reward_fn is reward_stage1
    c.end_episode(400.0, 10.0)
    lines = open(tmp_path / "episodes" / "w0v0.jsonl").read().strip().splitlines()
    assert json.loads(lines[0])["peak"] == 400.0
    write_stage(tmp_path, 1, False)
    c._last_check = 0.0          # forcera omkontroll utan att vänta 5 s
    changed = c.end_episode(410.0, 0.0)
    assert changed and c.stage == 1 and c.reward_fn is reward_stage2


def test_daemon_scan_reads_incrementally(tmp_path):
    ep = tmp_path / "episodes"
    ep.mkdir()
    f = open(ep / "a.jsonl", "w", buffering=1)
    f.write(json.dumps({"peak": 300, "coll": 0, "stage": 0}) + "\n")
    files = {}
    first = scan_new(files, ep)
    assert len(first) == 1
    assert scan_new(files, ep) == []          # inget nytt
    f.write(json.dumps({"peak": 310, "coll": 0, "stage": 0}) + "\n")
    again = scan_new(files, ep)
    assert len(again) == 1 and again[0]["peak"] == 310
