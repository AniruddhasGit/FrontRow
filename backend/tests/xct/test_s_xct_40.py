"""S-XCT-40 (PRD P-XCT-26, S7.16): no Zone C artefact, nothing created in AWS, a specification instead.

ZONE B COMMENT RULE, AS READ HERE. "Every non-blank, non-comment line ... is preceded by a comment line"
is applied per LOGICAL line: a statement or instruction that continues over several physical lines
(a Dockerfile `\\` continuation, a shell `\\` continuation, a Python bracketed expression) is one unit,
and the physical line directly above its first line must be a comment. [JUDGMENT CALL] - reading it per
physical line would demand a comment inside every multi-line call and every RUN continuation.
"""

from __future__ import annotations

import io
import re
import tokenize

from ._support import DEPLOY, REPO, _files, prep_queue, rg, spec_files

ZONE_B = ("backend/Dockerfile", "frontend/Dockerfile", "backend/entrypoint.sh", "backend/app/core/config.py", "backend/app/api/health.py")
FOUR = ("## What to build", "## What the application expects", "## Acceptance criteria", "## Common mistakes")
MARKER = "(reasoned, not observed)"


def test_no_zone_c_artefact_by_path():
    bad = []
    for p in _files(REPO):
        rel = p.relative_to(REPO).as_posix()
        name = p.name.lower()
        if (
            name.endswith((".tf", ".tfvars", ".tf.json"))
            or rel.startswith(".github/workflows/")
            or re.fullmatch(r"taskdef.*\.json", name)
            or re.fullmatch(r".*cloudformation.*\.ya?ml", name)
        ):
            bad.append(rel)
    assert bad == []


def test_no_reference_implementation():
    assert rg("reference only", "backend/app", "backend/migrations", "frontend/src", "scripts", "docs/30 Deployment", ignore_case=True) == []


def test_every_named_spec_exists_and_carries_the_four_headings():
    rows = prep_queue()
    named = set()
    for r in rows:
        if r["Spec"] == "—":
            continue
        files = spec_files(r["Spec"])
        assert files, f"row {r['#']}: Spec is neither an em dash nor a link: {r['Spec']}"
        named.update(files)
    for f in sorted(named):
        path = DEPLOY / f
        assert path.is_file(), f
        lines = path.read_text(encoding="utf-8").splitlines()
        for h in FOUR:
            assert h in lines, (f, h)
        i = lines.index("## Common mistakes")
        items = []
        for line in lines[i + 1 :]:
            if line.startswith("#"):
                break
            if line.startswith("- "):
                items.append(line)
        assert 2 <= len(items) <= 3, (f, len(items))


def test_no_terraform_cloudformation_or_task_definition_block():
    assert rg(r'resource "aws_|AWSTemplateFormatVersion|"containerDefinitions"', "docs/30 Deployment") == []


def test_every_queue_row_is_needed_by_a_phase():
    assert all(re.match(r"^Phase [1-8]", r["Needed by"]) for r in prep_queue())


def test_no_mutating_aws_command_in_the_deployment_tree_or_scripts():
    hits = rg(r"aws (ec2|ecs|elbv2|iam|s3api|sqs|ses|ssm|logs|cloudwatch) [a-z-]+", "docs/30 Deployment", "scripts")
    verbs = [re.search(r"aws (?:ec2|ecs|elbv2|iam|s3api|sqs|ses|ssm|logs|cloudwatch) ([a-z-]+)", h[2]).group(1) for h in hits]
    assert [v for v in verbs if not re.match(r"^(describe|list|get)", v)] == []


def test_the_aws_behaviour_marker_is_on_every_in_aws_paragraph():
    assert rg(MARKER, "docs/30 Deployment", fixed=True)
    bad = []
    for f in sorted(DEPLOY.glob("*.md")):
        for para in re.split(r"\n\s*\n", f.read_text(encoding="utf-8")):
            if "in AWS" in para and MARKER not in para:
                bad.append((f.name, para[:120]))
    assert bad == []


# ------------------------------------------------------------------- the Zone B comment walk


def _python_units(text: str) -> list[int]:
    """First physical line number of every logical line (statement) in a Python file."""
    starts, at_start = [], True
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        if tok.type == tokenize.NEWLINE:
            at_start = True
            continue
        if at_start:
            starts.append(tok.start[0])
            at_start = False
    return starts


def _continued_units(text: str) -> list[int]:
    """First line of every instruction in a Dockerfile or shell script, folding `\\` continuations
    (comment lines inside a Dockerfile continuation are part of it, as Docker treats them)."""
    starts, continuing = [], False
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continuing = False if not continuing else continuing
            continue
        if line.startswith("#"):
            continue
        if not continuing:
            starts.append(n)
        continuing = line.endswith("\\")
    return starts


def test_every_zone_b_line_is_preceded_by_a_comment_line():
    bad = []
    for rel in ZONE_B:
        text = (REPO / rel).read_text(encoding="utf-8")
        lines = text.splitlines()
        units = _python_units(text) if rel.endswith(".py") else _continued_units(text)
        for n in units:
            above = lines[n - 2].strip() if n >= 2 else ""
            if not above.startswith("#"):
                bad.append(f"{rel}:{n}: {lines[n - 1].strip()[:80]}")
    assert bad == [], "\n".join(bad)
