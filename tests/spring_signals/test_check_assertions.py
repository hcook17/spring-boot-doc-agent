"""Tests for spring-signals/harness/check-assertions.py — fail-closed assertion engine.

Exit semantics under test (documented in the engine docstring): 0 = all
assertions hold, 1 = an assertion failed or input rejected (SystemExit with a
message exits 1), 2 = the gate cannot vouch for the result (empty spec,
stale output in --out).

Every test exists to kill a named mutant; tests/spring_signals/mutation_driver.py
applies them and proves each dies:

  M1  minimums `>=` -> `>`              killed by test_minimum_passes_at_equality
  M2  exact `==` -> `>=`                killed by test_asserted_fails_low
  M3  exact `==` -> `<=`                killed by test_asserted_fails_high
  M4  missing CSV returns 0 rows        killed by test_missing_csv_fails_not_zero
  M5  IDENT_RE weakened to `.*`         killed by TestQueryNameHygiene rejected cases
  M6  record containment removed        killed by test_record_refused_outside_harness
  M7  signals compared as sets          killed by test_signals_fanout_duplicate_fails
  M8  stale-CSV check removed           killed by test_unexpected_csv_exits_2
  M9  record shadows asserted           killed by test_record_never_shadows_asserted
  M10 record merges instead of replaces killed by test_record_drops_stale_queries
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = REPO_ROOT / "spring-signals" / "harness" / "check-assertions.py"
HARNESS_DIR = ENGINE_PATH.parent

spec = importlib.util.spec_from_file_location("check_assertions", ENGINE_PATH)
ca = importlib.util.module_from_spec(spec)
sys.modules["check_assertions"] = ca  # dataclasses/typing resolve __module__ via sys.modules
spec.loader.exec_module(ca)

HEADER = (
    "file,start_line,end_line,source_set,schema_version,"
    "rule_id,framework,generation,symbol,signal,detail\n"
)


def write_csv(out_dir: Path, query: str, rows: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{query}.csv"
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return path


def row(rule_id: str, signal: str, symbol: str = "com.example/Foo#bar.") -> str:
    return f"src/Foo.java,1,1,main,v1,{rule_id},spring,,{symbol},{signal},x\n"


def write_spec(path: Path, spec_obj: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec_obj, indent=2) + "\n", encoding="utf-8")
    return path


def base_spec(**sections) -> dict:
    return {"repo": "test", "asserted": {}, "minimums": {}, "snapshot": {}, **sections}


def run(spec_path: Path, out_dir: Path, *extra: str) -> int:
    return ca.main(["--out", str(out_dir), "--expectations", str(spec_path), *extra])


# ------------------------------------------------------------------ spec loading


class TestSpecLoading:
    def test_missing_expectations_file_rejected(self, tmp_path):
        (tmp_path / "out").mkdir()
        with pytest.raises(SystemExit):
            run(tmp_path / "nope.json", tmp_path / "out")

    def test_malformed_json_rejected(self, tmp_path):
        (tmp_path / "out").mkdir()
        spec_path = tmp_path / "s.json"
        spec_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit):
            run(spec_path, tmp_path / "out")

    def test_empty_spec_exits_2(self, tmp_path):
        (tmp_path / "out").mkdir()
        spec_path = write_spec(tmp_path / "s.json", base_spec())
        assert run(spec_path, tmp_path / "out") == 2

    def test_allow_empty_passes(self, tmp_path):
        (tmp_path / "out").mkdir()
        spec_path = write_spec(tmp_path / "s.json", base_spec())
        assert run(spec_path, tmp_path / "out", "--allow-empty") == 0

    def test_cli_path_with_dotdot_rejected(self, tmp_path):
        write_csv(tmp_path / "out", "A", [])
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 0}}))
        with pytest.raises(SystemExit):
            ca.main(["--out", str(tmp_path / "out" / ".." / "out"), "--expectations", str(spec_path)])


# ------------------------------------------------------------------ name hygiene


class TestQueryNameHygiene:
    @pytest.mark.parametrize(
        "bad",
        ["../etc", "x;rm -rf", "has space", "", "x/y", "..", ".hidden", "9leading",
         # \w without re.ASCII would admit these into path construction.
         "Ångström", "日本語"],
    )
    def test_rejected_names(self, tmp_path, bad):
        (tmp_path / "out").mkdir()
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={bad: {"_rows": 0}}))
        with pytest.raises(SystemExit):
            run(spec_path, tmp_path / "out")

    @pytest.mark.parametrize("good", ["ApiSurface", "Messaging", "A", "q_1"])
    def test_valid_names_accepted(self, tmp_path, good):
        write_csv(tmp_path / "out", good, [])
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={good: {"_rows": 0}}))
        assert run(spec_path, tmp_path / "out") == 0


# ------------------------------------------------------------------ count kinds


class TestAssertedExact:
    def test_asserted_exact_passes(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 3)
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 3}}))
        assert run(spec_path, tmp_path / "out") == 0

    def test_asserted_fails_high(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 4)
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 3}}))
        assert run(spec_path, tmp_path / "out") == 1

    def test_asserted_fails_low(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 2)
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 3}}))
        assert run(spec_path, tmp_path / "out") == 1

    def test_per_rule_counts_only_matching_rule_id(self, tmp_path):
        rows = [row("api_surface__controller", "g")] * 3 + [row("api_surface__endpoint", "h")] * 10
        write_csv(tmp_path / "out", "ApiSurface", rows)
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(asserted={"ApiSurface": {"api_surface__controller": 4}}),
        )
        # 13 rows total; only 3 carry the pinned rule_id.
        assert run(spec_path, tmp_path / "out") == 1

    def test_boolean_count_rejected(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")])
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": True}}))
        with pytest.raises(SystemExit):
            run(spec_path, tmp_path / "out")


class TestMinimums:
    def test_minimum_passes_at_equality(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 5)
        spec_path = write_spec(tmp_path / "s.json", base_spec(minimums={"A": {"_rows": 5}}))
        assert run(spec_path, tmp_path / "out") == 0

    def test_minimum_passes_above(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 6)
        spec_path = write_spec(tmp_path / "s.json", base_spec(minimums={"A": {"_rows": 5}}))
        assert run(spec_path, tmp_path / "out") == 0

    def test_minimum_fails_below(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 4)
        spec_path = write_spec(tmp_path / "s.json", base_spec(minimums={"A": {"_rows": 5}}))
        assert run(spec_path, tmp_path / "out") == 1


# ------------------------------------------------------------------ fail closed


class TestFailClosed:
    def test_missing_csv_fails_not_zero(self, tmp_path):
        (tmp_path / "out").mkdir()
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"Ghost": {"_rows": 0}}))
        assert run(spec_path, tmp_path / "out") == 1

    def test_missing_out_dir_rejected(self, tmp_path):
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 0}}))
        with pytest.raises(SystemExit):
            run(spec_path, tmp_path / "gone")

    def test_unexpected_csv_exits_2(self, tmp_path):
        write_csv(tmp_path / "out", "A", [])
        write_csv(tmp_path / "out", "Stale", [row("r", "g")])
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 0}}))
        with pytest.raises(SystemExit) as exc:
            run(spec_path, tmp_path / "out")
        assert exc.value.code == 2

    def test_utf16_csv_is_a_miss_not_a_traceback(self, tmp_path):
        # A PowerShell `>` re-decode produces UTF-16, which utf-8-sig cannot
        # read. The documented contract is fail-closed-as-missing (exit 1 via
        # MISS), never an uncaught UnicodeDecodeError.
        import codecs

        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "A.csv").write_bytes(
            codecs.BOM_UTF16_LE + HEADER.encode("utf-16-le")
        )
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 0}}))
        assert run(spec_path, tmp_path / "out") == 1

    def test_utf8_bom_csv_reads_normally(self, tmp_path):
        import codecs

        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "A.csv").write_bytes(
            codecs.BOM_UTF8 + (HEADER + row("r", "g")).encode("utf-8")
        )
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": {"_rows": 1}}))
        assert run(spec_path, tmp_path / "out") == 0


# ------------------------------------------------------------------ snapshots


class TestSnapshots:
    def test_snapshot_match_passes(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 7)
        spec_path = write_spec(tmp_path / "s.json", base_spec(snapshot={"A": {"_rows": 7}}))
        assert run(spec_path, tmp_path / "out") == 0

    def test_snapshot_drift_fails(self, tmp_path):
        # Snapshots encode current behaviour, not intent; drift still fails the
        # gate here -- --record is the deliberate update path.
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 8)
        spec_path = write_spec(tmp_path / "s.json", base_spec(snapshot={"A": {"_rows": 7}}))
        assert run(spec_path, tmp_path / "out") == 1


# ------------------------------------------------------------------ _signals


class TestSignals:
    OPS = "org.springframework.kafka.core.KafkaOperations"
    TPL = "org.springframework.kafka.core.KafkaTemplate"

    def _spec(self, tmp_path: Path, signals: list[str]) -> Path:
        return write_spec(
            tmp_path / "s.json",
            base_spec(asserted={"Messaging": {"_signals": {"messaging__client_type": signals}}}),
        )

    def test_signals_exact_list_passes(self, tmp_path):
        write_csv(
            tmp_path / "out",
            "Messaging",
            [row("messaging__client_type", self.TPL), row("messaging__client_type", self.OPS)],
        )
        assert run(self._spec(tmp_path, [self.OPS, self.TPL]), tmp_path / "out") == 0

    def test_signals_wrong_survivor_fails_same_count(self, tmp_path):
        # Two rows either way: a count-only assertion could not tell.
        write_csv(
            tmp_path / "out",
            "Messaging",
            [row("messaging__client_type", self.TPL), row("messaging__client_type", self.TPL)],
        )
        assert run(self._spec(tmp_path, [self.OPS, self.TPL]), tmp_path / "out") == 1

    def test_signals_fanout_duplicate_fails(self, tmp_path):
        write_csv(
            tmp_path / "out",
            "Messaging",
            [row("messaging__client_type", self.OPS)] * 2
            + [row("messaging__client_type", self.TPL)],
        )
        assert run(self._spec(tmp_path, [self.OPS, self.TPL]), tmp_path / "out") == 1

    def test_signals_missing_rule_fails(self, tmp_path):
        write_csv(tmp_path / "out", "Messaging", [row("messaging__listener", "g")])
        assert run(self._spec(tmp_path, [self.OPS]), tmp_path / "out") == 1

    def test_signals_non_dict_rejected(self, tmp_path):
        write_csv(tmp_path / "out", "Messaging", [])
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(asserted={"Messaging": {"_signals": [self.OPS]}}),
        )
        with pytest.raises(SystemExit):
            run(spec_path, tmp_path / "out")


# ------------------------------------------------------------------ known_defects


class TestKnownDefects:
    def test_defects_printed_never_asserted(self, tmp_path, capsys):
        write_csv(tmp_path / "out", "A", [])
        spec_path = write_spec(
            tmp_path / "s.json",
            {
                **base_spec(asserted={"A": {"_rows": 0}}),
                "known_defects": {"A.some_rule": "counts 2x upstream"},
            },
        )
        assert run(spec_path, tmp_path / "out") == 0
        assert "counts 2x upstream" in capsys.readouterr().out


# ------------------------------------------------------------------ record


class TestRecord:
    def test_record_refused_outside_harness(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")])
        spec_path = write_spec(tmp_path / "s.json", base_spec(snapshot={"A": {"_rows": 0}}))
        with pytest.raises(SystemExit):
            run(spec_path, tmp_path / "out", "--record")

    def _harness_spec(self, spec_obj: dict) -> Path:
        # record() confines writes to the harness directory by construction, so
        # the success-path tests must use a throwaway spec inside it.
        return write_spec(HARNESS_DIR / "expectations" / ".test-record-tmp.json", spec_obj)

    def test_record_writes_snapshot_and_keeps_asserted(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r1", "g")] * 4)
        spec_path = self._harness_spec(
            base_spec(asserted={"A": {"r1": 4}}, snapshot={"A": {"_rows": 0}})
        )
        try:
            assert run(spec_path, tmp_path / "out", "--record") == 0
            written = json.loads(spec_path.read_text(encoding="utf-8"))
            assert written["asserted"]["A"]["r1"] == 4
            # r1 is asserted, so the snapshot must not shadow it; _rows is not.
            assert written["snapshot"]["A"] == {"_rows": 4}
            assert not spec_path.with_suffix(".json.tmp").exists()
        finally:
            spec_path.unlink(missing_ok=True)

    def test_record_never_shadows_asserted(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r1", "g")] * 3)
        spec_path = self._harness_spec(base_spec(asserted={"A": {"r1": 99}}))
        try:
            assert run(spec_path, tmp_path / "out", "--record") == 0
            written = json.loads(spec_path.read_text(encoding="utf-8"))
            assert written["asserted"]["A"]["r1"] == 99
            assert "r1" not in written["snapshot"]["A"]
        finally:
            spec_path.unlink(missing_ok=True)

    def test_record_drops_stale_queries(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r1", "g")])
        spec_path = self._harness_spec(
            base_spec(snapshot={"A": {"_rows": 1}, "Ghost": {"_rows": 9}})
        )
        try:
            assert run(spec_path, tmp_path / "out", "--record") == 0
            written = json.loads(spec_path.read_text(encoding="utf-8"))
            assert "Ghost" not in written["snapshot"]
        finally:
            spec_path.unlink(missing_ok=True)


# ------------------------------------------------------- real expectations files


class TestRealExpectations:
    """The run.sh default wave and the shipped specs must agree on query names.

    run.sh emits one CSV per DEFAULT_QUERIES entry; check_no_stale_csvs exits 2
    on any CSV the spec does not name. A spec that names fewer queries than the
    default wave makes the default invocation un-runnable -- the exact failure
    this test exists to catch.
    """

    @staticmethod
    def _default_queries() -> list[str]:
        run_sh = (REPO_ROOT / "spring-signals" / "harness" / "run.sh").read_text(encoding="utf-8")
        m = re.search(r'^DEFAULT_QUERIES="([^"]+)"', run_sh, re.M)
        assert m, "run.sh no longer defines DEFAULT_QUERIES"
        return m.group(1).split()

    @pytest.mark.parametrize(
        "spec_name", ["ocs-api-service.json", "fixture-repo.json"]
    )
    def test_spec_names_every_default_wave_query(self, spec_name):
        spec_path = REPO_ROOT / "spring-signals" / "harness" / "expectations" / spec_name
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        named = ca.spec_queries(spec)
        missing = [q for q in self._default_queries() if q not in named]
        assert not missing, f"{spec_name} does not name default-wave queries: {missing}"


# ------------------------------------------------------------------ end to end


class TestEndToEnd:
    def test_subprocess_exit_codes(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "g")] * 2)
        good = write_spec(tmp_path / "good.json", base_spec(asserted={"A": {"_rows": 2}}))
        bad = write_spec(tmp_path / "bad.json", base_spec(asserted={"A": {"_rows": 1}}))

        def invoke(spec_path: Path) -> int:
            return subprocess.run(
                [sys.executable, str(ENGINE_PATH), "--out", str(tmp_path / "out"),
                 "--expectations", str(spec_path)],
                capture_output=True,
                text=True,
            ).returncode

        assert invoke(good) == 0
        assert invoke(bad) == 1
        assert invoke(tmp_path / "absent.json") != 0
