"""Tests for spring-signals/harness/check_assertions.py — fail-closed JSON assertion engine.

Every test here exists to kill a named mutant. The mutation pass (documented in
the harness module) applies these mutants to the engine and proves each dies:

  M1  `>=` -> `>` in AtLeast            killed by test_minimum_passes_at_equality
  M2  `==` -> `>=` in AssertedExact     killed by test_asserted_fails_low
  M3  `==` -> `<=` in AssertedExact     killed by test_asserted_fails_high
  M4  missing-CSV branch returns 0 rows killed by test_missing_csv_is_data_error_not_zero
  M5  IDENT_RE weakened to `.*`         killed by test_check_name_rejects_bad_names and
                                          test_traversal_name_cannot_read_outside_file
                                          (the exit-code-only version of this test let M5
                                          survive: a traversal name failed later as a
                                          missing-CSV DataError, masking the bypass)
  M6  containment check removed         killed by test_checked_path_rejects_symlink_escape
  M7  signal match on rule_id only      killed by test_signal_wrong_survivor_fails
  M8  unexpected-CSV check removed      killed by test_unexpected_csv_is_data_error
  M9  rule_minimums counts all rows     killed by test_counts_only_matching_rule_id
  M10 rule_minimums `>=` -> `>`         killed by test_rule_minimum_passes_at_equality
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = REPO_ROOT / "spring-signals" / "harness" / "check_assertions.py"

spec = importlib.util.spec_from_file_location("check_assertions", ENGINE_PATH)
ca = importlib.util.module_from_spec(spec)
sys.modules["check_assertions"] = ca  # dataclasses resolve cls.__module__ via sys.modules
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


def row(rule_id: str, symbol: str, signal: str) -> str:
    return (
        f"src/Foo.java,1,1,main,v1,{rule_id},spring,,{symbol},{signal},x\n"
    )


def write_spec(path: Path, spec_obj: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec_obj, indent=2) + "\n", encoding="utf-8")
    return path


def base_spec(**sections) -> dict:
    return {"spec_version": "v1", **sections}


# ---------------------------------------------------------------- spec loading


class TestSpecLoading:
    def test_missing_spec_file_exits_2(self, tmp_path):
        assert ca.main(["--spec", str(tmp_path / "nope.json"), "--out", str(tmp_path)]) == 2

    def test_empty_spec_file_exits_2(self, tmp_path):
        spec_path = write_spec(tmp_path / "expectations" / "s.json", {})
        spec_path.write_text("", encoding="utf-8")
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    def test_spec_with_no_expectations_exits_2(self, tmp_path):
        spec_path = write_spec(tmp_path / "expectations" / "s.json", base_spec())
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    def test_malformed_json_exits_2(self, tmp_path):
        spec_path = tmp_path / "s.json"
        spec_path.write_text("{not json", encoding="utf-8")
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    def test_unknown_spec_version_exits_2(self, tmp_path):
        spec_path = write_spec(tmp_path / "s.json", {"spec_version": "v99", "asserted": {"A": 0}})
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    def test_missing_spec_version_exits_2(self, tmp_path):
        spec_path = write_spec(tmp_path / "s.json", {"asserted": {"A": 0}})
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    def test_unknown_top_level_key_exits_2(self, tmp_path):
        spec_path = write_spec(
            tmp_path / "s.json", base_spec(asserted={"A": 0}, evil_key={})
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    def test_boolean_count_rejected(self, tmp_path):
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": True}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2


# ------------------------------------------------------------------ name hygiene


class TestQueryNameHygiene:
    @pytest.mark.parametrize(
        "bad",
        ["../etc", "x;rm -rf", "has space", "", "x/y", "..", ".hidden", "9leading"],
    )
    def test_rejected_names_exit_2(self, tmp_path, bad):
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={bad: 0}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2

    @pytest.mark.parametrize("good", ["ApiSurface", "Messaging", "A", "q_1"])
    def test_valid_names_accepted(self, tmp_path, good):
        write_csv(tmp_path / "out", good, [])
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={good: 0}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_checked_path_rejects_symlink_escape(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        base = tmp_path / "out"
        base.mkdir()
        link = base / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            # Directory junctions need no privilege on Windows; resolve() follows them.
            created = (
                os.name == "nt"
                and subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                    capture_output=True,
                ).returncode == 0
            )
            if not created:
                pytest.skip("symlink creation requires privileges on this platform")
        with pytest.raises(ca.SpecError):
            ca.checked_path(link, "Anything")

    @pytest.mark.parametrize(
        "bad",
        ["../etc", "x;rm -rf", "has space", "", "x/y", "..", ".hidden", "9leading", "../escape"],
    )
    def test_check_name_rejects_bad_names(self, bad):
        with pytest.raises(ca.SpecError):
            ca._check_name(bad)

    @pytest.mark.parametrize("good", ["ApiSurface", "Messaging", "A", "q_1"])
    def test_check_name_accepts_good_names(self, good):
        assert ca._check_name(good) == good

    def test_traversal_name_cannot_read_outside_file(self, tmp_path):
        # Plant a real CSV one level above the out dir. If the name check is
        # bypassed, "../escape" resolves to that file and gets graded instead
        # of rejected -- the exit-code-only version of this test missed that.
        write_csv(tmp_path, "escape", [row("r", "s", "g")])
        (tmp_path / "out").mkdir()
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"../escape": 1}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2


# ------------------------------------------------------------------ count kinds


class TestAssertedExact:
    def test_asserted_exact_passes(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 3)
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": 3}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_asserted_fails_high(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 4)
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": 3}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 1

    def test_asserted_fails_low(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 2)
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": 3}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 1


class TestMinimums:
    def test_minimum_passes_at_equality(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 5)
        spec_path = write_spec(tmp_path / "s.json", base_spec(minimums={"A": 5}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_minimum_passes_above(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 6)
        spec_path = write_spec(tmp_path / "s.json", base_spec(minimums={"A": 5}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_minimum_fails_below(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 4)
        spec_path = write_spec(tmp_path / "s.json", base_spec(minimums={"A": 5}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 1


# ------------------------------------------------------------------ fail closed


class TestFailClosed:
    def test_missing_csv_is_data_error_not_zero(self, tmp_path):
        (tmp_path / "out").mkdir()
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"Ghost": 0}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2

    def test_missing_out_dir_is_data_error(self, tmp_path):
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": 0}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "gone")]) == 2

    def test_unexpected_csv_is_data_error(self, tmp_path):
        write_csv(tmp_path / "out", "A", [])
        write_csv(tmp_path / "out", "Stale", [row("r", "s", "g")])
        spec_path = write_spec(tmp_path / "s.json", base_spec(asserted={"A": 0}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2


# ------------------------------------------------------------------ rule_minimums


class TestRuleMinimums:
    def _csv(self, tmp_path: Path):
        write_csv(
            tmp_path / "out",
            "ApiSurface",
            [row("api_surface__controller", "src/A.java:C", "x")] * 49
            + [row("api_surface__endpoint", "src/A.java:C.m1", "y")] * 369,
        )

    def test_rule_minimum_passes_at_equality(self, tmp_path):
        self._csv(tmp_path)
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {"api_surface__controller": 49}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_rule_minimum_passes_above(self, tmp_path):
        self._csv(tmp_path)
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {"api_surface__controller": 40}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_rule_minimum_fails_below(self, tmp_path):
        self._csv(tmp_path)
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {"api_surface__controller": 50}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 1

    def test_counts_only_matching_rule_id(self, tmp_path):
        # The file holds 418 rows total; only 49 carry the pinned rule_id.
        self._csv(tmp_path)
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {"api_surface__controller": 100}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 1

    def test_only_rule_minimums_section_is_a_valid_spec(self, tmp_path):
        self._csv(tmp_path)
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {"api_surface__endpoint": 369}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    @pytest.mark.parametrize("bad_rule", ["CamelCase", "has space", "../x", ""])
    def test_bad_rule_id_exits_2(self, tmp_path, bad_rule):
        write_csv(tmp_path / "out", "ApiSurface", [])
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {bad_rule: 1}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2

    def test_boolean_rule_count_exits_2(self, tmp_path):
        write_csv(tmp_path / "out", "ApiSurface", [])
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(rule_minimums={"ApiSurface": {"api_surface__controller": True}}),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 2


# ------------------------------------------------------------------ snapshots


class TestSnapshots:
    def test_snapshot_match_passes(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 7)
        spec_path = write_spec(tmp_path / "s.json", base_spec(snapshot={"A": 7}))
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")]) == 0

    def test_snapshot_drift_reports_without_failing(self, tmp_path, capsys):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 8)
        spec_path = write_spec(tmp_path / "s.json", base_spec(snapshot={"A": 7}))
        rc = ca.main(["--spec", str(spec_path), "--out", str(tmp_path / "out")])
        assert rc == 0
        assert "drift" in capsys.readouterr().out.lower()

    def test_snapshot_drift_fails_with_strict(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 8)
        spec_path = write_spec(tmp_path / "s.json", base_spec(snapshot={"A": 7}))
        rc = ca.main(
            ["--spec", str(spec_path), "--out", str(tmp_path / "out"), "--strict"]
        )
        assert rc == 1

    def test_record_updates_snapshot_in_place(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 9)
        exp_dir = tmp_path / "expectations"
        spec_path = write_spec(exp_dir / "s.json", base_spec(snapshot={"A": 0}))
        rc = ca.main(
            ["--spec", str(spec_path), "--out", str(tmp_path / "out"), "--record"]
        )
        assert rc == 0
        assert json.loads(spec_path.read_text(encoding="utf-8"))["snapshot"]["A"] == 9

    def test_record_refused_outside_expectations_dir(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")])
        spec_path = write_spec(tmp_path / "elsewhere" / "s.json", base_spec(snapshot={"A": 0}))
        rc = ca.main(
            ["--spec", str(spec_path), "--out", str(tmp_path / "out"), "--record"]
        )
        assert rc == 2


# ------------------------------------------------------------------ signals


class TestSignals:
    KAFKA_OPS = "org.springframework.kafka.core.KafkaOperations"
    KAFKA_TEMPLATE = "org.springframework.kafka.core.KafkaTemplate"

    def _spec(self, tmp_path: Path, signal: str) -> Path:
        return write_spec(
            tmp_path / "s.json",
            base_spec(
                signals=[
                    {
                        "query": "Messaging",
                        "rule_id": "messaging__template_type",
                        "symbol": "src/MessagingConfig.java:kafkaOps",
                        "signal": signal,
                    }
                ]
            ),
        )

    def test_signal_correct_survivor_passes(self, tmp_path):
        write_csv(
            tmp_path / "out",
            "Messaging",
            [row("messaging__template_type", "src/MessagingConfig.java:kafkaOps", self.KAFKA_OPS)],
        )
        rc = ca.main(
            ["--spec", str(self._spec(tmp_path, self.KAFKA_OPS)), "--out", str(tmp_path / "out")]
        )
        assert rc == 0

    def test_signal_wrong_survivor_fails(self, tmp_path):
        # Same row count, wrong surviving signal: a count-only harness would pass.
        write_csv(
            tmp_path / "out",
            "Messaging",
            [row("messaging__template_type", "src/MessagingConfig.java:kafkaOps", self.KAFKA_TEMPLATE)],
        )
        rc = ca.main(
            ["--spec", str(self._spec(tmp_path, self.KAFKA_OPS)), "--out", str(tmp_path / "out")]
        )
        assert rc == 1

    def test_signal_wrong_symbol_fails(self, tmp_path):
        write_csv(
            tmp_path / "out",
            "Messaging",
            [row("messaging__template_type", "src/Other.java:impl", self.KAFKA_OPS)],
        )
        rc = ca.main(
            ["--spec", str(self._spec(tmp_path, self.KAFKA_OPS)), "--out", str(tmp_path / "out")]
        )
        assert rc == 1

    def test_signal_entry_with_unknown_key_exits_2(self, tmp_path):
        spec_path = write_spec(
            tmp_path / "s.json",
            base_spec(
                signals=[
                    {
                        "query": "Messaging",
                        "rule_id": "r",
                        "symbol": "s",
                        "signal": "g",
                        "extra": "x",
                    }
                ]
            ),
        )
        assert ca.main(["--spec", str(spec_path), "--out", str(tmp_path)]) == 2


# ------------------------------------------------------------------ end to end


class TestEndToEnd:
    def test_subprocess_exit_codes(self, tmp_path):
        write_csv(tmp_path / "out", "A", [row("r", "s", "g")] * 2)
        good = write_spec(tmp_path / "good.json", base_spec(asserted={"A": 2}))
        bad = write_spec(tmp_path / "bad.json", base_spec(asserted={"A": 1}))

        run = lambda spec_path: subprocess.run(  # noqa: E731
            [sys.executable, str(ENGINE_PATH), "--spec", str(spec_path), "--out", str(tmp_path / "out")],
            capture_output=True,
            text=True,
        )
        assert run(good).returncode == 0
        assert run(bad).returncode == 1
        assert run(tmp_path / "absent.json").returncode == 2
