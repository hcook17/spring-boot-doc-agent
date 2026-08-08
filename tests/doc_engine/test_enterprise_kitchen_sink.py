#!/usr/bin/env python3
"""
tests/doc_engine/test_enterprise_kitchen_sink.py — the whole pipeline, run as real commands
against a deliberately hostile synthetic "enterprise" repo, and then attacked.

WHY THIS EXISTS
Every other suite here tests one script at a time, and two structural holes
followed from that:

  1. Nothing ran the pipeline's documented command sequence as real
     subprocesses. tests/doc_engine/test_capacity_preflight.py chains four stages in-process
     and stops before the gates.
  2. No fault injection ever closed the loop to a real process exit code.
     tests/ci/test_check_pipeline_output.py asserts the pure function
     exit_code(["x"]) == 1 — so before this file, every gate in this pipeline
     was proven only to *populate an issues list*, never to actually fail a
     run. A gate that cannot be shown to fail is not a gate.

Hostile-input coverage was likewise near-absent: nothing exercised invalid
UTF-8, a BOM, CRLF, NUL bytes, zero-byte files, unicode paths, two @Entity
classes in one file, or --max-file-bytes through its actual CLI flag.

WHAT IT DELIBERATELY DOES NOT RE-TEST
.gitignore/--respect-gitignore (covered twice already), @EntityScan
false-positives, JPQL-vs-native argument order, multi-line @PreAuthorize,
run_manifest's own lifecycle and its partial/crashed-run path, the secret
heuristics' unit behavior, citation_coverage's finding kinds at function
level, and capacity_preflight's warn-on-max rule. Those have owners.

ORGANIZATION — Kleppmann, *Designing Data-Intensive Applications*
This is a derived-data pipeline, so DDIA's vocabulary fits it more literally
than usual and organizes both the variety of inputs and the rigor of the
assertions. Class names are zero-padded so unittest's alphabetical ordering
matches chapter order:

  Ch01  reliability; fault vs. failure; deliberately induced faults
  Ch03  storage and retrieval; a secondary index on a non-unique key
  Ch04  encoding
  Ch05  replication — four derived copies of one fact, and where they diverge
  Ch06  partitioning; skew; hot spots; rebalancing
  Ch07  lost updates; read-modify-write; atomic writes
  Ch10  batch/derived data; the command chain; staleness
  Ch12  the end-to-end argument — which layer catches which defect

A note on rigor, since it drove several choices: structural invariants are
preferred over re-run-and-diff probes throughout. That is not style — a
re-run-and-diff probe in this project once missed a bug that a
`keys == sorted(keys)` invariant caught. Where sortedness is asserted it is
asserted only for collections that are sorted at the source; the DFS-ordered
ones carry a deliberate *inverse* assertion, because asserting sortedness on
them would be asserting a falsehood.

COST
setUpModule builds the fixture and runs the chain exactly once; every class
reads those shared artifacts, and anything destructive works on a copy.

Measured: ~132s total on Windows, of which ~55s is setUpModule. The cost is
process startup, not work — this suite spawns ~45 subprocesses and Windows
charges ~1.3s for each, against ~0.2-0.4s on a Linux runner, so CI is
substantially faster than the local figure. If that ever needs cutting, the
single biggest discretionary item is
Ch10CommandChainTest.test_run_pipeline_local_driver_runs_end_to_end (~20s,
and the only coverage run_pipeline_local.py has).

KNOWN DEFECTS THIS SUITE PINS
Three findings surfaced while writing it. Two are fixed and now have
regression tests here; remaining open items are pinned as current behavior
with the reasoning recorded at the assertion:
  fixed  spring_signal_scan.py decoded ast-grep's stdout with the locale
         codec — crash on some non-ASCII, silent mojibake on the rest
  fixed  config files were read as utf-8 rather than utf-8-sig, so a BOM
         blinded the first line to every ^\\s*-anchored regex
  fixed  build_groups() could loop forever (see
         Ch06PartitioningTest.test_build_groups_terminates_*)
  fixed  overlap cascades past adjacent groups — carry_forward no longer
         re-carries overlap seed files (Ch06 + RealEnterpriseRepoTest)
  fixed  `application-dev-local.yml` is now recognized as a config file
  fixed  Stage-0 covering sibling + Path A internal-key strip (Ch10) —
         `covering_proof.json` beside `spring_signals.json`; ABSENCE/UNPROVEN
         stamps in `facts.jsonl`; no `_covering_proof` leak into Path A
  open   a write into a gitignored path is invisible to the write-scope gate

Run with:

    pytest tests/doc_engine/test_enterprise_kitchen_sink.py -v

Opt-in lane against a real repository (skipped unless configured)::

    DOC_ENGINE_REAL_REPO=/abs/path/to/a/real/spring/repo \\
        pytest tests/doc_engine/test_enterprise_kitchen_sink.py::RealEnterpriseRepoTest -v

Or ``local-runs/real-repo.path`` / legacy ``KITCHEN_SINK_REPO``.

Requires: ast-grep on PATH, and git (for the write-scope gate).

UNADDRESSED HAZARD, RECORDED RATHER THAN TESTED
partition_repo.py's hand-written _walk() decides dir-vs-file with
os.path.isdir(), which follows symlinks, and has no cycle guard — a symlink
loop would recurse until the stack blows. spring_signal_scan.py's
os.walk(followlinks=False) is safe by contrast. No symlink is planted in this
fixture: creating one on Windows needs elevation, and a cycle in CI would
hang the job rather than fail it. _walk is also real Python recursion, so a
tree ~1000 levels deep raises RecursionError; this fixture goes 30 levels,
which exercises deep paths without approaching either that limit or Windows
MAX_PATH.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS
from doc_engine.pipeline.mock_stages import (
    find_existing_readme,
    load_citations,
    mock_architecture,
    mock_docs,
    mock_file_summaries,
    mock_gap_and_interview,
    sweep_todos,
)
from doc_engine.tools import partition_repo, run_manifest, spring_signal_scan
from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES
from doc_engine.scanning.covering import verify_covering_proof

SCRIPT_DIR = SCRIPTS_DIR
PY = sys.executable
MAX_TOKENS = "2000"        # small on purpose: forces real multi-group partitioning
SMALL_FILE_BYTES = "4096"  # for the --max-file-bytes CLI exercise

# sha256 of zero bytes — a free exact check on file_signatures.
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

BILLING = "services/billing-service/src/main/java/com/acme/billing"
LEDGER = "services/ledger-service/src/main/java/com/acme/ledger"
LEGACY = "services/legacy-batch/src/main/java/com/acme/legacy"
RES = "services/billing-service/src/main/resources"

TWO_ENTITIES = f"{BILLING}/TwoEntities.java"
MIXED_ENTITIES = f"{BILLING}/MixedEntities.java"
NESTED_ENTITY = f"{BILLING}/NestedEntity.java"
DUP_BILLING = f"{BILLING}/Invoice.java"
DUP_LEDGER = f"{LEDGER}/Invoice.java"
UNICODE_QUERY = f"{LEDGER}/LedgerRepository.java"
HUGE_JAVA = f"{LEGACY}/Huge.java"
EMPTY_JAVA = f"{LEGACY}/Empty.java"
LATIN1_JAVA = f"{LEGACY}/Latin1.java"
NUL_JAVA = f"{LEGACY}/NulInside.java"
CRLF_JAVA = f"{LEGACY}/Crlf.java"

BOM_YML = f"{RES}/application-prod.yml"
NOBOM_YML = f"{RES}/application-nobom.yml"
PLACEHOLDER_YML = f"{RES}/application.yml"
SECRETS_YML = f"{RES}/application-secrets.yml"
MULTI_SEG_YML = f"{RES}/application-dev-local.yml"
CRLF_PROPS = f"{RES}/application-legacy.properties"
LF_PROPS = f"{RES}/application-lfprops.properties"
EMPTY_YML = f"{RES}/application-empty.yml"

SPACE_PATH = "docs and notes/guide.md"
UNICODE_DIR_JAVA = "módulo-común/src/main/java/com/acme/uni/UniController.java"
DEEP_JAVA = "deep/" + "/".join(f"l{i:02d}" for i in range(30)) + "/Leaf.java"
GITIGNORED_DIR = "generated"

PLANTED_EXCLUDED_DIRS = ["target", "build", "node_modules", "vendor", "venv",
                         "dist", "out", "coverage"]

_STATE = {}


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _w(root, rel, text):
    path = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _wb(root, rel, data):
    """Bytes, for the files whose whole point is their encoding — never text
    mode, since the default encoding is exactly what is under test."""
    path = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _controller(pkg, name, seg):
    return f"""package {pkg};

import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@RestController
@RequestMapping("/api/{seg}")
public class {name} {{
    @GetMapping("/{{id}}")
    @PreAuthorize(
        "hasRole('{seg.upper()}_READ')"
    )
    public String get(@PathVariable Long id) {{ return "ok"; }}

