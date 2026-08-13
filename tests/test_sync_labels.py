from __future__ import annotations

from pathlib import Path

import pytest

from heimdall.sync_labels import (
    DEFAULT_GITHUB_LABELS,
    parse_labels_yml,
    refuse_github_defaults,
    taxonomy_names,
)

REPO_LABELS = Path(__file__).resolve().parents[1] / "labels.yml"

SAMPLE = """\
namespaces:
  - name: work
    description: Engineering queue
    color: "7EE787"
    labels:
      - name: work:ready
        description: Triaged, ready to implement
      - name: work:done
        description: Shipped / closed
        color: "6E7681"
  - name: source
    color: "8B949E"
    labels:
      - name: source:github
        description: From GitHub
"""


def test_parse_labels_yml_namespace_color_and_override(tmp_path: Path) -> None:
    path = tmp_path / "labels.yml"
    path.write_text(SAMPLE, encoding="utf-8")
    wanted = parse_labels_yml(path)
    by_name = {lab["name"]: lab for lab in wanted}
    assert by_name["work:ready"]["color"] == "7EE787"
    assert by_name["work:done"]["color"] == "6E7681"
    assert by_name["source:github"]["color"] == "8B949E"
    assert by_name["work:ready"]["description"] == "Triaged, ready to implement"
    assert "work" not in by_name
    assert "bug" not in by_name


def test_parse_repo_labels_yml_is_taxonomy_only() -> None:
    wanted = parse_labels_yml(REPO_LABELS)
    names = {lab["name"] for lab in wanted}
    assert "work:ready" in names
    assert "work:doing" in names
    assert "work:done" in names
    assert "source:github" in names
    assert "signal:bug" in names
    assert "pri:p0" in names
    assert names.isdisjoint(DEFAULT_GITHUB_LABELS)
    assert all(":" in name for name in names)
    assert taxonomy_names(REPO_LABELS) == frozenset(names)


def test_refuse_github_defaults() -> None:
    with pytest.raises(SystemExit, match="refusing to create deleted GitHub default"):
        refuse_github_defaults(
            [{"name": "bug", "description": "x", "color": "000000"}]
        )
    refuse_github_defaults(
        [{"name": "work:ready", "description": "x", "color": "7EE787"}]
    )


def test_missing_color_fails(tmp_path: Path) -> None:
    path = tmp_path / "labels.yml"
    path.write_text(
        "namespaces:\n  - name: work\n    labels:\n      - name: work:ready\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="missing color"):
        parse_labels_yml(path)


def test_dry_run_prune_prints_without_gh(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import heimdall.sync_labels as mod

    monkeypatch.setattr(mod, "detect_repo", lambda: "mikolaj92/heimdall")
    monkeypatch.setattr(
        mod, "list_label_names", lambda repo: {"bug", "enhancement", "work:ready"}
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not call gh")

    monkeypatch.setattr(mod, "gh", boom)
    assert mod.main(["--dry-run", "--prune", "--repo", "mikolaj92/heimdall"]) == 0
    out = capsys.readouterr().out
    assert "upsert work:ready" in out
    assert "delete bug" in out
    assert "delete enhancement" in out
    assert "dry-run ok:" in out
    assert "pruned 2" in out
