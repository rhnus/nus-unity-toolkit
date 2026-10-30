"""export_agents.py on a throwaway project. Run: python -m pytest <this folder>/test_export_agents.py"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_agents as E


@pytest.fixture
def skills(tmp_path, monkeypatch):
    source = tmp_path / "toolkit" / "skills"
    plain = source / "plain-skill"
    (plain / "scripts" / "__pycache__").mkdir(parents=True)
    (plain / "SKILL.md").write_bytes(b"---\r\nname: plain-skill\r\ndescription: Does a | plain thing.\r\n---\r\n\r\n"
                                     b"# Plain\r\n\r\nRun `python \"${CLAUDE_SKILL_DIR}/scripts/tool.py\"`.\r\n")
    (plain / "scripts" / "tool.py").write_text("print('hi')\n")
    (plain / "scripts" / "test_tool.py").write_text("def test(): pass\n")
    (plain / "scripts" / "__pycache__" / "tool.cpython-312.pyc").write_bytes(b"\x00")
    editor = source / "editor-skill"
    editor.mkdir()
    (editor / "SKILL.md").write_text("---\nname: editor-skill\ndescription: Needs the editor.\n---\n\n"
                                     "Call `Unity_RunCommand` with the snippet.\n")
    monkeypatch.setattr(E, "SKILLS", source)
    monkeypatch.setattr(E, "toolkit_version", lambda: "9.9.9")
    return source


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return root


def run(project, *args):
    return E.main(["--project", str(project), *args])


def test_the_copy_points_at_its_own_scripts_and_says_where_it_came_from(skills, project):
    assert run(project) == 0
    copy = project / ".github" / "skills" / "plain-skill"
    text = (copy / "SKILL.md").read_text(encoding="utf-8")
    assert '".github/skills/plain-skill/scripts/tool.py"' in text
    assert "${CLAUDE_SKILL_DIR}" not in text
    assert text.startswith("---\nname: plain-skill\n")             # front matter stays first, with LF endings
    assert E.GENERATED_MARK + " 9.9.9" in text
    assert (copy / "scripts" / "tool.py").is_file()
    assert not (copy / "scripts" / "test_tool.py").exists()
    assert not (copy / "scripts" / "__pycache__").exists()


def test_only_skills_that_call_the_editor_are_marked_as_needing_the_bridge(skills, project):
    run(project)
    assert "Needs the Unity MCP bridge" in (project / ".github/skills/editor-skill/SKILL.md").read_text()
    assert "Needs the Unity MCP bridge" not in (project / ".github/skills/plain-skill/SKILL.md").read_text()


def test_agents_md_gets_one_section_and_keeps_what_was_there(skills, project):
    (project / "AGENTS.md").write_text("# Rules\n\nRead CLAUDE.md.\n")
    run(project)
    run(project)
    text = (project / "AGENTS.md").read_text()
    assert text.startswith("# Rules\n\nRead CLAUDE.md.\n\n<!-- nus-unity-toolkit:start -->")
    assert text.count("<!-- nus-unity-toolkit:start -->") == 1
    assert "| `plain-skill` | Does a / plain thing. | `.github/skills/plain-skill/SKILL.md` |  |" in text
    assert "| `editor-skill` | Needs the editor. | `.github/skills/editor-skill/SKILL.md` | yes |" in text


def test_check_passes_after_an_export_and_fails_after_a_toolkit_update(skills, project, monkeypatch):
    assert run(project, "--check") == 1
    run(project)
    assert run(project, "--check") == 0
    monkeypatch.setattr(E, "toolkit_version", lambda: "10.0.0")
    assert run(project, "--check") == 1


def test_check_ignores_line_endings(skills, project):
    run(project)
    tool = project / ".github/skills/plain-skill/SKILL.md"
    tool.write_bytes(tool.read_bytes().replace(b"\n", b"\r\n"))
    assert run(project, "--check") == 0


def test_a_project_s_own_skill_of_the_same_name_is_left_alone(skills, project):
    own = project / ".github/skills/plain-skill"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("---\nname: plain-skill\ndescription: Ours.\n---\n")
    run(project)
    assert (own / "SKILL.md").read_text() == "---\nname: plain-skill\ndescription: Ours.\n---\n"
    assert "plain-skill" not in json.loads((project / ".github/skills" / E.STAMP).read_text())["skills"]
    assert "`plain-skill`" not in (project / "AGENTS.md").read_text()


def test_a_skill_dropped_from_the_toolkit_is_removed_from_the_project(skills, project):
    run(project)
    (skills / "plain-skill" / "SKILL.md").unlink()
    run(project)
    assert not (project / ".github/skills/plain-skill").exists()
    assert (project / ".github/skills/editor-skill").is_dir()


def test_a_tampered_stamp_cannot_delete_outside_the_skills_directory(skills, project):
    run(project)
    assets = project / "Assets"
    assets.mkdir()
    (assets / "keep.txt").write_text("keep")
    stamp = project / ".github/skills" / E.STAMP
    stamp.write_text(json.dumps({"skills": ["../../Assets"]}))

    with pytest.raises(SystemExit, match="Invalid skill name"):
        run(project)

    assert (assets / "keep.txt").read_text() == "keep"


def test_off_removes_only_what_the_export_wrote(skills, project):
    (project / "AGENTS.md").write_text("# Rules\n")
    own = project / ".github/skills/our-skill"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("---\nname: our-skill\n---\n")
    run(project)
    run(project, "--off")
    assert (project / "AGENTS.md").read_text() == "# Rules\n"
    assert (own / "SKILL.md").is_file()
    assert not (project / ".github/skills/plain-skill").exists()


def test_check_with_off_is_refused_and_removes_nothing(skills, project):
    run(project)
    before = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))
    with pytest.raises(SystemExit) as err:
        run(project, "--check", "--off")
    assert err.value.code == 2
    assert sorted(p.relative_to(project).as_posix() for p in project.rglob("*")) == before


def test_agents_md_alone_is_refused_because_it_lists_the_copies(skills, project):
    with pytest.raises(SystemExit) as err:
        run(project, "--targets", "agents-md")
    assert "github or agents" in str(err.value)


def test_the_real_skills_export_without_any_claude_only_path(project):
    assert E.main(["--project", str(project), "--targets", "agents", "agents-md"]) == 0
    copies = list((project / ".agents" / "skills").glob("*/SKILL.md"))
    assert len(copies) == len(E.shipped_skills()) >= 7
    for path in copies:
        assert "${CLAUDE_SKILL_DIR}" not in path.read_text(encoding="utf-8"), path
    assert "`ticket-proof`" in (project / "AGENTS.md").read_text(encoding="utf-8")
