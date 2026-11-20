"""Run: python -m pytest <this folder>/test_motion_scan.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion_scan as M


def scan(tmp_path, source):
    path = tmp_path / "Thing.cs"
    path.write_text(source, encoding="utf-8")
    return [(h["rule"], h["line"]) for h in M.scan_file(str(path))]


def test_a_drag_override_without_its_base_call_is_a_lead(tmp_path):
    hits = scan(tmp_path, """class Card : DraggableItem {
    public override void OnBeginDrag(PointerEventData e)
    {
        Move();
    }
    public override void OnEndDrag(PointerEventData e)
    {
        base.OnEndDrag(e);
    }
}""")
    assert ("base-skipped", 2) in hits
    assert not any(rule == "base-skipped" and line == 6 for rule, line in hits)


def test_searches_and_allocations_count_only_inside_per_frame_methods(tmp_path):
    hits = scan(tmp_path, """class Board : MonoBehaviour {
    void Start() { var a = FindAnyObjectByType<Board>(); var l = new List<int>(); }
    void Update()
    {
        var b = GetComponent<Image>();
        var m = new List<int>();
    }
}""")
    assert ("frame-search", 5) in hits
    assert ("frame-alloc", 6) in hits
    assert not any(line == 2 for _, line in hits)


def test_scaled_time_is_a_lead_but_unscaled_time_is_not(tmp_path):
    hits = scan(tmp_path, """class Fade : MonoBehaviour {
    IEnumerator Run() {
        t += Time.deltaTime;
        t += Time.unscaledDeltaTime;
    }
}""")
    assert ("scaled-time", 3) in hits
    assert not any(rule == "scaled-time" and line == 4 for rule, line in hits)


def test_a_new_yield_counts_only_inside_a_coroutine_loop(tmp_path):
    hits = scan(tmp_path, """class Slide : MonoBehaviour {
    IEnumerator Run() {
        yield return new WaitForSeconds(1f);
        while (t < 1f)
        {
            var c = GetComponent<Image>();
            yield return new WaitForEndOfFrame();
        }
    }
}""")
    assert ("yield-alloc", 7) in hits
    assert ("frame-search", 6) in hits
    assert not any(rule == "yield-alloc" and line == 3 for rule, line in hits)


def test_on_drag_is_per_frame_code(tmp_path):
    hits = scan(tmp_path, """class Bar : MonoBehaviour {
    public void OnDrag(PointerEventData e)
    {
        var hits = new List<RaycastResult>();
    }
}""")
    assert ("frame-alloc", 4) in hits


def test_commented_out_code_is_ignored(tmp_path):
    hits = scan(tmp_path, """class Quiet : MonoBehaviour {
    // t += Time.deltaTime; panel.SetActive(true); new Color(1f, 0f, 0f);
    void Update() { } // GetComponent<Image>();
}""")
    assert hits == []


def test_colours_scale_writes_and_instant_panels_are_flagged(tmp_path):
    hits = scan(tmp_path, """class Look : MonoBehaviour {
    void Show() {
        image.color = new Color(0.9f, 0.2f, 0.2f);
        card.localScale = Vector3.one * 1.1f;
        resultPanel.SetActive(true);
        icon.SetActive(true);
    }
}""")
    assert ("colour-literal", 3) in hits
    assert ("direct-scale", 4) in hits
    assert ("instant-show", 5) in hits
    assert not any(rule == "instant-show" and line == 6 for rule, line in hits)


SCALE_GUID = "a" * 32
CARD_GUID = "b" * 32


def tiny_project(tmp_path):
    scripts = tmp_path / "Assets" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "ScaleFeedback.cs").write_text("class ScaleFeedback : MonoBehaviour { }", encoding="utf-8")
    (scripts / "ScaleFeedback.cs.meta").write_text(f"fileFormatVersion: 2\nguid: {SCALE_GUID}\n", encoding="utf-8")
    (scripts / "Card.cs").write_text("""class Card : DraggableItem {
    public override void OnBeginDrag(PointerEventData e) { Move(); }
}""", encoding="utf-8")
    (scripts / "Card.cs.meta").write_text(f"fileFormatVersion: 2\nguid: {CARD_GUID}\n", encoding="utf-8")
    (scripts / "Unused.cs").write_text("class Unused { void Update() { var x = new List<int>(); } }", encoding="utf-8")
    prefab = tmp_path / "Assets" / "Card.prefab"
    prefab.write_text(f"""%YAML 1.1
