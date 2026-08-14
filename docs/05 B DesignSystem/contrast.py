#!/usr/bin/env python3
"""
contrast.py — the computation behind CONTRAST.md.

FrontRow design system. This script is the ONLY thing in this repository that is
allowed to produce a contrast figure. CONSTITUTION.md Art VII.1 forbids a number
nobody ran, so no contrast ratio, no L* value and no delta is ever typed by a
human into any document under docs/05 B DesignSystem/.

What it does
------------
1. Parses `tokens.css` — the source of record — into four declaration blocks
   marked by `/* @block <name> */` comments.
2. Reads the machine-readable annotation on each token's trailing comment and
   builds the foreground/background pair list FROM THAT, never from a list held
   here. A hand-maintained list measures only what someone remembered to add.
3. Resolves one level of `var(--fr-x)` aliasing per theme.
4. Runs thirteen checks (see CHECKS below) across BOTH themes.
5. Writes `CONTRAST.md` with a GENERATED banner and the SHA-256 of the tokens
   file it was produced from.

Vacuous truth is not a pass
---------------------------
Every check carries a SUBJECT COUNT: how many things it actually looked at. A
check that looked at zero things reports SKIP, never PASS, and a SKIP does not
earn exit 0. This file used to report eleven PASSes against an absent tokens.css
— GOTCHAS.md names that exact trap: *a check that cannot fail looks exactly like
a clean result.* The subject count is printed next to every check so a reader can
see the check ran rather than take its word for it.

Usage
-----
    python contrast.py             regenerate CONTRAST.md; exit 1 if any check fails
    python contrast.py --check     verify only; write nothing; also fail if
                                   CONTRAST.md on disk is stale
    python contrast.py --selftest  plant a real violation of EVERY check in a
                                   throwaway copy and require each one to fire
    python contrast.py --quiet     suppress the per-failure detail lines

Exit codes: 0 every check passed. 1 at least one check failed or skipped.
            2 the tool itself could not run.

stdout is deliberately ASCII-only: this project is developed on Windows and a
check that crashes on a console codepage is a check that does not run.

Standard library only. No network, no credentials, no shelling out.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import tempfile
import traceback
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Floors. Each is a WCAG 2.2 success criterion, named so a reader can check it.
# ---------------------------------------------------------------------------
FLOOR = {
    "text": (4.5, "1.4.3 Contrast (Minimum), normal text"),
    "text-lg": (3.0, "1.4.3 Contrast (Minimum), large text (>=24px, or >=18.66px bold)"),
    "ui": (3.0, "1.4.11 Non-text Contrast, UI components and graphical objects"),
}
ROLES = set(FLOOR) | {"ground", "decor"}

# Perceptual lightness separation required between two seat states in the same
# greyscale group. Set at 12 CIE L*: roughly 1 in 12 men cannot separate the
# obvious hue palette for this surface, so luminance carries the meaning and the
# hue is only ever the redundant second cue.
GREY_MIN_DELTA_L = 12.0

# A seat fill must be separable from the seat-map field it sits on, either by
# lightness alone or by a declared edge token that passes the 1.4.11 floor.
SEAT_FIELD_MIN_DELTA_L = 8.0
SEAT_FIELD_TOKEN = "--fr-surface-inset"

BLOCK_STRUCTURAL = "structural"
BLOCK_LIGHT = "palette-light"
BLOCK_DARK_AUTO = "palette-dark-auto"
BLOCK_DARK_EXPLICIT = "palette-dark-explicit"
REQUIRED_BLOCKS = (BLOCK_STRUCTURAL, BLOCK_LIGHT, BLOCK_DARK_AUTO, BLOCK_DARK_EXPLICIT)

CHECKS = OrderedDict(
    [
        ("PARSE", ("tokens.css parses and every block marker is present", "declaration")),
        ("ONE-PER-LINE", ("every custom property is declared on its own line", "line")),
        ("ANNOTATED", ("every colour-valued token carries a role annotation", "colour token")),
        ("DECOR-WHY", ("every @decor token states why it is exempt", "exemption")),
        ("ON-RESOLVES", ("every on: target names a real @ground token", "foreground token")),
        ("THEME-PARITY", ("light and dark define exactly the same palette tokens", "palette token")),
        ("DARK-IDENTICAL", ("the two dark blocks are value-for-value identical", "token")),
        ("CONTRAST", ("every derived pair meets its WCAG floor in both themes", "pair")),
        ("GREYSCALE",
         ("seat states separate by >=%.0f L* with no colour" % GREY_MIN_DELTA_L, "step")),
        ("GLYPH", ("every seat state carries a distinct non-colour mark", "state")),
        ("SEAT-FIELD", ("every seat fill separates from the seat-map field", "fill x theme")),
        ("TOKEN-COVERAGE", ("tokens.css and COMPONENTS.md name the same token set", "token")),
        ("GENERATED", ("CONTRAST.md on disk is exactly what tokens.css produces", "file")),
    ]
)

DECL_RE = re.compile(
    r"^\s*(?P<name>--fr-[a-z0-9-]+)\s*:\s*(?P<value>[^;]+);\s*(?:/\*(?P<note>.*?)\*/)?\s*$"
)
ANY_DECL_RE = re.compile(r"--fr-[a-z0-9-]+\s*:")
BLOCK_RE = re.compile(r"/\*\s*@block\s+([a-z-]+)\s*\*/")
HEX_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")
VAR_RE = re.compile(r"^var\(\s*(--fr-[a-z0-9-]+)\s*\)$")
TOKEN_MENTION_RE = re.compile(r"--fr-[a-z0-9-]+")


class Paths:
    """Where the three files live. Parameterised so --selftest can point the whole
    tool at a throwaway copy of this directory instead of the real one."""

    def __init__(self, base: Path) -> None:
        self.base = Path(base)
        self.tokens = self.base / "tokens.css"
        self.out = self.base / "CONTRAST.md"
        self.components = self.base / "COMPONENTS.md"


# ---------------------------------------------------------------------------
# Colour maths. sRGB -> linear -> relative luminance -> WCAG ratio; and
# relative luminance -> CIE L*, which is what the greyscale proof is stated in
# because L* is perceptually uniform and relative luminance is not.
# ---------------------------------------------------------------------------
def parse_hex(value: str) -> tuple[int, int, int]:
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 8:
        h = h[:6]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _to_linear(channel_8bit: int) -> float:
    c = channel_8bit / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(linear: float) -> int:
    linear = min(1.0, max(0.0, linear))
    c = linear * 12.92 if linear <= 0.0031308 else 1.055 * (linear ** (1 / 2.4)) - 0.055
    return int(round(c * 255))


def relative_luminance(hex_value: str) -> float:
    r, g, b = (_to_linear(c) for c in parse_hex(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def lstar(hex_value: str) -> float:
    """CIE L* from relative luminance, D65. 0 = black, 100 = white."""
    y = relative_luminance(hex_value)
    f = y ** (1 / 3) if y > 216 / 24389 else (24389 / 27 * y + 16) / 116
    return 116 * f - 16


def greyscale_hex(hex_value: str) -> str:
    """The neutral of identical relative luminance. This is what the colour
    becomes when hue information is unavailable to the viewer."""
    y = relative_luminance(hex_value)
    c = _from_linear(y)
    return "#%02X%02X%02X" % (c, c, c)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
class Token:
    __slots__ = ("name", "raw", "roles", "on", "grey", "glyph", "edge", "why", "line")

    def __init__(self, name, raw, line):
        self.name = name
        self.raw = raw.strip()
        self.line = line
        self.roles: list[str] = []
        self.on: list[str] = []
        self.grey: str | None = None
        self.glyph: str | None = None
        self.edge: str | None = None
        self.why: str | None = None

    @property
    def short(self) -> str:
        return self.name[len("--fr-"):]


def parse_annotation(tok: Token, note: str | None) -> list[str]:
    """Read the machine-readable trailing comment. Returns parse errors."""
    errs: list[str] = []
    if not note:
        return errs
    why = re.search(r'why:"([^"]*)"', note)
    if why:
        tok.why = why.group(1)
        note = note[: why.start()] + note[why.end():]
    for word in note.split():
        if word.startswith("@"):
            body = word[1:]
            if ":" in body:
                key, val = body.split(":", 1)
                if key == "grey":
                    tok.grey = val
                else:
                    errs.append("%s: unknown annotation @%s" % (tok.name, body))
            elif body in ROLES:
                tok.roles.append(body)
            else:
                errs.append("%s: unknown role @%s" % (tok.name, body))
        elif word.startswith("on:"):
            tok.on.extend(p for p in word[3:].split(",") if p)
        elif word.startswith("glyph:"):
            tok.glyph = word[6:]
        elif word.startswith("edge:"):
            tok.edge = word[5:]
        elif word.startswith("--"):
            pass  # prose reference to another token, ignored
        else:
            pass  # free prose in the comment is allowed
    return errs


def parse_tokens(text: str):
    """Split tokens.css into annotated blocks.

    Returns (blocks, errors, n_decl_lines). `n_decl_lines` is the subject count
    for ONE-PER-LINE: how many lines carried a custom property at all."""
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: dict[str, "OrderedDict[str, Token]"] = OrderedDict()
    errors: list[str] = []
    current: str | None = None
    decl_lines = 0
    for i, line in enumerate(lines, start=1):
        marker = BLOCK_RE.search(line)
        if marker:
            current = marker.group(1)
            blocks.setdefault(current, OrderedDict())
            continue
        if "--fr-" not in line:
            continue
        hits = ANY_DECL_RE.findall(line)
        if not hits:
            continue
        decl_lines += 1
        if len(hits) > 1:
            errors.append("ONE-PER-LINE: line %d declares %d properties" % (i, len(hits)))
            continue
        m = DECL_RE.match(line)
        if not m:
            errors.append("PARSE: line %d is not a parseable declaration: %s" % (i, line.strip()))
            continue
        if current is None:
            errors.append("PARSE: line %d declares %s before any @block marker"
                          % (i, m.group("name")))
            continue
        tok = Token(m.group("name"), m.group("value"), i)
        errors.extend(parse_annotation(tok, m.group("note")))
        if tok.name in blocks[current]:
            errors.append("PARSE: %s declared twice in @block %s" % (tok.name, current))
        blocks[current][tok.name] = tok
    return blocks, errors, decl_lines


def resolve(theme: "OrderedDict[str, Token]") -> tuple[dict[str, str], list[str]]:
    """Resolve var() aliases within a theme. One level is enough for this system;
    the loop guards against a chain anyway."""
    out: dict[str, str] = {}
    errs: list[str] = []
    for name, tok in theme.items():
        value, seen = tok.raw, set()
        while True:
            m = VAR_RE.match(value)
            if not m:
                break
            target = m.group(1)
            if target in seen or target not in theme:
                errs.append("PARSE: %s aliases %s which does not resolve" % (name, target))
                break
            seen.add(target)
            value = theme[target].raw
        out[name] = value
    return out, errs


def is_colour(value: str) -> bool:
    return bool(HEX_RE.match(value.strip()))


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
class Result:
    """One run. Each check owns its failures AND its subject count.

    `subjects[key] == 0` means the check had nothing to look at. That is a SKIP,
    never a PASS: a check over an empty set has not been run, and reporting it
    green is how a tool lies. `ok` requires every check to be PASS, so a SKIP
    holds the exit code at 1 exactly like a failure would.
    """

    def __init__(self) -> None:
        self.failures: "OrderedDict[str, list[str]]" = OrderedDict((k, []) for k in CHECKS)
        self.subjects: "OrderedDict[str, int]" = OrderedDict((k, 0) for k in CHECKS)
        self.pairs: list[dict] = []
        self.grey: "OrderedDict[str, list[dict]]" = OrderedDict()
        self.decor: list[tuple[str, str, str]] = []
        self.counts: dict[str, int] = {}
        self.seat_field: list[dict] = []

    def fail(self, check: str, message: str) -> None:
        self.failures[check].append(message)

    def saw(self, check: str, n: int) -> None:
        self.subjects[check] += n

    def status(self, check: str) -> str:
        if self.failures[check]:
            return "FAIL"
        if self.subjects[check] <= 0:
            return "SKIP"
        return "PASS"

    @property
    def ok(self) -> bool:
        return all(self.status(k) == "PASS" for k in CHECKS)

    @property
    def n_fail(self) -> int:
        return sum(1 for k in CHECKS if self.status(k) == "FAIL")

    @property
    def n_skip(self) -> int:
        return sum(1 for k in CHECKS if self.status(k) == "SKIP")

    @property
    def n_pass(self) -> int:
        return sum(1 for k in CHECKS if self.status(k) == "PASS")


def run(paths: Paths) -> Result:
    res = Result()
    res.counts["tokens_sha256"] = "-"
    # GENERATED's subject is the output file itself, and it always exists as a
    # subject: in --check the on-disk copy is compared, and in write mode it is
    # rewritten. Counted HERE rather than after render() so the rendered document
    # reports the same verdict the terminal does — the first version of this fix
    # counted it afterwards and CONTRAST.md announced FAILED on a clean run.
    res.saw("GENERATED", 1)
    if not paths.tokens.exists():
        # Not a SKIP. tokens.css is the source of record; its absence is the
        # whole system missing, and the tool must say FAIL out loud.
        res.saw("PARSE", 1)
        res.fail("PARSE", "tokens.css not found at %s" % paths.tokens)
        return res

    text = paths.tokens.read_text(encoding="utf-8")
    res.counts["tokens_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    blocks, parse_errors, decl_lines = parse_tokens(text)
    res.saw("ONE-PER-LINE", decl_lines)
    res.saw("PARSE", decl_lines + len(REQUIRED_BLOCKS))
    for e in parse_errors:
        head = e.split(":", 1)[0]
        res.fail(head if head in CHECKS else "PARSE", e)

    for required in REQUIRED_BLOCKS:
        if required not in blocks:
            res.fail("PARSE", "missing /* @block %s */" % required)
    if res.failures["PARSE"]:
        # Everything downstream has no subjects and will report SKIP. That is
        # the honest answer: those checks did not run.
        return res

    structural = blocks[BLOCK_STRUCTURAL]
    light_pal = blocks[BLOCK_LIGHT]
    dark_auto = blocks[BLOCK_DARK_AUTO]
    dark_exp = blocks[BLOCK_DARK_EXPLICIT]

    # -- THEME-PARITY -------------------------------------------------------
    parity_subjects = set(light_pal) | set(dark_exp)
    res.saw("THEME-PARITY", len(parity_subjects))
    for n in [n for n in light_pal if n not in dark_exp]:
        res.fail("THEME-PARITY", "%s defined in light only" % n)
    for n in [n for n in dark_exp if n not in light_pal]:
        res.fail("THEME-PARITY", "%s defined in dark only" % n)

    # -- DARK-IDENTICAL -----------------------------------------------------
    res.saw("DARK-IDENTICAL", len(set(dark_auto) | set(dark_exp)))
    if set(dark_auto) != set(dark_exp):
        res.fail(
            "DARK-IDENTICAL",
            "the prefers-color-scheme block and the [data-theme=dark] block "
            "declare different token sets (%d vs %d)" % (len(dark_auto), len(dark_exp)),
        )
    for n in dark_auto:
        if n in dark_exp and dark_auto[n].raw != dark_exp[n].raw:
            res.fail(
                "DARK-IDENTICAL",
                "%s is %s under prefers-color-scheme but %s under [data-theme=dark]"
                % (n, dark_auto[n].raw, dark_exp[n].raw),
            )

    # Annotations are authored once, on the light block, and reused by name.
    annotations: "OrderedDict[str, Token]" = OrderedDict(
        list(structural.items()) + list(light_pal.items())
    )
    raw_values = {
        "light": OrderedDict(list(structural.items()) + list(light_pal.items())),
        "dark": OrderedDict(list(structural.items()) + list(dark_exp.items())),
    }

    resolved: dict[str, dict[str, str]] = {}
    for theme, table in raw_values.items():
        vals, errs = resolve(table)
        resolved[theme] = vals
        for e in errs:
            res.fail("PARSE", "[%s] %s" % (theme, e))
    if res.failures["PARSE"]:
        return res

    # -- ANNOTATED / DECOR-WHY ---------------------------------------------
    colour_tokens: list[str] = []
    for name, tok in annotations.items():
        light_val = resolved["light"].get(name, "")
        dark_val = resolved["dark"].get(name, light_val)
        if not (is_colour(light_val) or is_colour(dark_val)):
            if tok.roles:
                res.saw("ANNOTATED", 1)
                res.fail("ANNOTATED", "%s is annotated %s but is not a colour" % (name, tok.roles))
            continue
        colour_tokens.append(name)
        res.saw("ANNOTATED", 1)
        if not tok.roles:
            res.fail(
                "ANNOTATED",
                "%s (line %d) is a colour with no role. Add @ground / @text / "
                "@text-lg / @ui, or @decor with a why:\"...\"." % (name, tok.line),
            )
        if "decor" in tok.roles:
            res.saw("DECOR-WHY", 1)
            if not tok.why:
                res.fail("DECOR-WHY", '%s is @decor but states no why:"..."' % name)
            res.decor.append((name, tok.why or "", ", ".join(tok.roles)))

    grounds = {n for n in colour_tokens if "ground" in annotations[n].roles}

    # -- ON-RESOLVES + CONTRAST --------------------------------------------
    for name in colour_tokens:
        tok = annotations[name]
        fg_roles = [r for r in tok.roles if r in FLOOR]
        if not fg_roles:
            if tok.on:
                res.saw("ON-RESOLVES", 1)
                res.fail("ON-RESOLVES", "%s lists on: but has no foreground role" % name)
            continue
        res.saw("ON-RESOLVES", 1)
        if not tok.on:
            res.fail("ON-RESOLVES",
                     "%s has role %s but names no on: background" % (name, fg_roles))
            continue
        floor = min(FLOOR[r][0] for r in fg_roles)
        criterion = FLOOR[sorted(fg_roles, key=lambda r: FLOOR[r][0])[0]][1]
        for short in tok.on:
            bg = "--fr-" + short
            if bg not in grounds:
                res.fail(
                    "ON-RESOLVES",
                    "%s declares on:%s but --fr-%s is not a token annotated @ground"
                    % (name, short, short),
                )
                continue
            for theme in ("light", "dark"):
                fgv, bgv = resolved[theme][name], resolved[theme][bg]
                if not (is_colour(fgv) and is_colour(bgv)):
                    continue
                ratio = contrast_ratio(fgv, bgv)
                passed = ratio + 1e-9 >= floor
                res.saw("CONTRAST", 1)
                res.pairs.append(
                    {
                        "theme": theme,
                        "fg": name,
                        "bg": bg,
                        "fg_hex": fgv.upper(),
                        "bg_hex": bgv.upper(),
                        "ratio": ratio,
                        "floor": floor,
                        "role": "/".join(fg_roles),
                        "criterion": criterion,
                        "pass": passed,
                    }
                )
                if not passed:
                    res.fail(
                        "CONTRAST",
                        "[%s] %s on %s = %.2f:1, floor %.1f:1 (%s)"
                        % (theme, name, bg, ratio, floor, criterion),
                    )

    # -- GREYSCALE + GLYPH --------------------------------------------------
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for name in colour_tokens:
        g = annotations[name].grey
        if g:
            groups.setdefault(g, []).append(name)

    for group, members in groups.items():
        glyphs: dict[str, str] = {}
        for name in members:
            res.saw("GLYPH", 1)
            glyph = annotations[name].glyph
            if not glyph:
                res.fail("GLYPH",
                         "%s is in greyscale group '%s' but declares no glyph:" % (name, group))
            elif glyph in glyphs:
                res.fail(
                    "GLYPH",
                    "%s and %s both use glyph:%s - colour would be the only difference"
                    % (glyphs[glyph], name, glyph),
                )
            else:
                glyphs[glyph] = name
        for theme in ("light", "dark"):
            rows = []
            for name in members:
                v = resolved[theme][name]
                rows.append(
                    {
                        "token": name,
                        "hex": v.upper(),
                        "grey": greyscale_hex(v),
                        "lstar": lstar(v),
                        "glyph": annotations[name].glyph or "-",
                    }
                )
            rows.sort(key=lambda r: r["lstar"])
            for i, row in enumerate(rows):
                row["delta"] = None if i == 0 else row["lstar"] - rows[i - 1]["lstar"]
                if row["delta"] is None:
                    continue
                res.saw("GREYSCALE", 1)
                if row["delta"] + 1e-9 < GREY_MIN_DELTA_L:
                    res.fail(
                        "GREYSCALE",
                        "[%s] group '%s': %s and %s are %.1f L* apart, floor %.1f - "
                        "indistinguishable without colour"
                        % (theme, group, rows[i - 1]["token"], row["token"],
                           row["delta"], GREY_MIN_DELTA_L),
                    )
            res.grey["%s/%s" % (group, theme)] = rows

    # -- SEAT-FIELD ---------------------------------------------------------
    for group, members in groups.items():
        for theme in ("light", "dark"):
            field = resolved[theme].get(SEAT_FIELD_TOKEN)
            if not field or not is_colour(field):
                continue
            for name in members:
                res.saw("SEAT-FIELD", 1)
                v = resolved[theme][name]
                delta = abs(lstar(v) - lstar(field))
                edge_short = annotations[name].edge
                edge_ok = None
                if edge_short:
                    edge = "--fr-" + edge_short
                    if edge not in resolved[theme]:
                        res.fail("SEAT-FIELD",
                                 "%s declares edge:%s which does not exist" % (name, edge_short))
                        continue
                    edge_ok = contrast_ratio(resolved[theme][edge], field)
                ok = delta + 1e-9 >= SEAT_FIELD_MIN_DELTA_L or (edge_ok is not None
                                                               and edge_ok >= 3.0)
                res.seat_field.append(
                    {
                        "theme": theme,
                        "token": name,
                        "delta": delta,
                        "edge": edge_short,
                        "edge_ratio": edge_ok,
                        "pass": ok,
                    }
                )
                if not ok:
                    res.fail(
                        "SEAT-FIELD",
                        "[%s] %s is %.1f L* from the seat-map field (floor %.1f) and has no "
                        "edge token clearing 3.0:1" % (theme, name, delta, SEAT_FIELD_MIN_DELTA_L),
                    )

    # -- TOKEN-COVERAGE -----------------------------------------------------
    declared = set(structural) | set(light_pal) | set(dark_exp)
    if paths.components.exists():
        named = set(TOKEN_MENTION_RE.findall(paths.components.read_text(encoding="utf-8")))
    else:
        named = set()
        res.saw("TOKEN-COVERAGE", 1)
        res.fail("TOKEN-COVERAGE", "COMPONENTS.md not found at %s" % paths.components)
    res.saw("TOKEN-COVERAGE", len(declared | named))
    unused = sorted(declared - named)
    unknown = sorted(named - declared)
    res.counts["declared"] = len(declared)
    res.counts["named_in_components"] = len(named)
    res.counts["unused"] = len(unused)
    res.counts["unknown"] = len(unknown)
    res.counts["colour_tokens"] = len(colour_tokens)
    for n in unused:
        res.fail("TOKEN-COVERAGE",
                 "%s is declared in tokens.css but no component spec uses it" % n)
    for n in unknown:
        res.fail("TOKEN-COVERAGE",
                 "COMPONENTS.md names %s which does not exist in tokens.css" % n)

    res.counts["pairs"] = len(res.pairs)
    res.counts["pairs_light"] = sum(1 for p in res.pairs if p["theme"] == "light")
    res.counts["pairs_dark"] = sum(1 for p in res.pairs if p["theme"] == "dark")
    res.counts["min_ratio"] = min((p["ratio"] for p in res.pairs), default=0.0)
    res.counts["grey_pairs"] = res.subjects["GREYSCALE"]
    res.counts["min_delta_l"] = min(
        (r["delta"] for rows in res.grey.values() for r in rows if r["delta"] is not None),
        default=0.0,
    )
    return res


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def bar(lstar_value: float, width: int = 40) -> str:
    n = int(round(lstar_value / 100 * width))
    n = max(0, min(width, n))
    return "█" * n + "·" * (width - n)


def render(res: Result) -> str:
    c = res.counts
    L: list[str] = []
    A = L.append
    A("<!-- ------------------------------------------------------------------")
    A("     GENERATED FILE - DO NOT EDIT BY HAND")
    A("     Produced by: docs/05 B DesignSystem/contrast.py")
    A("     Regenerate:  py \"docs/05 B DesignSystem/contrast.py\"")
    A("     Verify:      py \"docs/05 B DesignSystem/contrast.py\" --check")
    A("     Red-proof:   py \"docs/05 B DesignSystem/contrast.py\" --selftest")
    A("     Any edit made here is destroyed on the next run.")
    A("     ------------------------------------------------------------------ -->")
    A("")
    A("# CONTRAST.md - computed, not claimed")
    A("")
    A("> **GENERATED.** Every number on this page was computed by `contrast.py` from")
    A("> `tokens.css`. No figure here was typed by a human, and no figure here may be")
    A("> quoted into another document by hand - cite this file or re-run the script.")
    A("> `CONSTITUTION.md` Art VII.1.")
    A("")
    A("| | |")
    A("|---|---|")
    A("| Source of record | `tokens.css` |")
    A("| `tokens.css` SHA-256 | `%s` |" % c.get("tokens_sha256", "-"))
    A("| Colour tokens | %d |" % c.get("colour_tokens", 0))
    A("| Foreground/background pairs checked | **%d** (%d light, %d dark) |"
      % (c.get("pairs", 0), c.get("pairs_light", 0), c.get("pairs_dark", 0)))
    A("| Lowest ratio measured | **%.2f:1** |" % c.get("min_ratio", 0.0))
    A("| Greyscale steps checked | %d |" % c.get("grey_pairs", 0))
    A("| Smallest lightness step measured | **%.1f L\\*** (floor %.1f) |"
      % (c.get("min_delta_l", 0.0), GREY_MIN_DELTA_L))
    A("| Checks | %d pass, %d fail, %d skip, of %d |"
      % (res.n_pass, res.n_fail, res.n_skip, len(CHECKS)))
    A("| Result | **%s** |" % ("ALL CHECKS PASS" if res.ok else "FAILED"))
    A("")
    A("## How the pair list is built")
    A("")
    A("The pairs below are **derived from `tokens.css`**, not from a list kept inside the")
    A("script. Each colour token carries a machine-readable annotation in its trailing")
    A("comment: a role (`@text`, `@text-lg`, `@ui`, `@ground`, `@decor`) and, for a")
    A("foreground, the `on:` backgrounds it is allowed to sit on. The script takes the")
    A("cross product. Adding a token without an annotation fails the `ANNOTATED` check,")
    A("so a new colour cannot enter the system unmeasured.")
    A("")
    A("| Role | Floor | WCAG 2.2 criterion |")
    A("|---|---|---|")
    for role in ("text", "text-lg", "ui"):
        A("| `@%s` | %.1f:1 | %s |" % (role, FLOOR[role][0], FLOOR[role][1]))
    A("")

    A("## Checks")
    A("")
    A("`subjects` is how many things the check actually looked at. A check with zero")
    A("subjects reports **SKIP**, never PASS - a check over an empty set has not run,")
    A("and reporting it green is the failure mode `GOTCHAS.md` warns about. A SKIP holds")
    A("the exit code at 1 exactly as a FAIL does.")
    A("")
    A("| Check | What it proves | Subjects | Result |")
    A("|---|---|---|---|")
    for key, (desc, unit) in CHECKS.items():
        st = res.status(key)
        n = res.subjects[key]
        shown = "**FAIL (%d)**" % len(res.failures[key]) if st == "FAIL" else st
        A("| `%s` | %s | %d %s%s | %s |"
          % (key, desc, n, unit, "" if n == 1 else "s", shown))
    A("")
    if not res.ok:
        A("### Failures")
        A("")
        for key, fails in res.failures.items():
            for f in fails:
                A("- `%s` %s" % (key, f))
        for key in CHECKS:
            if res.status(key) == "SKIP":
                A("- `%s` SKIPPED - zero subjects. This check did not run." % key)
        A("")

    A("## Token coverage")
    A("")
    A("Both directions, because one direction alone is not a check: a token nobody uses")
    A("is dead weight, and a component naming a token that does not exist is a build")
    A("failure waiting for the first person who tries it.")
    A("")
    A("| Direction | Count |")
    A("|---|---|")
    A("| Tokens declared in `tokens.css` | %d |" % c.get("declared", 0))
    A("| Distinct tokens named in `COMPONENTS.md` | %d |" % c.get("named_in_components", 0))
    A("| Declared but used by no component spec | **%d** |" % c.get("unused", 0))
    A("| Named by a component spec but not declared | **%d** |" % c.get("unknown", 0))
    A("")

    A("## Greyscale separability of the seat states")
    A("")
    A("Roughly one man in twelve cannot separate the hue palette a seat map normally")
    A("reaches for. So on this seat map **hue is never the carrier**. Each state is")
    A("placed on a lightness staircase and given its own non-colour mark. The table")
    A("below is the proof: `grey` is the neutral of identical relative luminance - what")
    A("the fill becomes when hue information is unavailable - and `step` is the CIE L\\*")
    A("distance to the state immediately below it.")
    A("")
    for key, rows in res.grey.items():
        group, theme = key.split("/")
        A("### Group `%s` - %s theme" % (group, theme))
        A("")
        A("| State token | fill | greyscale equivalent | L\\* | step below | non-colour mark |")
        A("|---|---|---|---|---|---|")
        for r in rows:
            step = "-" if r["delta"] is None else "%.1f" % r["delta"]
            A(
                "| `%s` | `%s` | `%s` | %.1f | %s | `%s` |"
                % (r["token"], r["hex"], r["grey"], r["lstar"], step, r["glyph"])
            )
        A("")
        A("```text")
        A("lightness staircase, greyscale only (0 = black, 100 = white)")
        for r in rows:
            A("%-26s %s %5.1f  %s" % (r["token"], bar(r["lstar"]), r["lstar"], r["glyph"]))
        A("```")
        A("")

    A("### Each fill against the seat-map field")
    A("")
    A("A staircase between states is not enough on its own - every state also has to")
    A("read against `%s`, the field the map is drawn on. A state that sits" % SEAT_FIELD_TOKEN)
    A("closer than %.0f L\\* to the field must carry an edge token that clears 3.0:1."
      % SEAT_FIELD_MIN_DELTA_L)
    A("")
    A("| Theme | State | L\\* from field | edge token | edge ratio | |")
    A("|---|---|---|---|---|---|")
    for r in sorted(res.seat_field, key=lambda x: (x["theme"], x["token"])):
        edge = "`--fr-%s`" % r["edge"] if r["edge"] else "-"
        er = "%.2f:1" % r["edge_ratio"] if r["edge_ratio"] is not None else "-"
        A(
            "| %s | `%s` | %.1f | %s | %s | %s |"
            % (r["theme"], r["token"], r["delta"], edge, er, "PASS" if r["pass"] else "**FAIL**")
        )
    A("")

    A("## Every pair, both themes")
    A("")
    for theme in ("light", "dark"):
        rows = [p for p in res.pairs if p["theme"] == theme]
        rows.sort(key=lambda p: p["ratio"])
        A("### %s theme - %d pairs, worst first" % (theme.capitalize(), len(rows)))
        A("")
        A("| Foreground | Background | Role | Ratio | Floor | |")
        A("|---|---|---|---|---|---|")
        for p in rows:
            A(
                "| `%s` <br>`%s` | `%s` <br>`%s` | `@%s` | **%.2f:1** | %.1f:1 | %s |"
                % (
                    p["fg"], p["fg_hex"], p["bg"], p["bg_hex"], p["role"],
                    p["ratio"], p["floor"], "PASS" if p["pass"] else "**FAIL**",
                )
            )
        A("")

    A("## Not measured, and why")
    A("")
    if res.decor:
        A("A token may be exempted from a contrast floor only by declaring `@decor` with an")
        A("explicit reason. The script fails if a reason is missing, so this list cannot")
        A("quietly grow.")
        A("")
        A("| Token | Reason given |")
        A("|---|---|")
        for name, why, _roles in res.decor:
            A("| `%s` | %s |" % (name, why))
    else:
        A("Nothing is exempt.")
    A("")
    A("---")
    A("")
    A("*End of generated output.*")
    return "\n".join(L) + "\n"


def report(res: Result, quiet: bool) -> None:
    c = res.counts
    print("contrast.py - FrontRow design system")
    print("  tokens.css sha256      %s" % c.get("tokens_sha256", "-"))
    print("  colour tokens          %d" % c.get("colour_tokens", 0))
    print("  pairs checked          %d  (light %d, dark %d)"
          % (c.get("pairs", 0), c.get("pairs_light", 0), c.get("pairs_dark", 0)))
    print("  lowest ratio           %.2f:1" % c.get("min_ratio", 0.0))
    print("  greyscale steps        %d" % c.get("grey_pairs", 0))
    print("  smallest L* step       %.1f  (floor %.1f)"
          % (c.get("min_delta_l", 0.0), GREY_MIN_DELTA_L))
    print("  tokens declared        %d" % c.get("declared", 0))
    print("  tokens used by specs   %d" % c.get("named_in_components", 0))
    print("  declared but unused    %d" % c.get("unused", 0))
    print("  used but undeclared    %d" % c.get("unknown", 0))
    print("")
    for key, (desc, unit) in CHECKS.items():
        st = res.status(key)
        n = res.subjects[key]
        print("  [%-4s] %-15s %-4d %-14s %s"
              % (st, key, n, unit + ("" if n == 1 else "s"), desc))
        if st == "SKIP":
            print("         - zero subjects: this check did not run, so it cannot be a pass")
        if res.failures[key] and not quiet:
            for f in res.failures[key]:
                print("         - %s" % f)
    print("")
    print("checks: %d  -  %d pass  -  %d fail  -  %d skip"
          % (len(CHECKS), res.n_pass, res.n_fail, res.n_skip))
    print("RESULT: %s" % ("PASS" if res.ok else "FAIL"))


# ---------------------------------------------------------------------------
# --selftest: plant a real violation of every check and require each one to fire
# ---------------------------------------------------------------------------
FIXTURE_TOKENS = """\
/* Fixture written by contrast.py --selftest. Not part of the design system.
   It exists so every check can be red-proofed BEFORE the real tokens.css is
   authored: a checker that can only be trusted after its subject exists is a
   checker nobody red-proofed on the day it mattered. */
