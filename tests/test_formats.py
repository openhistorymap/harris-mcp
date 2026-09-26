"""Format adapters against T. S. Dye's fig12 harris-matrix-data-package."""

import json
import shutil
from pathlib import Path

import pytest

from harris_mcp import formats

FIG12 = Path(__file__).parent / "fixtures" / "fig12"


def _check_fig12(m):
    assert len(m.contexts) == 19
    assert m.graph.number_of_edges() == 27  # 26 observations + 1 date-order
    assert m.name == "harris-matrix-fig12"
    assert m.contexts["1"].type == "deposit"
    assert m.contexts["1"].period == "Period 3"
    assert m.contexts["Natural ground"].phase == "Phase II"
    assert m.contexts["1"].attrs["url"] == "http://harris-matrix.tsdye.com/img/fig12-1.png"
    assert [s["lab"] for s in m.contexts["15"].attrs["radiocarbon"]] == ["LAB-3", "LAB-4"]
    assert m.equiv.find("7") == m.equiv.find("8")  # inference
    assert m.graph.has_edge("4", "3")  # date-order: 4 is younger than 3
    sources = {r.attrs["source"] for r in m.relations}
    assert sources == {"observation", "inference", "date-order"}


@pytest.mark.parametrize("target", ["dir", "descriptor"])
def test_datapackage_paths(target):
    path = FIG12 if target == "dir" else FIG12 / "datapackage.json"
    assert formats.detect(path) == "datapackage"
    _check_fig12(formats.load(path))


def test_datapackage_zip_with_subfolder(tmp_path):
    # Same layout as a GitHub "Download ZIP": the package sits in a subfolder.
    shutil.copytree(FIG12, tmp_path / "src" / "harris-matrix-data-package")
    archive = shutil.make_archive(str(tmp_path / "fig12"), "zip", tmp_path / "src")
    m = formats.load(archive)
    _check_fig12(m)
    assert m.path == archive


def test_datapackage_is_read_only(tmp_path):
    with pytest.raises(NotImplementedError):
        formats.dump(formats.load(FIG12), tmp_path / "out.zip")


def test_hmdp_rejects_non_hmdp_json(tmp_path):
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"foo": 1}))
    with pytest.raises(ValueError, match="not an HMDP file"):
        formats.load(other)
    with pytest.raises(ValueError, match="not an HMDP file"):
        formats.load(FIG12 / "datapackage.json", fmt="hmdp")


def test_csv_pair_accepts_label_and_younger_older():
    m = formats.load(f"{FIG12}/contexts.csv+{FIG12}/observations.csv")
    assert len(m.contexts) == 19
    assert m.graph.number_of_edges() == 26
    assert m.graph.has_edge("18", "Natural ground")
    assert m.contexts["2"].type == "interface"


def test_csv_pair_rejects_unknown_columns(tmp_path):
    (tmp_path / "contexts.csv").write_text("name\nA\n")
    (tmp_path / "relations.csv").write_text("a,b\nA,B\n")
    with pytest.raises(ValueError, match="no context ids"):
        formats.load(tmp_path)
    (tmp_path / "contexts.csv").write_text("id\nA\n")
    (tmp_path / "relations.csv").write_text("x,y\nA,B\n")
    with pytest.raises(ValueError, match="no relations"):
        formats.load(tmp_path)


def test_hmdp_round_trip(tmp_path):
    m = formats.load(FIG12)
    out = tmp_path / "fig12.hmdp.json"
    formats.dump(m, out)
    m2 = formats.load(out)
    assert set(m2.graph.edges) == set(m.graph.edges)
    assert m2.contexts["15"].attrs == m.contexts["15"].attrs


def test_hm_ini_project(tmp_path):
    # hm's own project layout: prefixed tables named by an .ini, no descriptor.
    for f in FIG12.glob("*.csv"):
        shutil.copy(f, tmp_path / f"site-{f.name}")
    (tmp_path / "unrelated.ini").write_text("[Output files]\nsequence-dot = x.dot\n")
    (tmp_path / "site.ini").write_text(
        "[Input files]\n"
        "contexts = site-contexts.csv\nobservations = site-observations.csv\n"
        "inferences = site-inferences.csv\nperiods = site-periods.csv\n"
        "phases = site-phases.csv\nevents = site-radiocarbon.csv\n"
        "event-order = site-date-order.csv\n"
        "[Input file headers]\ncontexts = yes\n"
    )
    assert formats.detect(tmp_path) == "datapackage"
    m = formats.load(tmp_path)
    assert m.name == "site"
    assert len(m.contexts) == 19 and m.graph.number_of_edges() == 27
    assert [s["lab"] for s in m.contexts["15"].attrs["radiocarbon"]] == ["LAB-3", "LAB-4"]


def test_hm_ini_without_header_rows(tmp_path):
    (tmp_path / "c.csv").write_text("A,deposit,other,,,\nB,deposit,other,,,\n")
    (tmp_path / "o.csv").write_text("A,B,\n")
    (tmp_path / "p.ini").write_text(
        "[Input files]\ncontexts = c.csv\nobservations = o.csv\n"
        "[Input file headers]\ncontexts = no\nobservations = no\n"
    )
    m = formats.load(tmp_path / "p.ini")
    assert set(m.contexts) == {"A", "B"} and m.graph.has_edge("A", "B")


ULM = Path(__file__).parent / "fixtures" / "ulm-eggingen"


def _snapshot(m):
    return (
        set(m.graph.edges),
        {k: (c.type, c.phase, c.period) for k, c in m.contexts.items()},
        {frozenset(v) for v in m.equiv.classes().values() if len(v) > 1},
    )


def test_hmcx_graphml():
    m = formats.load(ULM / "Ulm-Eggingen_Strat.hmcx")
    assert len(m.contexts) == 110  # units incl. T / U / G, excluding groups
    assert m.graph.number_of_edges() == 192
    assert len(m.phases) == 36 and set(m.periods) == {"I", "II", "III"}
    assert m.contexts["T"].type == "top_surface"
    assert m.contexts["G"].type == "geology"
    assert m.contexts["49/3"].phase == "B. 36"
    assert m.contexts["12/36"].phase is None and m.contexts["12/36"].period == "III"
    assert m.graph.has_edge("T", "49/3") and m.graph.has_edge("49/3", "U")
    assert "16/9" in m.contexts  # stored as " 16/9" in the file
    assert m.equiv.find("8/11") == m.equiv.find("10/14")


def test_hmc_csv_export_matches_hmcx():
    csv_m = formats.load(ULM / "Ulm-Eggingen_Strat_uncollapsed.csv")
    assert _snapshot(csv_m) == _snapshot(formats.load(ULM / "Ulm-Eggingen_Strat.hmcx"))
    assert csv_m.contexts["49/3"].description == "L pit of Buildingg 36; CA phase 3"