    @PostMapping
    public String create(@RequestBody String body) {{
        // TODO: validate payload before persisting
        return "created";
    }}
}}
"""


def _service(pkg, name):
    return (f"package {pkg};\n\nimport org.springframework.stereotype.Service;\n\n"
            f"@Service\npublic class {name} {{\n"
            f"    public String handle(String in) {{ return in.trim(); }}\n}}\n")


def _entity(pkg, name, table):
    return (f"package {pkg};\n\nimport jakarta.persistence.*;\n\n"
            f"@Entity\n@Table(name = \"{table}\")\npublic class {name} {{\n"
            f"    @Id\n    private Long id;\n    private String status;\n}}\n")


def build_enterprise_repo(root):
    """Write a deterministic, hostile, multi-module Spring repo.

    Deterministic in the strict sense: fixed content, no randomness, no clock,
    no network — which is what lets the invariant assertions mean anything.
    The hostile bytes are declared inline rather than copied from a checked-in
    tree, because git and editors silently normalize exactly the things under
    test here (BOM, CRLF, lone high bytes).
    """
    os.makedirs(root, exist_ok=True)

    _w(root, "README.md", "# Acme Platform\n\nPre-existing overview.\n")
    _w(root, "pom.xml", "<project><modules/></project>\n")
    _w(root, "build.gradle", """plugins {
    id 'org.springframework.boot' version '3.2.0'
    id 'java'
}
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10'
}
sourceCompatibility = '17'
""")
    _w(root, "settings.gradle", "include 'billing'\ninclude ':ledger'\n")
    _w(root, "gradle/libs.versions.toml", """
[versions]
spring-boot = "3.2.0"
[libraries]
starter = { module = "org.springframework.boot:spring-boot-starter", version.ref = "spring-boot" }
""")
    _w(root, ".gitignore", "/generated/\n*.log\n")
    _w(root, "Dockerfile", "FROM eclipse-temurin:21-jre\nCOPY app.jar /app.jar\n")
    _w(root, "docker-compose.yml", "services:\n  db:\n    image: postgres:16\n")
    _w(root, "ops/k8s/deployment.yaml",
       "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: billing\n")

    # --- billing service ----------------------------------------------------
    _w(root, f"{BILLING}/BillingController.java",
       _controller("com.acme.billing", "BillingController", "billing"))
    _w(root, DUP_BILLING, _entity("com.acme.billing", "Invoice", "billing_invoice"))
    _w(root, f"{BILLING}/InvoiceRepository.java", """package com.acme.billing;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

@Repository
public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    @Query("SELECT i FROM Invoice i WHERE i.status = :status")
    java.util.List<Invoice> byStatus(String status);

    @Query(value = "SELECT * FROM billing_invoice_audit WHERE ts > ?1", nativeQuery = true)
    java.util.List<Object[]> auditSince(String ts);
}
""")

    # Two sibling @Entity classes in ONE file. README.md's stated fix is that
    # each resolves to its own @Table rather than the first @Table in the file
    # being paired with the first class in it. No other fixture in this repo
    # has two entity classes in one file, so that claim was untested.
    _w(root, TWO_ENTITIES, """package com.acme.billing;

import jakarta.persistence.*;

@Entity
@Table(name = "alpha_tbl")
public class Alpha {
    @Id
    private Long id;
}

@Entity
@Table(name = "beta_tbl")
class Beta {
    @Id
    private Long id;
}
""")

    # The sharper form of the same regression: the second entity has no @Table
    # at all, so it must fall back to inferred default naming rather than
    # scavenging the first class's explicit table name.
    _w(root, MIXED_ENTITIES, """package com.acme.billing;

import jakarta.persistence.*;

@Entity
@Table(name = "gamma_explicit")
public class Gamma {
    @Id
    private Long id;
}

@Entity
class Delta {
    @Id
    private Long id;
}
""")

    # Exploratory: the persistence rule uses stopBy: end, so an outer class
    # wrapping a nested @Entity may also match. Characterized by the test
    # rather than assumed.
    _w(root, NESTED_ENTITY, """package com.acme.billing;

import jakarta.persistence.*;

public class NestedEntityHolder {
    @Entity
    @Table(name = "nested_inner")
    public static class InnerEntity {
        @Id
        private Long id;
    }
}
""")

    # Skew: many tiny services in one module and almost none in another, so
    # partitioning has a genuinely lopsided distribution to cope with.
    for i in range(40):
        _w(root, f"{BILLING}/Filler{i:02d}.java",
           _service("com.acme.billing", f"Filler{i:02d}"))

    _w(root, "services/billing-service/src/test/java/com/acme/billing/BillingControllerTest.java",
       "package com.acme.billing;\n\nimport org.junit.jupiter.api.Test;\n\n"
       "class BillingControllerTest {\n    @Test void works() { }\n}\n")

    # --- config: BOM vs no-BOM twins, CRLF vs LF twins, secrets, placeholders
    # The BOM file's line 1 is a *group header* on purpose. ﻿ is category
    # Cf — neither \s nor \w — so a plain utf-8 read leaves it in place, the
    # ^\s*-anchored key regex fails on line 1, the header never enters the
    # indent stack, and every descendant key silently loses its prefix.
    nobom_body = "spring:\n  jwt-secret: s3cr3tliteralvalue\n  datasource:\n    url: jdbc:h2:mem\n"
    _wb(root, BOM_YML, b"\xef\xbb\xbf" + nobom_body.encode("utf-8"))
    _wb(root, NOBOM_YML, nobom_body.encode("utf-8"))

    props_body = "acme.batch.size=100\nacme.batch.retries=3\n"
    _wb(root, CRLF_PROPS, props_body.replace("\n", "\r\n").encode("utf-8"))
    _wb(root, LF_PROPS, props_body.encode("utf-8"))

    _w(root, PLACEHOLDER_YML, """spring:
  application:
    name: billing-service
datasource:
  password: ${DB_PASSWORD}
  api-key: CHANGEME
  client-secret: <set-me>