:root {
  /* @block structural */
  --fr-space-1: 4px;

  /* @block palette-light */
  --fr-surface-base: #FFFFFF;   /* @ground */
  --fr-surface-inset: #F0F0F0;  /* @ground */
  --fr-ink: #1A1A1A;            /* @text on:surface-base,surface-inset */
  --fr-decor-wash: #EFEFEF;     /* @decor why:"fixture wash, carries nothing" */
  --fr-seat-a: #E6E6E6;         /* @ground @grey:seat glyph:outline edge:seat-edge */
  --fr-seat-b: #A8A8A8;         /* @ground @grey:seat glyph:wait */
  --fr-seat-c: #6E6E6E;         /* @ground @grey:seat glyph:cross */
  --fr-seat-d: #2E2E2E;         /* @ground @grey:seat glyph:check */
  --fr-seat-edge: #6E6E6E;      /* @ui on:surface-inset */
  --fr-seat-ink: #FFFFFF;       /* @text on:seat-c,seat-d */
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* @block palette-dark-auto */
    --fr-surface-base: #0E0E0E;
    --fr-surface-inset: #050505;
    --fr-ink: #F2F2F2;
    --fr-decor-wash: #1A1A1A;
    --fr-seat-a: #262626;
    --fr-seat-b: #4D4D4D;
    --fr-seat-c: #7D7D7D;
    --fr-seat-d: #C4C4C4;
    --fr-seat-edge: #8A8A8A;
    --fr-seat-ink: #0A0A0A;
  }
}
:root[data-theme="dark"] {
  /* @block palette-dark-explicit */
  --fr-surface-base: #0E0E0E;
  --fr-surface-inset: #050505;
  --fr-ink: #F2F2F2;
  --fr-decor-wash: #1A1A1A;
  --fr-seat-a: #262626;
  --fr-seat-b: #4D4D4D;
  --fr-seat-c: #7D7D7D;
  --fr-seat-d: #C4C4C4;
  --fr-seat-edge: #8A8A8A;
  --fr-seat-ink: #0A0A0A;
}
"""

FIXTURE_COMPONENTS = """\
# Fixture COMPONENTS.md - written by contrast.py --selftest, not a real spec.

