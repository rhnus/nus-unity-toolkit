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


def test_scaled_time_and_a_new_yield_are_leads_but_unscaled_time_is_not(tmp_path):
    hits = scan(tmp_path, """class Fade : MonoBehaviour {
    IEnumerator Run() {
        t += Time.deltaTime;
        t += Time.unscaledDeltaTime;
        yield return new WaitForEndOfFrame();
    }
}""")
    assert ("scaled-time", 3) in hits
    assert not any(rule == "scaled-time" and line == 4 for rule, line in hits)
    assert ("yield-alloc", 5) in hits


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