--- !u!1 &100
GameObject:
  m_Name: Card
--- !u!114 &201
MonoBehaviour:
  m_GameObject: {{fileID: 100}}
  m_Script: {{fileID: 11500000, guid: {SCALE_GUID}, type: 3}}
  _pointerLocator: {{fileID: 300}}
  hoverScale: {{x: 1.03, y: 1.03, z: 1.03}}
  speed: 8
--- !u!114 &202
MonoBehaviour:
  m_GameObject: {{fileID: 100}}
  m_Script: {{fileID: 11500000, guid: {SCALE_GUID}, type: 3}}
  _pointerLocator: {{fileID: 300}}
  hoverScale: {{x: 1.1, y: 1.1, z: 1.1}}
  speed: 8
--- !u!114 &203
MonoBehaviour:
  m_GameObject: {{fileID: 100}}
  m_Script: {{fileID: 11500000, guid: {CARD_GUID}, type: 3}}
  onClick:
    m_PersistentCalls:
      m_Calls:
      - m_Target: {{fileID: 100}}
        m_MethodName: SetActive
""", encoding="utf-8")
    return prefab


def test_a_prefab_scans_only_its_own_scripts_and_its_wiring(tmp_path, capsys):
    prefab = tiny_project(tmp_path)
    assert M.main(["--json", str(prefab)]) == 0
    hits = __import__("json").loads(capsys.readouterr().out)
    rules = {h["rule"] for h in hits}
    files = {os.path.basename(h["file"]) for h in hits}
    assert "base-skipped" in rules            # Card.cs, reached through the prefab's guid
    assert "Unused.cs" not in files           # not on the prefab, so not scanned
    assert "feedback-fight" in rules          # two ScaleFeedbacks on one locator
    assert "inspector-toggle" in rules        # the persistent SetActive call
    values = [h["code"] for h in hits if h["rule"] == "feedback-values"]
    assert any("hoverScale" in v and "1.03" in v and "1.1" in v for v in values)


def test_a_feedback_left_unset_drives_its_own_object_and_can_fight_one_aimed_at_it(tmp_path):
    prefab = tiny_project(tmp_path)
    prefab.write_text(f"""%YAML 1.1
--- !u!1 &100
GameObject:
  m_Name: Card Feedback Group
--- !u!224 &110
RectTransform:
  m_GameObject: {{fileID: 100}}
--- !u!1 &400
GameObject:
  m_Name: Drag Icon
--- !u!114 &201
MonoBehaviour:
  m_GameObject: {{fileID: 100}}
  m_Script: {{fileID: 11500000, guid: {SCALE_GUID}, type: 3}}
  _pointerLocator: {{fileID: 0}}
--- !u!114 &202
MonoBehaviour:
  m_GameObject: {{fileID: 400}}
  m_Script: {{fileID: 11500000, guid: {SCALE_GUID}, type: 3}}
  _pointerLocator: {{fileID: 110}}
""", encoding="utf-8")
    hits, _ = M.scan_prefab(str(prefab), M.script_index(M.project_root(str(prefab)), [SCALE_GUID]))
    fights = [h["code"] for h in hits if h["rule"] == "feedback-fight"]
    assert len(fights) == 1 and "Card Feedback Group" in fights[0] and "Drag Icon" in fights[0]