""")
    _w(root, SECRETS_YML, "aws:\n  access-key-id: AKIAABCDEFGHIJKLMNOP\n"
                          "  password: hunter2literalvalue\n")
    _w(root, MULTI_SEG_YML, "spring:\n  datasource:\n"
                            "    password: multiSegLiteralSecret99\n")
    _wb(root, EMPTY_YML, b"")
    _w(root, f"{RES}/logback-spring.xml",
       "<configuration><root level=\"INFO\"/></configuration>\n")

    # --- ledger service: name collision + non-ASCII in a matched query ------
    _w(root, DUP_LEDGER, _entity("com.acme.ledger", "Invoice", "ledger_invoice"))
    # 'Á' is C3 81 and 'с' is D1 81 — byte 0x81 is undefined in cp1252, so a
    # locale-decoded read of ast-grep's stdout dies here rather than merely
    # mangling. é / 日 decode to silent mojibake instead. Both are regressions
    # against the explicit encoding= on that subprocess call.
    _w(root, UNICODE_QUERY, """package com.acme.ledger;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface LedgerRepository extends JpaRepository<Invoice, Long> {
    @Query("SELECT l FROM Invoice l WHERE l.nombre = 'ÁÍÝ спасибо café 日本語'")
    java.util.List<Invoice> byNombre();
}
""")
    for i in range(2):
        _w(root, f"{LEDGER}/LedgerService{i}.java",
           _service("com.acme.ledger", f"LedgerService{i}"))

    # --- legacy batch: the encoding and size hazards ------------------------
    # ~12 KB, and it carries a @RestController so it is genuinely citable
    # evidence — which is the point of the Ch.5 divergence test.
    _w(root, HUGE_JAVA,
       _controller("com.acme.legacy", "Huge", "huge")
       + ("// generated padding line kept well under any real size limit\n" * 180))
    _wb(root, EMPTY_JAVA, b"")
    _wb(root, LATIN1_JAVA,
        b"package com.acme.legacy;\n// caf\xe9 latin-1 comment\nclass Latin1 { }\n")
    _wb(root, NUL_JAVA, b"package com.acme.legacy;\nclass NulInside { }\n\x00// tail\n")
    _wb(root, CRLF_JAVA,
        _service("com.acme.legacy", "Crlf").replace("\n", "\r\n").encode("utf-8"))
    _w(root, "services/legacy-batch/db/migration/V1__init.sql",
       "CREATE TABLE billing_invoice (id BIGINT PRIMARY KEY);\n")

    # --- path hazards -------------------------------------------------------
    _w(root, SPACE_PATH, "# Guide\n\nA path segment with spaces in it.\n")
    _w(root, UNICODE_DIR_JAVA, _controller("com.acme.uni", "UniController", "uni"))
    _w(root, DEEP_JAVA, _service("com.acme.deep", "Leaf"))

    # --- gitignored dir (empty until write-scope tests plant a stray) -------
    # Do not seed ignored untracked files here: check_pipeline_output lists
    # all ignored-untracked paths as write-scope violations, so a pre-seeded
    # Big.json would fail a clean run. Root-only /generated/ in .gitignore
    # keeps packages/ui/build/generated/ trackable for scan-exclusion tests.

    # --- build noise that must never be scanned, grouped, or cited ---------
    _w(root, "packages/ui/node_modules/leftpad/index.js", "module.exports = 1;\n")
    _w(root, "packages/ui/node_modules/leftpad/Leaked.java",
       _controller("com.acme.noise", "LeakedController", "leak"))
    _w(root, "packages/ui/vendor/thirdparty/Vendored.java",
       _entity("com.acme.noise", "VendoredEntity", "vendored_table"))
    _w(root, "packages/ui/build/generated/Generated.java",
       _entity("com.acme.noise", "GeneratedEntity", "generated_table"))
    _w(root, "services/billing-service/target/generated-sources/Gen.java",
       _controller("com.acme.noise", "GenController", "gen"))
    _w(root, "tools/venv/lib/site.py", "# venv noise\n")
    _w(root, "tools/dist/out.js", "// dist noise\n")
    _w(root, "coverage/report.xml", "<coverage/>\n")
    _w(root, "tools/out/Stale.java", _service("com.acme.noise", "Stale"))


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------

def _run(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def _git(repo, *args):
    return _run(["git"] + list(args), cwd=repo)


def run_chain(repo, out_dir):
    """The documented command series, as real subprocesses.

    Step-by-step rather than delegating to run_pipeline_local.py, so each
    step's own exit code is observable. The four LLM stages are filled in by
    calling that script's mock builders in-process — they are the only part of
    the chain a plain Python process cannot run for real.
    """
    steps = {}
    manifest = os.path.join(out_dir, "run_manifest.json")
    signals = os.path.join(out_dir, "spring_signals.json")
    groups = os.path.join(out_dir, "groups.json")
    edges = os.path.join(out_dir, "cross_group_edges.json")
    preflight = os.path.join(out_dir, "capacity_preflight_report.json")
    docs = os.path.join(repo, "docs")
    snapshots = []

    def record(name, proc):
        steps[name] = proc
        if os.path.isfile(manifest):
            with open(manifest, encoding="utf-8") as f:
                snapshots.append((name, json.load(f)))

    def manifest_cmd(*args):
        return [PY, "-m", "doc_engine.tools.run_manifest", *args]

    record("init", _run(manifest_cmd("init", repo, "--out", manifest)))
    record("start_signal_scan", _run(manifest_cmd("start-stage", manifest, "signal_scan")))
    record("signal_scan", _run([
        PY, "-m", "doc_engine.tools.spring_signal_scan", repo, "--out", signals,
        "--scanners", "filesystem,ast-grep",
    ]))
    record("end_signal_scan",
           _run(manifest_cmd("end-stage", manifest, "signal_scan", "--status", "complete")))
    record("start_partition", _run(manifest_cmd("start-stage", manifest, "partition")))
    record("partition", _run([PY, "-m", "doc_engine.tools.partition_repo", repo,
                              "--max-tokens", MAX_TOKENS, "--out", groups]))
    record("end_partition",
           _run(manifest_cmd("end-stage", manifest, "partition", "--status", "complete")))
    record("cross_group_edges", _run([PY, "-m", "doc_engine.tools.build_cross_group_edges",
                                      groups, signals, "--out", edges]))
    record("capacity_preflight", _run([PY, "-m", "doc_engine.tools.capacity_preflight", repo,
                                       "--groups-file", groups, "--signals-file", signals,
                                       "--max-tokens", MAX_TOKENS, "--out", preflight]))

    signals_data = json.load(open(signals, encoding="utf-8"))
    groups_data = json.load(open(groups, encoding="utf-8"))
    edges_data = json.load(open(edges, encoding="utf-8"))

    quiet = lambda *a, **k: None  # noqa: E731
    today = datetime.date.today().isoformat()
    pool = load_citations(signals_data, repo)
    todos = sweep_todos(repo)
    n = groups_data["num_groups"]

    record("start_file_summarize",
           _run(manifest_cmd("start-stage", manifest, "file_summarize", "--fanout", str(n))))
    mock_file_summaries(out_dir, groups_data, pool, edges_data, quiet)
    record("end_file_summarize",
           _run(manifest_cmd("end-stage", manifest, "file_summarize", "--status", "complete")))

    record("start_architect",
           _run(manifest_cmd("start-stage", manifest, "architect", "--fanout", str(n + 1))))
    mock_architecture(out_dir, groups_data, pool, quiet)
    record("end_architect",
           _run(manifest_cmd("end-stage", manifest, "architect", "--status", "complete")))

    record("start_gap", _run(manifest_cmd("start-stage", manifest,
                                          "gap_analysis_interview", "--fanout", "1")))
    mock_gap_and_interview(out_dir, pool, todos, today, quiet)
    record("end_gap", _run(manifest_cmd("end-stage", manifest,
                                        "gap_analysis_interview", "--status", "complete")))

    answers = json.load(open(os.path.join(out_dir, "interview_answers.json"), encoding="utf-8"))
    record("start_doc_writer",
           _run(manifest_cmd("start-stage", manifest, "doc_writer", "--fanout", "14")))
    mock_docs(docs, pool, todos, answers, today,
              find_existing_readme(repo), quiet)
    record("end_doc_writer",
           _run(manifest_cmd("end-stage", manifest, "doc_writer", "--status", "complete")))

    record("gate", _run([PY, "-m", "doc_engine.tools.check_pipeline_output", docs, "--target-repo", repo]))
    record("citation_coverage", _run([PY, "-m", "doc_engine.tools.citation_coverage", docs,
                                      "--target-repo", repo]))
    record("secrets", _run([PY, "-m", "doc_engine.tools.check_no_secrets_leaked",
                            os.path.join(out_dir, "summaries.json"), docs]))
    record("finalize", _run(manifest_cmd(
        "finalize", manifest, "--signals-file", signals, "--docs-dir", docs,
        "--interview-file", os.path.join(out_dir, "interview_answers.json"),
        "--preflight-file", preflight)))
    # Deliberately after finalize: --manifest reads file_signatures, which is
    # written by finalize. Earlier would compare against nothing.
    record("drift", _run([PY, "-m", "doc_engine.tools.spring_drift_check", repo, signals,
                          "--manifest", manifest,
                          "--out", os.path.join(out_dir, "drift_report.json")]))
    return steps, snapshots


def setUpModule():
    if not shutil.which("ast-grep"):
        raise unittest.SkipTest("ast-grep not on PATH")
    if not shutil.which("git"):
        raise unittest.SkipTest("git not on PATH")

    tmp = tempfile.mkdtemp(prefix="kitchensink_")
    repo = os.path.join(tmp, "repo")
    out_dir = os.path.join(tmp, "run")
    os.makedirs(out_dir)
    build_enterprise_repo(repo)

    # Identity on the command line, never ambient config — a bare commit on a
    # runner with no configured identity fails.
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=kitchensink@example.invalid",
         "-c", "user.name=kitchensink", "commit", "-qm", "init")

    steps, snapshots = run_chain(repo, out_dir)

    def load(name):
        with open(os.path.join(out_dir, name), encoding="utf-8") as f:
            return json.load(f)

    def load_facts():
        path = os.path.join(out_dir, "facts.jsonl")
        if not os.path.isfile(path):
            return []
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    _STATE.update({
        "tmp": tmp, "repo": repo, "out": out_dir, "steps": steps,
        "snapshots": snapshots, "docs": os.path.join(repo, "docs"),
        "signals": load("spring_signals.json"),
        "covering_proof": load("covering_proof.json"),
        "facts": load_facts(),
        "groups": load("groups.json"),
        "edges": load("cross_group_edges.json"),
        "manifest": load("run_manifest.json"),
        "preflight": load("capacity_preflight_report.json"),
    })


def tearDownModule():
    tmp = _STATE.get("tmp")
    if tmp and os.path.isdir(tmp):
        # ignore_errors: .git's read-only object files make rmtree fail on
        # Windows, and a leftover temp dir is harmless while a teardown
        # exception is a confusing red run.
        shutil.rmtree(tmp, ignore_errors=True)


def _evidence_files(signals):
    for rows in (signals.get("evidence") or {}).values():
        for row in rows:
            yield row["file"]


def _grouped(groups):
    return {f for g in groups["groups"] for f in g["files"]}


def _copy_docs():
    scratch = tempfile.mkdtemp(prefix="ks_docs_")
    shutil.copytree(_STATE["docs"], os.path.join(scratch, "docs"))
    return scratch, os.path.join(scratch, "docs")


def _miscase_first_tag(case, path):
    """Lowercase the first tag word in a doc, asserting the mutation landed.

    Without the assertion these tests pass vacuously against a document whose
    evidence bucket happened to be empty — the injected fault would simply not
    exist, and 'the gate did not fail' would prove nothing.
    """
    text = open(path, encoding="utf-8").read()
    mutated = text.replace("[Evidenced —", "[evidenced —", 1)
    case.assertNotEqual(text, mutated, f"{os.path.basename(path)} carried no tag to miscase")
    with open(path, "w", encoding="utf-8") as f:
        f.write(mutated)


def _has_segment(rel, name):
    """Segment-wise membership. A substring check would call
    'outbound/Client.java' an 'out' directory."""
    return name in rel.split("/")


# ---------------------------------------------------------------------------
# Ch. 1 — a fault must become a visible failure
# ---------------------------------------------------------------------------

class Ch01FaultInjectionTest(unittest.TestCase):
    """The suite's thesis.

    DDIA Ch.1 distinguishes a fault (a component deviating from spec) from a
    failure (the system stopping service), and argues for deliberately
    inducing faults, because an untriggered fault-tolerance mechanism is
    indistinguishable from one that does not work. Applied here: before this
    class, nothing proved a corrupted run actually fails.
    """

    def _gate(self, docs, *extra):
        # --no-write-check because these run against a *copy* of docs/ that
        # lives outside the target repo. With docs elsewhere the write check
        # asserts nothing in the repo changed, which the run's own real docs/
        # legitimately violates. The write check gets its own dedicated test
        # in Ch12, against the real in-repo path.
        return _run([PY, "-m", "doc_engine.tools.check_pipeline_output", docs,
                     "--target-repo", _STATE["repo"], "--no-write-check", *extra])

    def test_clean_output_passes(self):
        """The control. Without it every assertion below could pass for the
        wrong reason."""
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        proc = self._gate(docs)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_missing_doc_becomes_a_process_failure(self):
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        os.remove(os.path.join(docs, "testing.md"))
        proc = self._gate(docs)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing expected doc: testing.md", proc.stderr)

    def test_a_miscased_tag_is_a_fault_that_never_becomes_a_failure(self):
        """Deliberately adjacent to the test above: the same magnitude of
        defect, and the gate the pipeline actually blocks on returns 0. A
        lowercase tag word matches neither the valid patterns nor the
        malformed-span detector, so the citation is scored as absent
        everywhere. Fault without failure — the contrast is the point."""
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        _miscase_first_tag(self, os.path.join(docs, "database.md"))
        self.assertEqual(self._gate(docs).returncode, 0)

    def test_operator_error_exits_two_not_one(self):
        """Exit 2 (the checker could not run) is a different condition from
        exit 1 (the run is bad). A caller that collapses them loses that."""
        proc = self._gate(os.path.join(_STATE["tmp"], "no-such-dir"))
        self.assertEqual(proc.returncode, 2)


# ---------------------------------------------------------------------------
# Ch. 3 — entity_table_map as a secondary index on a non-unique key
# ---------------------------------------------------------------------------

class Ch03DerivedIndexTest(unittest.TestCase):
    """entity_table_map is an index over evidence.persistence keyed by bare
    class name — package deliberately excluded, so the key is not unique.
    "Two entities in one file" is an index-build question; the cross-module
    name clash is a key-resolution question."""

    def setUp(self):
        self.signals = _STATE["signals"]
        self.mapping = self.signals["entity_table_map"]

    def test_two_entities_in_one_file_resolve_to_their_own_tables(self):
        """README.md's stated fix — each entity's own @Table, rather than the
        first @Table in the file paired with the first class in it. Untested
        until now: no other fixture has two entity classes in one file."""
        self.assertIn("Alpha", self.mapping)
        self.assertIn("Beta", self.mapping)
        self.assertEqual(self.mapping["Alpha"]["table"], "alpha_tbl")
        self.assertEqual(self.mapping["Beta"]["table"], "beta_tbl")
        self.assertEqual(self.mapping["Alpha"]["file"], TWO_ENTITIES)
        self.assertEqual(self.mapping["Beta"]["file"], TWO_ENTITIES)

    def test_entity_without_its_own_table_does_not_borrow_a_siblings(self):
        """The sharper form: Delta has no @Table, so it must fall back to
        inferred default naming rather than scavenging Gamma's explicit one."""
        self.assertEqual(self.mapping["Gamma"]["table"], "gamma_explicit")
        self.assertIn("Delta", self.mapping)
        self.assertNotEqual(self.mapping["Delta"]["table"], "gamma_explicit")
        self.assertEqual(self.mapping["Delta"]["table"], "delta")

    def test_non_unique_key_collision_is_contested_and_deterministic(self):
        """Same bare class name in two modules. The evidence bucket keeps both
        rows; the index keeps one citation-identity entry keyed by lowest file
        path, marked status=contested with both candidates listed so JPQL
        lineage can refuse rather than guess."""
        entry = self.mapping["Invoice"]
        self.assertEqual(entry["file"], min(DUP_BILLING, DUP_LEDGER))
        self.assertEqual(entry["status"], "contested")
        self.assertEqual(
            {(c["file"], c["table"]) for c in entry["candidates"]},
            {(DUP_BILLING, "billing_invoice"), (DUP_LEDGER, "ledger_invoice")},
        )
        rows = {r["file"] for r in self.signals["evidence"]["persistence"]
                if r.get("class_name") == "Invoice"}
        self.assertEqual(rows, {DUP_BILLING, DUP_LEDGER},
                         "the index may drop a row; the evidence bucket must not")
        jpql = [e for e in self.signals["evidence"]["raw_queries"]
                if e.get("query_kind") == "jpql" and "Invoice" in (e.get("query") or "")]
        self.assertTrue(jpql, "fixture must include JPQL over the contested name")
        for e in jpql:
            self.assertFalse(e["lineage"]["available"], e)
            self.assertIn("contested", e["lineage"]["reason"])

    def test_index_keys_are_sorted_and_every_entry_resolves(self):
        keys = list(self.mapping)
        self.assertEqual(keys, sorted(keys))
        for name, entry in self.mapping.items():
            with self.subTest(entity=name):
                self.assertTrue(os.path.isfile(
                    os.path.join(_STATE["repo"], entry["file"].replace("/", os.sep))))