Names every fixture token exactly once so TOKEN-COVERAGE has both directions
satisfied and can be red-proofed by adding one unreferenced token.

`--fr-space-1` `--fr-surface-base` `--fr-surface-inset` `--fr-ink`
`--fr-decor-wash` `--fr-seat-a` `--fr-seat-b` `--fr-seat-c` `--fr-seat-d`
`--fr-seat-edge` `--fr-seat-ink`
"""


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8", newline="\n")


def _edit(p: Path, fn) -> bool:
    old = _read(p) if p.exists() else ""
    new = fn(old)
    if new == old:
        return False
    _write(p, new)
    return True


def _lines_with_blocks(text: str):
    """Yield (index, block_name_or_None, line) for every line."""
    current = None
    out = []
    for i, line in enumerate(text.replace("\r\n", "\n").split("\n")):
        m = BLOCK_RE.search(line)
        if m:
            current = m.group(1)
            out.append((i, current, line))
            continue
        out.append((i, current, line))
    return out


def _insert_after_marker(p: Path, block: str, payload: str) -> bool:
    def fn(text: str) -> str:
        lines = text.replace("\r\n", "\n").split("\n")
        for i, line in enumerate(lines):
            m = BLOCK_RE.search(line)
            if m and m.group(1) == block:
                lines.insert(i + 1, payload)
                return "\n".join(lines)
        return text
    return _edit(p, fn)


def _first_decl_line_in(text: str, block: str, pred=None):
    """Return (index, match) of the first parseable declaration in `block`."""
    for i, blk, line in _lines_with_blocks(text):
        if blk != block:
            continue
        m = DECL_RE.match(line)
        if not m:
            continue
        if pred is None or pred(m):
            return i, m
    return None, None


def _model(p: Path):
    """Parse the work copy the way run() does, so plants can adapt to whatever
    tokens.css actually says instead of hard-coding a token name that may not
    exist. Returns (blocks, annotations, resolved_light) or None."""
    if not p.exists():
        return None
    blocks, errs, _n = parse_tokens(_read(p))
    if any(e.startswith("PARSE") for e in errs):
        return None
    if not all(b in blocks for b in REQUIRED_BLOCKS):
        return None
    annotations = OrderedDict(
        list(blocks[BLOCK_STRUCTURAL].items()) + list(blocks[BLOCK_LIGHT].items())
    )
    light, _e = resolve(annotations)
    return blocks, annotations, light


def _set_value_in_block(p: Path, block: str, token: str, new_value: str) -> bool:
    def fn(text: str) -> str:
        lines = text.replace("\r\n", "\n").split("\n")
        for i, blk, line in _lines_with_blocks(text):
            if blk != block:
                continue
            m = DECL_RE.match(line)
            if m and m.group("name") == token:
                note = m.group("note")
                indent = line[: len(line) - len(line.lstrip())]
                comment = "  /*%s*/" % note if note is not None else ""
                lines[i] = "%s%s: %s;%s" % (indent, token, new_value, comment)
                return "\n".join(lines)
        return text
    return _edit(p, fn)


def _strip_annotation(p: Path, block: str, token: str, prefix: str) -> bool:
    def fn(text: str) -> str:
        lines = text.replace("\r\n", "\n").split("\n")
        for i, blk, line in _lines_with_blocks(text):
            if blk != block:
                continue
            m = DECL_RE.match(line)
            if m and m.group("name") == token and m.group("note"):
                note = " ".join(w for w in m.group("note").split()
                                if not w.startswith(prefix))
                indent = line[: len(line) - len(line.lstrip())]
                lines[i] = "%s%s: %s;  /* %s */" % (indent, token, m.group("value").strip(), note)
                return "\n".join(lines)
        return text
    return _edit(p, fn)


def _grey_group(model):
    """The first greyscale group with at least two members: (name, [tokens])."""
    _blocks, annotations, _light = model
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for name, tok in annotations.items():
        if tok.grey:
            groups.setdefault(tok.grey, []).append(name)
    for g, members in groups.items():
        if len(members) >= 2:
            return g, members
    return None, []


def _block_of(model, token: str) -> str:
    blocks, _a, _l = model
    return BLOCK_LIGHT if token in blocks[BLOCK_LIGHT] else BLOCK_STRUCTURAL


def plant_parse(w: Paths) -> bool:
    return _edit(w.tokens, lambda t: t.replace("/* @block %s */" % BLOCK_DARK_EXPLICIT,
                                               "/* dark, explicit */", 1))


def plant_one_per_line(w: Paths) -> bool:
    return _insert_after_marker(
        w.tokens, BLOCK_STRUCTURAL,
        "  --fr-planted-one: 1px; --fr-planted-two: 2px;")


def plant_annotated(w: Paths) -> bool:
    return _insert_after_marker(w.tokens, BLOCK_STRUCTURAL, "  --fr-planted-annot: #123456;")


def plant_decor_why(w: Paths) -> bool:
    return _insert_after_marker(w.tokens, BLOCK_STRUCTURAL,
                                "  --fr-planted-decor: #123456;  /* @decor */")


def plant_on_resolves(w: Paths) -> bool:
    return _insert_after_marker(
        w.tokens, BLOCK_STRUCTURAL,
        "  --fr-planted-on: #123456;  /* @text on:planted-nowhere */")


def plant_theme_parity(w: Paths) -> bool:
    return _insert_after_marker(
        w.tokens, BLOCK_LIGHT,
        "  --fr-planted-parity: #123456;  /* @decor why:\"light only, on purpose\" */")


def plant_dark_identical(w: Paths) -> bool:
    i, m = _first_decl_line_in(_read(w.tokens), BLOCK_DARK_AUTO)
    if m is None:
        return False
    return _set_value_in_block(w.tokens, BLOCK_DARK_AUTO, m.group("name"), "#010203")


def plant_contrast(w: Paths) -> bool:
    model = _model(w.tokens)
    if not model:
        return False
    _blocks, annotations, light = model
    for name, tok in annotations.items():
        if "ground" in tok.roles and is_colour(light.get(name, "")):
            return _insert_after_marker(
                w.tokens, BLOCK_STRUCTURAL,
                "  --fr-planted-contrast: %s;  /* @text on:%s */"
                % (light[name], name[len("--fr-"):]))
    return False


def plant_greyscale(w: Paths) -> bool:
    model = _model(w.tokens)
    if not model:
        return False
    _g, members = _grey_group(model)
    if len(members) < 2:
        return False
    _blocks, _a, light = model
    first, second = members[0], members[1]
    return _set_value_in_block(w.tokens, _block_of(model, second), second, light[first])


def plant_glyph(w: Paths) -> bool:
    model = _model(w.tokens)
    if not model:
        return False
    _g, members = _grey_group(model)
    if not members:
        return False
    return _strip_annotation(w.tokens, _block_of(model, members[0]), members[0], "glyph:")


def plant_seat_field(w: Paths) -> bool:
    model = _model(w.tokens)
    if not model:
        return False
    _blocks, _a, light = model
    _g, members = _grey_group(model)
    field = light.get(SEAT_FIELD_TOKEN)
    if not members or not field or not is_colour(field):
        return False
    target = members[0]
    blk = _block_of(model, target)
    changed = _strip_annotation(w.tokens, blk, target, "edge:")
    changed = _set_value_in_block(w.tokens, blk, target, field) or changed
    return changed


def plant_token_coverage(w: Paths) -> bool:
    return _insert_after_marker(w.tokens, BLOCK_STRUCTURAL, "  --fr-planted-unused: 1px;")


def plant_generated(w: Paths) -> bool:
    return _edit(w.out, lambda t: t + "\nPlanted: a hand edit to a generated file.\n")


PLANTS = [
    ("PARSE", "the @block palette-dark-explicit marker deleted", plant_parse),
    ("ONE-PER-LINE", "two custom properties crammed onto one line", plant_one_per_line),
    ("ANNOTATED", "a colour token added with no role annotation", plant_annotated),
    ("DECOR-WHY", "a token claiming @decor with no why:\"...\"", plant_decor_why),
    ("ON-RESOLVES", "a foreground whose on: names a background that does not exist",
     plant_on_resolves),
    ("THEME-PARITY", "a palette token added to light and not to dark", plant_theme_parity),
    ("DARK-IDENTICAL", "one value changed in the prefers-color-scheme block only",
     plant_dark_identical),
    ("CONTRAST", "a foreground set to the exact colour of its own background (1.00:1)",
     plant_contrast),
    ("GREYSCALE", "two seat states given the same fill, so 0.0 L* separates them",
     plant_greyscale),
    ("GLYPH", "a seat state stripped of its non-colour mark", plant_glyph),
    ("SEAT-FIELD", "a seat fill set to the field colour with its edge token removed",
     plant_seat_field),
    ("TOKEN-COVERAGE", "a token declared that no component spec names", plant_token_coverage),
    ("GENERATED", "a line appended by hand to the generated CONTRAST.md", plant_generated),
]


def evaluate(paths: Paths, check_disk: bool) -> Result:
    """One full run. `check_disk` adds the GENERATED check, which compares what is
    on disk against what tokens.css produces. Render happens BEFORE that failure is
    recorded, so the comparison is not self-referential."""
    res = run(paths)
    body = render(res)
    if check_disk:
        if not paths.out.exists():
            res.fail("GENERATED", "CONTRAST.md has never been generated - run without --check")
        elif paths.out.read_text(encoding="utf-8").replace("\r\n", "\n") != body:
            res.fail("GENERATED",
                     "CONTRAST.md on disk does not match what tokens.css produces - it is "
                     "stale or was hand-edited. Regenerate it.")
    res.counts["_body"] = body  # type: ignore[assignment]
    return res


def selftest(base: Path) -> int:
    """Red-proof every check by DELTA.

    Requiring a clean baseline would mean the tool can only be trusted on a green
    design system - which is never the day you need it. So the baseline is measured
    inside each throwaway copy, and each plant must make ITS OWN check's failure
    count RISE. A check nobody has watched fail is decoration.
    """
    print("contrast.py --selftest - red-proofing every check by delta")
    live = evaluate(Paths(base), check_disk=True)
    print("  live directory: %s" % base)
    print("  live baseline:  %d pass, %d fail, %d skip"
          % (live.n_pass, live.n_fail, live.n_skip))
    synth = not (base / "tokens.css").exists()
    if synth:
        print("  tokens.css is absent, so each copy is seeded with the built-in fixture")
        print("  before planting. The checker is proved BEFORE its subject is authored.")
    print("")

    passed = 0
    for key, what, plant in PLANTS:
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "designsystem"
            shutil.copytree(base, work_dir,
                            ignore=shutil.ignore_patterns("__pycache__", ".git"))
            w = Paths(work_dir)
            if not w.tokens.exists():
                _write(w.tokens, FIXTURE_TOKENS)
                _write(w.components, FIXTURE_COMPONENTS)
            # Normalise only the generated artefact, so GENERATED starts green and
            # its plant has somewhere to rise from.
            _write(w.out, evaluate(w, check_disk=False).counts["_body"])  # type: ignore[arg-type]

            before = evaluate(w, check_disk=True)
            if not plant(w):
                print("  FAIL  %-15s the plant was a no-op - it proved nothing" % key)
                continue
            after = evaluate(w, check_disk=True)
            b, a = len(before.failures[key]), len(after.failures[key])
            if a > b:
                passed += 1
                print("  ok    %-15s %d -> %d failure(s)   planted: %s" % (key, b, a, what))
            else:
                print("  FAIL  %-15s %d -> %d failure(s)   DID NOT FIRE. A check that "
                      "cannot fail is decoration. Planted: %s" % (key, b, a, what))
    print("")
    print("%d/%d checks red-proofed" % (passed, len(PLANTS)))
    return 0 if passed == len(PLANTS) else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Compute and verify FrontRow contrast figures.")
    ap.add_argument("--check", action="store_true",
                    help="verify only; write nothing; also fail if CONTRAST.md is stale")
    ap.add_argument("--selftest", action="store_true",
                    help="plant a real violation of every check and require each one to fire")
    ap.add_argument("--quiet", action="store_true", help="suppress per-failure detail")
    ap.add_argument("--dir", default=str(HERE), help="the design-system directory to operate on")
    args = ap.parse_args(argv)

    base = Path(args.dir).resolve()
    if args.selftest:
        return selftest(base)

    paths = Paths(base)
    res = evaluate(paths, check_disk=args.check)
    if not args.check:
        _write(paths.out, res.counts["_body"])  # type: ignore[arg-type]
    report(res, args.quiet)
    if not args.check:
        print("wrote %s" % paths.out)
    return 0 if res.ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # a check that dies silently is not a check
        traceback.print_exc()
        print("contrast.py could not run: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(2)
