"""The parts of ticket_proof that need no network. Run: python -m pytest <this folder>/test_ticket_proof.py"""
import datetime as dt
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticket_proof as T


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "ticket-board.json").write_text(json.dumps({
        "organization": "contoso", "project": "VR Game (Nursing)", "areaPath": "VR Game (Nursing)\\Ward"}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(T, "BOARD", None)
    monkeypatch.setattr(T, "ROOT", None)
    return tmp_path


def test_board_comes_from_an_azure_devops_remote():
    assert T.board_from_remote("https://org@dev.azure.com/nusit-aat-rt/Infection%20Control%20VR/_git/vr-game") == \
        ("https://dev.azure.com/nusit-aat-rt", "Infection Control VR")
    assert T.board_from_remote("https://nusit.visualstudio.com/Game/_git/game") == ("https://dev.azure.com/nusit", "Game")
    assert T.board_from_remote("https://github.com/rhnus/nus-unity-toolkit.git") is None


def test_the_settings_file_names_the_board(project):
    b = T.board()
    assert b["organization"] == "https://dev.azure.com/contoso"
    assert b["project"] == "VR Game (Nursing)"
    assert b["source"] == "config"
    assert b["capturesFolder"] == project / "Artifacts" / "TicketProof"


def test_no_board_anywhere_says_how_to_set_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as err:
        T.load_board(pathlib.Path(tmp_path))
    assert "ticket-board.json" in str(err.value)


def test_the_sprint_query_filters_by_area_and_type_and_escapes_quotes():
    q = T.sprint_wiql("Game\\Sprint 1", True, "Game\\Ward's", ["Epic"])
    assert "[System.IterationPath] UNDER 'Game\\Sprint 1'" in q
    assert "[System.AreaPath] UNDER 'Game\\Ward''s'" in q
    assert "NOT IN ('Epic')" in q
    assert "@Me" in q
    assert "@Me" not in T.sprint_wiql("Game\\Sprint 1", False)


def test_the_current_sprint_is_the_one_holding_today_else_the_last_started():
    sprints = [{"name": "S1", "start": "2026-01-01", "finish": "2026-01-14"},
               {"name": "S2", "start": "2026-02-01", "finish": "2026-02-14"}]
    assert T.current_sprint(sprints, "2026-01-05")["name"] == "S1"
    assert T.current_sprint(sprints, "2026-01-20")["name"] == "S1"
    assert T.current_sprint(sprints, "2025-12-01") is None


def test_the_comment_shows_images_inline_and_clips_as_links():
    captures = [{"file": "a.png", "kind": "image", "caption": "Item 1 - fixed.", "label": "Ward 2"},
                {"file": "b.mp4", "kind": "video", "caption": "Item 2 - fixed.", "label": "Grab"}]
    comment = T.build_comment(captures, ["https://x/a", "https://x/b"], "Both fixed", "abc12345", "2026-10-28")
    assert comment.startswith("<div><b>After:</b> Both fixed</div>")
    assert '<img src="https://x/a"' in comment
    assert '<a href="https://x/b">Clip: Grab</a>' in comment
    assert comment.count("<img") == 1
    assert T.MARKER in comment


def test_a_removed_capture_never_lets_the_next_overwrite_a_waiting_one(project):
    shot = project / "shot.png"
    shot.write_bytes(b"\x89PNG one")
    other = project / "other.png"
    other.write_bytes(b"\x89PNG two")
    third = project / "third.png"
    third.write_bytes(b"\x89PNG three")
    now = dt.datetime(2026, 10, 28, 9, 0, 0)
    first, second = T.attach(990001, [str(shot), str(other)], [], "", now=now)
    manifest = T.load_manifest(990001)
    manifest["captures"] = [c for c in manifest["captures"] if c["file"] != first["file"]]
    T.save_manifest(990001, manifest)
    (T.ticket_folder(990001) / first["file"]).unlink()

    [new] = T.attach(990001, [str(third)], [], "", now=now)

    assert new["file"] != second["file"]
    assert (T.ticket_folder(990001) / second["file"]).read_bytes() == b"\x89PNG two"


def test_a_pull_request_has_its_own_folder_and_name(project):
    shot = project / "shot.png"
    shot.write_bytes(b"\x89PNG pr")
    [queued] = T.attach(T.pr_key(45), [str(shot)], ["Item 1 - fixed."], "Ward 2")
    assert queued["file"].startswith("pr-45_")
    assert (project / "Artifacts" / "TicketProof" / "pr-45" / queued["file"]).is_file()
    assert T.name_of(T.pr_key(45)) == "pull request !45"
    assert T.name_of(123) == "#123"
    assert not T.is_scratch(T.pr_key(990001))


def test_one_of_ticket_or_pr_is_required():
    with pytest.raises(SystemExit):
        T.main(["status"])
    with pytest.raises(SystemExit):
        T.main(["status", "--ticket", "1", "--pr", "2"])


def test_a_pull_request_cannot_be_moved_to_done(project):
    with pytest.raises(SystemExit) as err:
        T.main(["post", "--pr", "45", "--done"])
    assert "pull request has none" in str(err.value)


def test_the_pull_request_comment_is_markdown_with_images_inline_and_clips_as_links():
    captures = [{"file": "a.png", "kind": "image", "caption": "Item 1 - fixed: the *gel* cue.", "label": "Ward 2"},
                {"file": "b.mp4", "kind": "video", "caption": "Item 2 - fixed.", "label": "Grab"}]
    comment = T.build_markdown(captures, ["https://x/a?n=1", "https://x/b"], "Both fixed", "abc12345", "2026-10-29")
    assert comment.startswith("**After:** Both fixed\n\n")
    assert "![After: Ward 2](<https://x/a?n=1>)" in comment
    assert "[Clip: Grab](<https://x/b>)" in comment
    assert r"the \*gel\* cue." in comment
    assert comment.count("![") == 1
    assert T.MARKER in comment
    assert "<img" not in comment


def test_a_pull_request_preview_writes_a_page_and_posts_nothing(project, monkeypatch):
    shot = project / "shot.png"
    shot.write_bytes(b"\x89PNG preview")
    T.attach(T.pr_key(45), [str(shot)], ["Item 1 - fixed."], "Ward 2")
    monkeypatch.setattr(T, "request", lambda *a, **k: pytest.fail("a preview must not call Azure DevOps"))
    T.main(["post", "--pr", "45", "--note", "Gel cue shows", "--preview"])
    page = (project / "Artifacts" / "TicketProof" / "pr-45" / "preview.html").read_text(encoding="utf-8")
    assert "Nothing has been posted to pull request !45" in page
    assert "<img" in page


def test_a_clip_cannot_be_outlined(project):
    clip = project / "clip.mp4"
    clip.write_bytes(b"video")
    with pytest.raises(SystemExit) as err:
        T.attach(990001, [str(clip)], [], "", outlines=["1,1,5,5"])
    assert "images only" in str(err.value)