# ---------------------------------------------------------------------------
# Ch. 4 — encoding
# ---------------------------------------------------------------------------

class Ch04EncodingTest(unittest.TestCase):

    def setUp(self):
        self.signals = _STATE["signals"]
        self.groups = _STATE["groups"]

    def _skip_reason(self, rel):
        for s in self.groups["skipped"]:
            if s["file"] == rel:
                return s["reason"]
        return None

    def test_bom_and_no_bom_twins_produce_identical_key_sets(self):
        """A BOM read as plain utf-8 leaves a literal ﻿, which is category
        Cf — neither \\s nor \\w — so the ^\\s*-anchored key regex fails on line
        1 entirely. When line 1 is a group header it never enters the indent
        stack and every descendant key silently loses its prefix, which yields
        a key set that looks plausible and is wholly wrong. Byte-identical
        twins are the assertion; membership of one key would not have caught
        the prefix loss."""
        keys = self.signals["config_key_sets"]
        self.assertIn(BOM_YML, keys)
        self.assertEqual(keys[BOM_YML], keys[NOBOM_YML])
        self.assertIn("spring.jwt-secret", keys[BOM_YML])

    def test_secret_on_the_line_after_a_bom_header_is_still_flagged(self):
        """Same root cause, confidentiality side: a blinded line 1 shifts the
        indent stack, and the secret heuristics are anchored the same way."""
        zones = self.signals["redaction_zones"]
        self.assertIn(BOM_YML, zones, "BOM'd config produced no redaction zones")
        self.assertEqual({h["line"] for h in zones[BOM_YML]},
                         {h["line"] for h in zones[NOBOM_YML]})

    def test_multi_segment_profile_names_are_recognized_as_config(self):
        """Multi-segment Spring profiles (application-dev-local.yml) must be
        ingested: CONFIG_NAME_PATTERNS uses [\\w.-]+ so hyphenated profile
        segments reach config_key_sets and redaction_zones."""
        self.assertTrue(any(p.match("application-dev-local.yml")
                            for p in spring_signal_scan.CONFIG_NAME_PATTERNS))
        self.assertTrue(any(p.match("application-prod.yml")
                            for p in spring_signal_scan.CONFIG_NAME_PATTERNS))
        self.assertTrue(any(p.match("bootstrap-dev-local.properties")
                            for p in spring_signal_scan.CONFIG_NAME_PATTERNS))
        keys = self.signals["config_key_sets"]
        self.assertIn(MULTI_SEG_YML, keys)
        self.assertIn("spring.datasource.password", keys[MULTI_SEG_YML])
        zones = self.signals["redaction_zones"]
        self.assertIn(MULTI_SEG_YML, zones,
                      "multi-segment profile must receive credential scanning")

    def test_crlf_and_lf_twins_produce_identical_key_sets(self):
        keys = self.signals["config_key_sets"]
        self.assertEqual(keys[CRLF_PROPS], keys[LF_PROPS])

    def test_crlf_java_is_scanned_with_sane_line_numbers(self):
        self.assertIn(CRLF_JAVA, _grouped(self.groups))
        for rows in (self.signals.get("evidence") or {}).values():
            for row in rows:
                if row["file"] == CRLF_JAVA:
                    self.assertGreaterEqual(row.get("line", 1), 1)

    def test_invalid_utf8_is_included_via_the_latin1_fallback(self):
        """latin-1 accepts every byte, so this is a silent mis-decode by
        design. Pinned as stated behavior, not endorsed."""
        self.assertIn(LATIN1_JAVA, _grouped(self.groups))
        self.assertIsNone(self._skip_reason(LATIN1_JAVA))

    def test_nul_byte_file_is_skipped_as_binary(self):
        self.assertEqual(self._skip_reason(NUL_JAVA), "binary")

    def test_zero_byte_java_costs_exactly_one_token(self):
        self.assertIn(EMPTY_JAVA, _grouped(self.groups))
        self.assertIsNone(self._skip_reason(EMPTY_JAVA))
        tokens, reason = partition_repo.estimate_tokens(
            os.path.join(_STATE["repo"], EMPTY_JAVA.replace("/", os.sep)), 2_000_000)
        self.assertEqual((tokens, reason), (1, None))

    def test_zero_byte_config_is_absent_rather_than_present_and_empty(self):
        self.assertNotIn(EMPTY_YML, self.signals["config_key_sets"])
        self.assertNotIn(EMPTY_YML, self.signals["redaction_zones"])

    def test_build_gradle_signals_extracted(self):
        """Build scripts are now structurally read for plugins, dependencies,
        and toolchains — not just classified by filename."""
        deployment = self.signals["evidence"]["deployment"]
        plugins = [r for r in deployment if r.get("rule_id") == "deployment__build_plugin"]
        self.assertEqual(
            {(p["plugin_id"], p["plugin_version"]) for p in plugins},
            {("org.springframework.boot", "3.2.0"), ("java", None)},
        )
        deps = [r for r in deployment if r.get("rule_id") == "deployment__build_dependency"]
        self.assertIn(
            ("implementation", "org.springframework.boot", "spring-boot-starter-web"),
            {(d["configuration"], d["coordinate"].get("group"), d["coordinate"].get("name")) for d in deps},
        )
        tcs = [r for r in deployment if r.get("rule_id") == "deployment__build_toolchain"]
        self.assertEqual(tcs[0]["toolchain_value"], "17")
        mods = [r for r in deployment if r.get("rule_id") == "deployment__build_module"]
        self.assertEqual({m["module"] for m in mods}, {"billing", "ledger"})
        catalogs = [r for r in deployment if r.get("rule_id") == "deployment__version_catalog"]
        self.assertEqual({c["catalog_kind"] for c in catalogs}, {"version", "library"})

    def test_non_ascii_source_is_neither_dropped_nor_mangled(self):
        matches = [row.get("match", "")
                   for rows in (self.signals.get("evidence") or {}).values()
                   for row in rows]
        blob = "\n".join(matches)
        self.assertNotIn("Ã", blob, "mojibake in evidence match text")
        self.assertNotIn("�", blob, "replacement chars in evidence match text")

    def test_scan_survives_non_ascii_under_a_non_utf8_locale(self):
        """Regression test for the locale-codec decode of ast-grep's stdout.
        ast-grep emits UTF-8; decoded with the locale's preferred encoding a
        character whose UTF-8 contains 0x81/0x8D/0x8F/0x90/0x9D (Á is C3 81,
        с is D1 81) raises UnicodeDecodeError and kills the scan, while é/日
        degrade to silent mojibake. Forcing an ASCII/cp1252 locale in the
        child reproduces the original conditions exactly."""
        env = dict(os.environ)
        env.update({"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0",
                    "PYTHONCOERCECLOCALE": "0"})
        # Scoped to a one-file tree rather than the whole fixture: it isolates
        # the variable under test and keeps a full second ast-grep pass out of
        # the suite's runtime.
        with tempfile.TemporaryDirectory() as d:
            mini = os.path.join(d, "repo")
            shutil.copytree(os.path.join(_STATE["repo"], LEDGER.replace("/", os.sep)),
                            os.path.join(mini, "src"))
            proc = _run([PY, "-m", "doc_engine.tools.spring_signal_scan", mini,
                         "--out", os.path.join(d, "s.json"),
                         "--scanners", "filesystem,ast-grep"], env=env)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            with open(os.path.join(d, "s.json"), encoding="utf-8") as f:
                mini_signals = json.load(f)
            blob = json.dumps(mini_signals, ensure_ascii=False)
            self.assertNotIn("Ã", blob)
            self.assertNotIn("�", blob)

    def test_unicode_space_and_deep_paths_survive_the_walk(self):
        grouped = _grouped(self.groups)
        for rel in (UNICODE_DIR_JAVA, SPACE_PATH, DEEP_JAVA):
            with self.subTest(path=rel):
                self.assertIn(rel, grouped)
                self.assertTrue(os.path.isfile(
                    os.path.join(_STATE["repo"], rel.replace("/", os.sep))))


# ---------------------------------------------------------------------------
# Ch. 5 — four derived replicas of one fact
# ---------------------------------------------------------------------------

class Ch05ConvergenceTest(unittest.TestCase):
    """signals.file_signatures, groups.json's file union, manifest
    .file_signatures and cross_group_edges' node set are four derived copies
    of one fact — the repo's file set — produced by three different walk
    implementations. Where they must converge, assert it; where they provably
    diverge, pin the divergence so it is a known trade-off rather than a
    surprise."""

    def test_manifest_signatures_are_the_scan_signatures(self):
        self.assertEqual(_STATE["manifest"]["file_signatures"],
                         _STATE["signals"]["file_signatures"])

    def test_empty_file_hashes_to_the_known_empty_digest(self):
        self.assertEqual(_STATE["signals"]["file_signatures"][EMPTY_JAVA], EMPTY_SHA256)

    def test_edge_nodes_are_a_subset_of_grouped_files(self):
        grouped = _grouped(_STATE["groups"])
        referenced = set()
        for _gid, block in _STATE["edges"]["groups"].items():
            for arc in block.get("outbound", []) + block.get("inbound", []):
                for key in ("from", "to", "from_file", "to_file", "file"):
                    if isinstance(arc, dict) and isinstance(arc.get(key), str):
                        referenced.add(arc[key])
        self.assertEqual(referenced - grouped, set())

    def test_preflight_reuses_the_partition_rather_than_re_deriving_it(self):
        self.assertEqual(_STATE["preflight"]["num_groups"], _STATE["groups"]["num_groups"])

    def test_nul_file_diverges_between_the_two_walkers(self):
        """Deterministic disagreement: partition skips it as binary, the scan
        still hashes it."""
        self.assertNotIn(NUL_JAVA, _grouped(_STATE["groups"]))
        self.assertIn(NUL_JAVA, _STATE["signals"]["file_signatures"])

    def test_a_file_can_be_cited_as_evidence_yet_belong_to_no_group(self):
        """The sharpest divergence, and the first CLI-level exercise of
        --max-file-bytes. partition_repo.py enforces a size ceiling;
        spring_signal_scan.py has none. So above the ceiling a file is
        citable evidence in the final documentation that no Stage-1 subagent
        will ever summarize, and nothing in the pipeline reconciles that."""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "groups.json")
            proc = _run([PY, "-m", "doc_engine.tools.partition_repo", _STATE["repo"],
                         "--max-tokens", MAX_TOKENS,
                         "--max-file-bytes", SMALL_FILE_BYTES, "--out", out])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            with open(out, encoding="utf-8") as f:
                small = json.load(f)
        skipped = {s["file"]: s["reason"] for s in small["skipped"]}
        self.assertIn(HUGE_JAVA, skipped)
        self.assertRegex(skipped[HUGE_JAVA], r"^too-large \(\d+ bytes\)$")
        self.assertNotIn(HUGE_JAVA, _grouped(small))
        self.assertIn(HUGE_JAVA, set(_evidence_files(_STATE["signals"])))


# ---------------------------------------------------------------------------
# Ch. 6 — partitioning, skew, hot spots
# ---------------------------------------------------------------------------

class Ch06PartitioningTest(unittest.TestCase):

    def setUp(self):
        self.groups = _STATE["groups"]
        self.max_tokens = self.groups["max_tokens_per_group"]

    def _membership(self):
        where = {}
        for g in self.groups["groups"]:
            for f in g["files"]:
                where.setdefault(f, set()).add(g["id"])
        return where

    def test_overlap_never_spans_more_than_two_groups(self):
        """Overlap must stay between adjacent groups only — no cascade into three."""
        for f, ids in self._membership().items():
            if len(ids) > 1:
                with self.subTest(file=f):
                    self.assertEqual(ids, {min(ids), min(ids) + 1})

    def test_every_file_lands_in_at_least_one_group(self):
        """The invariant that must hold regardless of the cascade above:
        overlap may duplicate, but it must never drop."""
        skipped = {s["file"] for s in self.groups["skipped"]}
        repo = _STATE["repo"]
        # dfs_file_list yields absolute paths; groups.json carries them
        # relative and forward-slashed. docs/ is excluded because the run
        # wrote it *after* partitioning.
        walked = {os.path.relpath(w, repo).replace(os.sep, "/")
                  for w in partition_repo.dfs_file_list(
                      repo, DEFAULT_EXCLUDED_DIRS,
                      partition_repo.DEFAULT_EXCLUDED_EXTS,
                      partition_repo.DEFAULT_EXCLUDED_FILES)}
        walked = {w for w in walked if not w.startswith("docs/")}
        self.assertEqual(walked - set(self._membership()) - skipped, set())

    def test_build_groups_terminates_across_a_range_of_budgets(self):
        """REGRESSION — build_groups used to hang outright.

        The zero-progress guard only re-checked the hard cap, so a carry that
        was itself large enough to re-trip the *soft target* looped forever:
        the same file was re-evaluated against an identical group, `i` never
        advanced, and the group list grew without bound. Reproduced with a
        2916-token file at --max-tokens 3000 (target_per_group 2901): 2927
        groups and climbing before the probe was killed.

        Run in a subprocess with a hard timeout, because the failure mode is a
        hang — an in-process assertion would take the whole suite down with it
        rather than reporting.
        """
        # noqa UP031: the %-formatting here is deliberate and not a style
        # holdover. This string is *source code* for a subprocess, and %r
        # renders the path as a valid Python literal with quoting and
        # backslash escaping already correct -- which matters on Windows,
        # where an f-string would interpolate C:\Users\... raw and produce a
        # probe that fails to parse.
        probe = (  # noqa: UP031
            "import os\n"
            "from doc_engine.tools import partition_repo as pr\n"
            "from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS as D\n"
            "repo = %r\n"
            "files = list(pr.dfs_file_list(repo, D, pr.DEFAULT_EXCLUDED_EXTS,"
            " pr.DEFAULT_EXCLUDED_FILES))\n"
            "ft = []\n"
            "for rel in files:\n"
            "    t, r = pr.estimate_tokens(os.path.join(repo, rel.replace('/', os.sep)),"
            " 2000000)\n"
            "    if r is None: ft.append((rel, t))\n"
            "for mt in (1000, 2000, 3000, 4000, 5000, 8000, 120000):\n"
            "    g = pr.build_groups(ft, mt, 0.10)\n"
            "    seen = {f for grp in g for f, _ in grp}\n"
            "    assert seen == {f for f, _ in ft}, mt\n"
            "print('OK')\n"
        ) % (_STATE["repo"],)
        try:
            proc = subprocess.run([PY, "-c", probe], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=120)
        except subprocess.TimeoutExpired:
            self.fail("build_groups did not terminate — the zero-progress guard "
                      "regressed (see this test's docstring)")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK", proc.stdout)

    def test_group_token_counts_are_internally_consistent(self):
        for g in self.groups["groups"]:
            with self.subTest(group=g["id"]):
                total = 0
                for rel in g["files"]:
                    tokens, reason = partition_repo.estimate_tokens(
                        os.path.join(_STATE["repo"], rel.replace("/", os.sep)), 2_000_000)
                    self.assertIsNone(reason)
                    total += tokens
                self.assertEqual(g["est_tokens"], total)

    def test_a_hot_spot_gets_its_own_group_rather_than_inflating_a_shared_one(self):
        for g in self.groups["groups"]:
            if g["est_tokens"] > self.max_tokens:
                with self.subTest(group=g["id"]):
                    self.assertEqual(len(g["files"]), 1)

    def test_skew_is_actually_present(self):
        """Guards the guard: if the fixture stopped being lopsided, the
        hot-spot test above would pass vacuously."""
        sizes = [g["est_tokens"] for g in self.groups["groups"]]
        self.assertGreater(len(sizes), 1)
        self.assertGreater(max(sizes), 2 * (sum(sizes) / len(sizes)))

    def test_no_excluded_directory_is_scanned_grouped_or_cited(self):
        """Segment-wise, not substring — 'out' must not match
        'outbound/Client.java'. This is also the first assertion anywhere in
        this repo that excluded dirs stay out of groups.json."""
        grouped = _grouped(self.groups)
        cited = set(_evidence_files(_STATE["signals"]))
        signed = set(_STATE["signals"]["file_signatures"])
        entities = {v["file"] for v in _STATE["signals"]["entity_table_map"].values()}
        for d in PLANTED_EXCLUDED_DIRS:
            for collection, label in ((grouped, "groups"), (cited, "evidence"),
                                      (signed, "file_signatures"),
                                      (entities, "entity_table_map")):
                with self.subTest(excluded=d, where=label):
                    self.assertEqual([f for f in collection if _has_segment(f, d)], [])

    def test_group_file_lists_are_dfs_preorder_not_sorted(self):
        """A deliberate inverse assertion. dfs_file_list emits a directory's
        own files before recursing into its subdirectories, so a root-level
        file precedes everything nested regardless of lexicographic order.
        Asserting sortedness here would assert a falsehood; this documents the
        contract and fails loudly if someone "fixes" the ordering."""
        unsorted = [g["id"] for g in self.groups["groups"]
                    if g["files"] != sorted(g["files"])]
        self.assertTrue(unsorted, "no group was DFS-ordered — fixture shape changed")


# ---------------------------------------------------------------------------
# Ch. 7 — lost updates and atomic writes
# ---------------------------------------------------------------------------

class Ch07LostUpdateTest(unittest.TestCase):

    def test_concurrent_read_modify_write_loses_an_update(self):
        """SKILL.md's concurrency contract — start-stage/end-stage exactly once
        per stage, orchestrating thread only — is load-bearing because this
        module has no locking, as its own docstring states. Demonstrated by
        replaying the forbidden interleaving deterministically rather than
        with threads: a racing test is a flaky test, and the interleaving is
        the point, not the race."""
        scratch = tempfile.mkdtemp(prefix="ks_lost_")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        path = os.path.join(scratch, "run_manifest.json")
        run_manifest._write_json_atomic(path, run_manifest.build_init_manifest(_STATE["repo"]))

        a = run_manifest._read_json(path)
        b = run_manifest._read_json(path)
        run_manifest.start_stage(a, "architect")
        run_manifest._write_json_atomic(path, a)
        run_manifest.start_stage(b, "doc_writer")
        run_manifest._write_json_atomic(path, b)

        names = [s["name"] for s in run_manifest._read_json(path)["stages"]]
        self.assertEqual(names, ["doc_writer"])
        self.assertNotIn("architect", names,
                         "if this now passes, run_manifest.py grew locking and "
                         "SKILL.md's concurrency contract can be relaxed")

    def test_a_failed_write_leaves_the_previous_manifest_intact(self):
        """Temp file plus os.replace, so a crash mid-write cannot leave a
        half-written manifest for the next stage's json.load(). Deterministic:
        the failure is injected, not waited for."""
        scratch = tempfile.mkdtemp(prefix="ks_atomic_")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        path = os.path.join(scratch, "run_manifest.json")
        run_manifest._write_json_atomic(path, run_manifest.build_init_manifest(_STATE["repo"]))
        before = open(path, "rb").read()

        with mock.patch.object(run_manifest.json, "dump",
                               side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                run_manifest._write_json_atomic(path, {"stages": [{"name": "x"}]})

        self.assertEqual(open(path, "rb").read(), before)
        json.loads(before.decode("utf-8"))
        leftovers = [n for n in os.listdir(scratch) if n != "run_manifest.json"]
        self.assertEqual(leftovers, [], f"temp file left behind: {leftovers}")

    def test_the_real_run_honored_the_once_per_stage_contract(self):
        names = [s["name"] for s in _STATE["manifest"]["stages"]]
        self.assertEqual(sorted(names), sorted([
            "architect", "doc_writer", "file_summarize",
            "gap_analysis_interview", "partition", "signal_scan"]))
        self.assertEqual(len(names), len(set(names)))
        for stage in _STATE["manifest"]["stages"]:
            with self.subTest(stage=stage["name"]):
                self.assertEqual(stage["status"], "complete")

    def test_manifest_is_never_observed_half_written(self):
        snapshots = _STATE["snapshots"]
        self.assertGreater(len(snapshots), 10)
        for name, data in snapshots:
            self.assertIn("stages", data, f"manifest malformed after {name}")


# ---------------------------------------------------------------------------
# Ch. 10 — the command chain, and staleness
# ---------------------------------------------------------------------------

class Ch10CommandChainTest(unittest.TestCase):

    def test_every_chain_step_exited_zero(self):
        failures = {n: (p.returncode, (p.stdout or "") + (p.stderr or ""))
                    for n, p in _STATE["steps"].items() if p.returncode != 0}
        self.assertEqual(failures, {}, f"non-zero steps: {list(failures)}")

    def test_the_gate_passed_on_a_clean_run(self):
        gate = _STATE["steps"]["gate"]
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        self.assertIn("OK: all 14 docs present", gate.stdout)

    def test_all_fourteen_docs_written(self):
        present = {os.path.splitext(n)[0] for n in os.listdir(_STATE["docs"])
                   if n.endswith(".md")}
        self.assertEqual(present, set(VALID_DOC_FILES))

    def test_every_expected_artifact_exists_and_is_non_empty(self):
        out = _STATE["out"]
        for name in ("spring_signals.json", "covering_proof.json", "facts.jsonl",
                     "groups.json", "cross_group_edges.json",
                     "capacity_preflight_report.json", "run_manifest.json",
                     "summaries.json", "architecture_merged.md", "gap_questions.json",
                     "interview_answers.json", "drift_report.json"):
            with self.subTest(artifact=name):
                path = os.path.join(out, name)
                self.assertTrue(os.path.isfile(path), f"{name} missing")
                self.assertGreater(os.path.getsize(path), 0)

    def test_covering_proof_verifies_against_path_a_inventory(self):
        """Deviation: chain greens without a verifiable covering_proof sibling."""
        signals = _STATE["signals"]
        proof = _STATE["covering_proof"]
        self.assertNotIn("_covering_proof", signals)
        self.assertNotIn("_scan_partials_meta", signals)
        ok, why = verify_covering_proof(
            proof,
            file_signatures=signals["file_signatures"],
            scanner_version=signals["scanner_version"],
        )
        self.assertTrue(ok, why)
        scanners = {r["scanner"] for r in proof["receipts"]}
        self.assertEqual(scanners, {"filesystem", "ast-grep"})
        self.assertTrue(all(r["status"] == "complete" for r in proof["receipts"]))

    def test_facts_ledger_has_absence_or_unproven_stamps(self):
        """Deviation: dual-emit facts omit ABSENCE/UNPROVEN covering writers."""
        predicates = {row.get("predicate") for row in _STATE["facts"]}
        self.assertTrue(
            predicates & {"ABSENCE", "UNPROVEN"},
            f"expected ABSENCE/UNPROVEN in facts; got {sorted(predicates)}",
        )
        # Default filesystem,ast-grep profile must not claim entity recall.
        self.assertNotIn("RECALL_MISS", predicates)

    def test_signal_scan_stderr_emits_covering_event(self):
        """Deviation: covering_proof written silently with no covering_emit telemetry."""
        err = _STATE["steps"]["signal_scan"].stderr or ""
        compact = err.replace(" ", "")
        self.assertIn('"event":"covering_emit"', compact, err[-2000:])
        self.assertIn("inventory_root", err)

    def test_summaries_cover_every_grouped_file(self):
        with open(os.path.join(_STATE["out"], "summaries.json"), encoding="utf-8") as f:
            summarized = {e["file"] for e in json.load(f)}
        self.assertEqual(_grouped(_STATE["groups"]) - summarized, set())

    def test_a_derived_view_is_not_stale_against_its_own_input(self):
        """Integrity catches corruption; drift catches staleness. Against the
        very scan the docs were derived from, nothing can be stale."""
        with open(os.path.join(_STATE["out"], "drift_report.json"), encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual({r["status"] for r in report["results"]}, {"unchanged"})

    def test_run_pipeline_local_driver_runs_end_to_end(self):
        """The driver's first test. It is the packaged form of this same
        series, exercised against the small checked-in fixture rather than
        paying for a second enterprise-scale scan."""
        with tempfile.TemporaryDirectory() as d:
            run_dir = os.path.join(d, "run")
            proc = _run([PY, "-m", "doc_engine.pipeline.local_runner",
                         os.path.join(SCRIPT_DIR, "fixtures", "spring_signals"),
                         "--out-dir", run_dir, "--skip-drift",
                         "--allow-mock"])
            self.assertEqual(proc.returncode, 0, proc.stdout[-4000:] + proc.stderr[-2000:])
            self.assertIn("RESULT: every gate passed", proc.stdout)
            cert_path = os.path.join(run_dir, "certification.json")
            self.assertTrue(os.path.isfile(cert_path))
            with open(cert_path, encoding="utf-8") as f:
                cert = json.load(f)
            self.assertTrue(
                cert.get("certified"),
                f"expected certified under --allow-mock; failures={cert.get('failures')}",
            )
            self.assertEqual(cert.get("generative_executor"), "mock")
            covering = os.path.join(run_dir, "covering_proof.json")
            signals_path = os.path.join(run_dir, "spring_signals.json")
            self.assertTrue(os.path.isfile(covering), "local_runner missing covering_proof.json")
            with open(signals_path, encoding="utf-8") as f:
                signals = json.load(f)
            with open(covering, encoding="utf-8") as f:
                proof = json.load(f)
            self.assertNotIn("_covering_proof", signals)
            ok, why = verify_covering_proof(
                proof,
                file_signatures=signals["file_signatures"],
                scanner_version=signals["scanner_version"],
            )
            self.assertTrue(ok, why)


class Ch10StalenessTest(unittest.TestCase):
    """Drift as a staleness detector, on a copy so mutation cannot perturb the
    artifacts every other class reads (and so test order stays irrelevant)."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.mkdtemp(prefix="ks_drift_")
        cls.repo = os.path.join(cls.scratch, "repo")
        shutil.copytree(_STATE["repo"], cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def _drift(self):
        out = os.path.join(self.scratch, "drift.json")
        proc = _run([PY, "-m", "doc_engine.tools.spring_drift_check", self.repo,
                     os.path.join(_STATE["out"], "spring_signals.json"),
                     "--manifest", os.path.join(_STATE["out"], "run_manifest.json"),
                     "--out", out])
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        with open(out, encoding="utf-8") as f:
            return json.load(f)

    def _statuses(self, report, rel):
        return {r["status"] for r in report["results"] if r.get("file") == rel}

    def _mutate(self, rel, old, new):
        path = os.path.join(self.repo, rel.replace("/", os.sep))
        text = open(path, encoding="utf-8").read()
        self.addCleanup(lambda: open(path, "w", encoding="utf-8", newline="\n").write(text))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text.replace(old, new) if old else text + new)

    def test_renamed_table_drifts_its_citation(self):
        self._mutate(TWO_ENTITIES, 'name = "alpha_tbl"', 'name = "alpha_renamed"')
        self.assertIn("drifted", self._statuses(self._drift(), TWO_ENTITIES))

    def test_deleted_file_marks_its_citations_deleted(self):
        path = os.path.join(self.repo, DUP_LEDGER.replace("/", os.sep))
        text = open(path, encoding="utf-8").read()
        os.remove(path)
        self.addCleanup(lambda: open(path, "w", encoding="utf-8", newline="\n").write(text))
        self.assertIn("file_deleted", self._statuses(self._drift(), DUP_LEDGER))

    def test_config_value_only_change_is_flagged_for_review(self):
        """The enterprise case this outcome exists for: checked-in config is a
        placeholder and real values arrive at deploy time, so a value moving
        under an unchanged key means something unusual happened."""
        self._mutate(SECRETS_YML, "hunter2literalvalue", "differentliteralvalue")
        self.assertIn("config_values_only_changed_review_needed",
                      self._statuses(self._drift(), SECRETS_YML))

    def test_added_config_key_is_structural_drift(self):
        self._mutate(SECRETS_YML, None, "extra:\n  added: 1\n")
        self.assertIn("config_structure_changed",
                      self._statuses(self._drift(), SECRETS_YML))


# ---------------------------------------------------------------------------
# Ch. 12 — the end-to-end argument
# ---------------------------------------------------------------------------

class Ch12GateResponsibilityTest(unittest.TestCase):
    """Which layer is responsible for catching which defect — including the
    defects no layer catches.

    The zeros in this class are as load-bearing as the ones: a gate's scope is
    only meaningful if what falls outside it is also written down.
    """

    def _gate(self, docs, *extra):
        """Copied-docs form — see Ch01._gate for why the write check is off
        here. test_stray_write_* below drives the real in-repo path with the
        write check on."""
        return _run([PY, "-m", "doc_engine.tools.check_pipeline_output", docs,
                     "--target-repo", _STATE["repo"], "--no-write-check", *extra])

    def _coverage(self, docs, *extra):
        return _run([PY, "-m", "doc_engine.tools.citation_coverage", docs,
                     "--target-repo", _STATE["repo"], *extra])

    def _secrets(self, *paths):
        return _run([PY, "-m", "doc_engine.tools.check_no_secrets_leaked", *paths])

    def test_three_citation_defects_all_fail_the_gate(self):
        """Collapsed into one mutated copy and one subprocess — three distinct
        issue classes, one process."""
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        path = os.path.join(docs, "database.md")
        text = open(path, encoding="utf-8").read()
        text = text.replace("[Evidenced —", "[Evidenced -", 1)          # malformed
        text = re.sub(r"(\[Evidenced — [^\];]+?):(\d+)\]",
                      lambda m: f"{m.group(1)}:999999]", text, count=1)  # past EOF
        text += "\n- Fabricated [Evidenced — no/such/File.java:1].\n"    # nonexistent
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        proc = self._gate(docs)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("malformed evidence tag", proc.stderr)
        self.assertIn("points past the end", proc.stderr)
        self.assertIn("does not exist under", proc.stderr)

    def test_extra_file_in_docs_fails_the_gate(self):
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        with open(os.path.join(docs, "notes.md"), "w", encoding="utf-8") as f:
            f.write("stray\n")
        proc = self._gate(docs)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unexpected file in docs dir", proc.stderr)

    def test_duplicate_output_path_shows_up_as_a_missing_name(self):
        """Two writers handed the same output_path produce fourteen writes
        with one name duplicated and another missing — which a count check
        passes and the name-set check does not."""
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        shutil.copyfile(os.path.join(docs, "readme.md"), os.path.join(docs, "glossary.md"))
        os.remove(os.path.join(docs, "testing.md"))
        proc = self._gate(docs)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing expected doc: testing.md", proc.stderr)

    def test_stray_write_is_caught_and_no_write_check_removes_the_control(self):
        """The real in-repo path, with the write check genuinely on: it reads
        `git status --porcelain` in the target repo, so this exercises the
        actual mechanism rather than a stand-in."""
        stray = os.path.join(_STATE["repo"], "stray-written-by-a-subagent.txt")
        with open(stray, "w", encoding="utf-8") as f:
            f.write("a writer went outside docs/\n")
        self.addCleanup(lambda: os.path.exists(stray) and os.remove(stray))
        strict = _run([PY, "-m", "doc_engine.tools.check_pipeline_output", _STATE["docs"],
                       "--target-repo", _STATE["repo"]])
        self.assertEqual(strict.returncode, 1)
        self.assertIn("unexpected write outside the docs directory", strict.stderr)
        self.assertEqual(self._gate(_STATE["docs"]).returncode, 0,
                         "--no-write-check should remove exactly this control")

    def test_a_stray_write_into_a_gitignored_path_fails_the_gate(self):
        """Ignored untracked paths are checked via git ls-files -o -i."""
        ignored_dir = os.path.join(_STATE["repo"], GITIGNORED_DIR)
        os.makedirs(ignored_dir, exist_ok=True)
        stray = os.path.join(ignored_dir, "oops.md")
        with open(stray, "w", encoding="utf-8") as f:
            f.write("written outside docs/, into a gitignored directory\n")
        self.addCleanup(lambda: os.path.exists(stray) and os.remove(stray))
        proc = _run([PY, "-m", "doc_engine.tools.check_pipeline_output", _STATE["docs"],
                     "--target-repo", _STATE["repo"]])
        self.assertEqual(proc.returncode, 1,
                         "gate must report a write into a gitignored path")
        self.assertIn("gitignored path", proc.stderr)

    def test_citation_coverage_is_a_worklist_by_default_and_a_gate_under_strict(self):
        """Three finding kinds, one strict run: a miscased tag the Stage-4 gate
        cannot see, an untagged claim, and a re-anchored citation."""
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        _miscase_first_tag(self, os.path.join(docs, "database.md"))
        with open(os.path.join(docs, "operations.md"), "a", encoding="utf-8") as f:
            f.write("\nBillingController.save() writes to billing_invoice on every request.\n")
        self.assertEqual(self._coverage(docs).returncode, 0, "must be a worklist by default")
        strict = self._coverage(docs, "--strict")
        self.assertEqual(strict.returncode, 1)
        self.assertIn("miscased_tag", strict.stdout)
        self.assertIn("untagged_claim", strict.stdout)

    def test_planted_credentials_fail_the_secrets_check(self):
        scratch, docs = _copy_docs()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        with open(os.path.join(docs, "configuration.md"), "a", encoding="utf-8") as f:
            f.write("\nLeaked: AKIAABCDEFGHIJKLMNOP\n-----BEGIN RSA PRIVATE KEY-----\n")
        proc = self._secrets(docs)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("aws_access_key_id", proc.stderr)
        self.assertIn("pem_private_key", proc.stderr)

    def test_placeholder_values_must_not_fire(self):
        """Negative control. Flagging ${VAR}/CHANGEME would make the checker
        noise, and doc-taxonomy.md wants those written up as 'supplied at
        deploy time'."""
        scratch = tempfile.mkdtemp(prefix="ks_ph_")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        path = os.path.join(scratch, "configuration.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("password: ${DB_PASSWORD}\napi-key: CHANGEME\nsecret: <set-me>\n")
        self.assertEqual(self._secrets(path).returncode, 0)

    def test_a_secret_in_prose_is_caught_by_no_layer_at_all(self):
        """The one defect class nothing in this pipeline reports. A stated
        scope limit, not an unintended defect: the key-name heuristic needs the
        secret-shaped key to be the line's own key, so a value moved into
        narrative prose is invisible, and only AKIA/PEM are context-free.
        Pinned so that a change to the boundary is visible in the diff — if
        this starts failing, _secret_heuristics.py's docstring needs updating
        with it."""
        scratch = tempfile.mkdtemp(prefix="ks_prose_")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        path = os.path.join(scratch, "summaries.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([{"summary": "The datasource password is hunter2literalvalue"}], f)
        self.assertEqual(self._secrets(path).returncode, 0)


# ---------------------------------------------------------------------------
# Opt-in lane: the portable invariants, against a real repository
# ---------------------------------------------------------------------------

def _kitchen_sink_real_repo() -> str | None:
    from doc_engine.real_fixture import real_repo_path

    path = real_repo_path()
    return str(path) if path is not None else None


@unittest.skipUnless(
    _kitchen_sink_real_repo(),
    "DOC_ENGINE_REAL_REPO / local-runs/real-repo.path not set — opt-in real-repo lane skipped",
)
class RealEnterpriseRepoTest(unittest.TestCase):
    """Only assertions that hold for *any* Spring repo.

    Content-specific expectations (planted secrets, known entity names, exact
    counts) stay in the synthetic classes, since an arbitrary repo cannot
    satisfy them. Same opt-in shape as tests/doc_engine/test_partition_repo_real_world.py, so
    CI stays hermetic. Deliberately outside the CI runtime budget.
    """

    @classmethod
    def setUpClass(cls):
        repo = os.path.abspath(_kitchen_sink_real_repo() or "")
        if not os.path.isdir(repo):
            raise unittest.SkipTest(f"real repo {repo!r} is not a directory")
        cls.repo = repo
        cls.scratch = tempfile.mkdtemp(prefix="ks_real_")
        cls.out = os.path.join(cls.scratch, "run")
        cls.proc = _run([PY, "-m", "doc_engine.pipeline.local_runner", repo,
                         "--out-dir", cls.out, "--skip-drift"])
        with open(os.path.join(cls.out, "spring_signals.json"), encoding="utf-8") as f:
            cls.signals = json.load(f)
        with open(os.path.join(cls.out, "groups.json"), encoding="utf-8") as f:
            cls.groups = json.load(f)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def test_chain_completes_and_gates_pass(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stdout[-4000:])

    def test_evidence_buckets_are_sorted(self):
        for bucket, rows in (self.signals.get("evidence") or {}).items():
            with self.subTest(bucket=bucket):
                self.assertEqual(rows, sorted(rows, key=lambda e: (e["file"], e.get("line", 0))))

    def test_entity_index_keys_are_sorted(self):
        keys = list(self.signals["entity_table_map"])
        self.assertEqual(keys, sorted(keys))

    def test_no_excluded_directory_leaked(self):
        pool = _grouped(self.groups) | set(_evidence_files(self.signals))
        for d in DEFAULT_EXCLUDED_DIRS:
            with self.subTest(excluded=d):
                self.assertEqual([f for f in pool if _has_segment(f, d)], [])

    def test_overlap_is_adjacent_only(self):
        """Overlap must stay between adjacent groups on the opt-in mid-size lane.

        Regression for CONSTRAINTS.md §6: carry_forward skips paths that
        entered a group only via prior overlap (carried_in_paths). Requires
        KITCHEN_SINK_REPO (class skips otherwise).
        """
        where = {}
        for g in self.groups["groups"]:
            for f in g["files"]:
                where.setdefault(f, set()).add(g["id"])
        for f, ids in where.items():
            if len(ids) > 1:
                with self.subTest(file=f):
                    self.assertEqual(ids, {min(ids), min(ids) + 1})

    def test_contested_entity_keys_are_well_formed(self):
        """Every contested entity_table_map entry must carry candidates and
        refuse JPQL lineage rather than guessing a table. Vacuous-pass when
        the target repo has no simple-name collisions (observed on the
        in-tree mid-size service checkout: 0 contested / 53 entities)."""
        contested = {
            name: entry for name, entry in self.signals["entity_table_map"].items()
            if entry.get("status") == "contested"
        }
        for name, entry in contested.items():
            with self.subTest(entity=name):
                self.assertGreaterEqual(len(entry.get("candidates") or []), 2)
                tables = {c["table"] for c in entry["candidates"]}
                files = {c["file"] for c in entry["candidates"]}
                self.assertEqual(len(files), len(entry["candidates"]))
                lineage = spring_signal_scan.resolve_jpql_to_lineage(
                    f"SELECT x FROM {name} x", self.signals["entity_table_map"]
                )
                self.assertFalse(lineage["available"])
                self.assertIn("contested", lineage["reason"])
                # Citation-identity table must be one of the candidates, not
                # an invented third name.
                self.assertIn(entry["table"], tables)

    def test_multi_hyphen_application_profiles_reach_config_key_sets(self):
        """Every application*-*.yml/properties on disk with ≥2 hyphens in the
        filename must appear in config_key_sets (the CONSTRAINTS §7 fix).
        Vacuous when the checkout has none (observed: 0 multi-hyphen stems
        among 12 application* configs on the in-tree mid-size service)."""
        on_disk = []
        for dirpath, _dirnames, filenames in os.walk(self.repo):
            for name in filenames:
                lower = name.lower()
                if not (lower.startswith("application") and (
                        lower.endswith(".yml") or lower.endswith(".yaml")
                        or lower.endswith(".properties"))):
                    continue
                if name.count("-") >= 2:
                    rel = os.path.relpath(os.path.join(dirpath, name), self.repo)
                    on_disk.append(rel.replace("\\", "/"))
        keys = self.signals.get("config_key_sets") or {}
        for rel in on_disk:
            with self.subTest(file=rel):
                self.assertIn(rel, keys)

    def test_fault_injection_holds_on_real_output(self):
        """The most valuable part of the real lane: the gate topology proven
        against real-shaped documentation, not templated mock prose."""
        scratch = tempfile.mkdtemp(prefix="ks_real_docs_")
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        copy = os.path.join(scratch, "docs")
        shutil.copytree(os.path.join(self.out, "docs"), copy)
        os.remove(os.path.join(copy, "testing.md"))
        proc = _run([PY, "-m", "doc_engine.tools.check_pipeline_output", copy,
                     "--target-repo", self.repo, "--no-write-check"])
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
