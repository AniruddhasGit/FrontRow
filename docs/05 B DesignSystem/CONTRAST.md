<!-- ------------------------------------------------------------------
     GENERATED FILE - DO NOT EDIT BY HAND
     Produced by: docs/05 B DesignSystem/contrast.py
     Regenerate:  py "docs/05 B DesignSystem/contrast.py"
     Verify:      py "docs/05 B DesignSystem/contrast.py" --check
     Red-proof:   py "docs/05 B DesignSystem/contrast.py" --selftest
     Any edit made here is destroyed on the next run.
     ------------------------------------------------------------------ -->

# CONTRAST.md - computed, not claimed

> **GENERATED.** Every number on this page was computed by `contrast.py` from
> `tokens.css`. No figure here was typed by a human, and no figure here may be
> quoted into another document by hand - cite this file or re-run the script.
> `CONSTITUTION.md` Art VII.1.

| | |
|---|---|
| Source of record | `tokens.css` |
| `tokens.css` SHA-256 | `456cf8be61bf64b648d9a7bb24d6e979f7d83402a6b1c059d48e15e529c1c37f` |
| Colour tokens | 32 |
| Foreground/background pairs checked | **70** (35 light, 35 dark) |
| Lowest ratio measured | **3.68:1** |
| Greyscale steps checked | 6 |
| Smallest lightness step measured | **14.1 L\*** (floor 12.0) |
| Checks | 13 pass, 0 fail, 0 skip, of 13 |
| Result | **ALL CHECKS PASS** |

## How the pair list is built

The pairs below are **derived from `tokens.css`**, not from a list kept inside the
script. Each colour token carries a machine-readable annotation in its trailing
comment: a role (`@text`, `@text-lg`, `@ui`, `@ground`, `@decor`) and, for a
foreground, the `on:` backgrounds it is allowed to sit on. The script takes the
cross product. Adding a token without an annotation fails the `ANNOTATED` check,
so a new colour cannot enter the system unmeasured.

| Role | Floor | WCAG 2.2 criterion |
|---|---|---|
| `@text` | 4.5:1 | 1.4.3 Contrast (Minimum), normal text |
| `@text-lg` | 3.0:1 | 1.4.3 Contrast (Minimum), large text (>=24px, or >=18.66px bold) |
| `@ui` | 3.0:1 | 1.4.11 Non-text Contrast, UI components and graphical objects |

## Checks

`subjects` is how many things the check actually looked at. A check with zero
subjects reports **SKIP**, never PASS - a check over an empty set has not run,
and reporting it green is the failure mode `GOTCHAS.md` warns about. A SKIP holds
the exit code at 1 exactly as a FAIL does.

| Check | What it proves | Subjects | Result |
|---|---|---|---|
| `PARSE` | tokens.css parses and every block marker is present | 153 declarations | PASS |
| `ONE-PER-LINE` | every custom property is declared on its own line | 149 lines | PASS |
| `ANNOTATED` | every colour-valued token carries a role annotation | 32 colour tokens | PASS |
| `DECOR-WHY` | every @decor token states why it is exempt | 3 exemptions | PASS |
| `ON-RESOLVES` | every on: target names a real @ground token | 19 foreground tokens | PASS |
| `THEME-PARITY` | light and dark define exactly the same palette tokens | 35 palette tokens | PASS |
| `DARK-IDENTICAL` | the two dark blocks are value-for-value identical | 35 tokens | PASS |
| `CONTRAST` | every derived pair meets its WCAG floor in both themes | 70 pairs | PASS |
| `GREYSCALE` | seat states separate by >=12 L* with no colour | 6 steps | PASS |
| `GLYPH` | every seat state carries a distinct non-colour mark | 4 states | PASS |
| `SEAT-FIELD` | every seat fill separates from the seat-map field | 8 fill x themes | PASS |
| `TOKEN-COVERAGE` | tokens.css and COMPONENTS.md name the same token set | 79 tokens | PASS |
| `GENERATED` | CONTRAST.md on disk is exactly what tokens.css produces | 1 file | PASS |

## Token coverage

Both directions, because one direction alone is not a check: a token nobody uses
is dead weight, and a component naming a token that does not exist is a build
failure waiting for the first person who tries it.

| Direction | Count |
|---|---|
| Tokens declared in `tokens.css` | 79 |
| Distinct tokens named in `COMPONENTS.md` | 79 |
| Declared but used by no component spec | **0** |
| Named by a component spec but not declared | **0** |

## Greyscale separability of the seat states

Roughly one man in twelve cannot separate the hue palette a seat map normally
reaches for. So on this seat map **hue is never the carrier**. Each state is
placed on a lightness staircase and given its own non-colour mark. The table
below is the proof: `grey` is the neutral of identical relative luminance - what
the fill becomes when hue information is unavailable - and `step` is the CIE L\*
distance to the state immediately below it.

### Group `seat` - light theme

| State token | fill | greyscale equivalent | L\* | step below | non-colour mark |
|---|---|---|---|---|---|
| `--fr-seat-mine` | `#1D667B` | `#5E5E5E` | 39.9 | - | `check` |
| `--fr-seat-held-other` | `#AA7E45` | `#868686` | 56.0 | 16.1 | `bar` |
| `--fr-seat-sold` | `#A7ACB1` | `#ABABAB` | 70.1 | 14.1 | `hatch` |
| `--fr-seat-available` | `#E0D6C5` | `#D7D7D7` | 86.0 | 15.9 | `outline` |

```text
lightness staircase, greyscale only (0 = black, 100 = white)
--fr-seat-mine             ████████████████························  39.9  check
--fr-seat-held-other       ██████████████████████··················  56.0  bar
--fr-seat-sold             ████████████████████████████············  70.1  hatch
--fr-seat-available        ██████████████████████████████████······  86.0  outline
```

### Group `seat` - dark theme

| State token | fill | greyscale equivalent | L\* | step below | non-colour mark |
|---|---|---|---|---|---|
| `--fr-seat-available` | `#1F242B` | `#242424` | 14.0 | - | `outline` |
| `--fr-seat-sold` | `#42474D` | `#464646` | 29.9 | 15.9 | `hatch` |
| `--fr-seat-held-other` | `#88673D` | `#6D6D6D` | 46.0 | 16.1 | `bar` |
| `--fr-seat-mine` | `#32B5CA` | `#A6A6A6` | 68.0 | 22.0 | `check` |

```text
lightness staircase, greyscale only (0 = black, 100 = white)
--fr-seat-available        ██████··································  14.0  outline
--fr-seat-sold             ████████████····························  29.9  hatch
--fr-seat-held-other       ██████████████████······················  46.0  bar
--fr-seat-mine             ███████████████████████████·············  68.0  check
```

### Each fill against the seat-map field

A staircase between states is not enough on its own - every state also has to
read against `--fr-surface-inset`, the field the map is drawn on. A state that sits
closer than 8 L\* to the field must carry an edge token that clears 3.0:1.

| Theme | State | L\* from field | edge token | edge ratio | |
|---|---|---|---|---|---|
| dark | `--fr-seat-available` | 11.0 | `--fr-seat-edge-available` | 3.80:1 | PASS |
| dark | `--fr-seat-held-other` | 43.0 | - | - | PASS |
| dark | `--fr-seat-mine` | 65.0 | `--fr-seat-edge-mine` | 13.65:1 | PASS |
| dark | `--fr-seat-sold` | 26.9 | - | - | PASS |
| light | `--fr-seat-available` | 5.5 | `--fr-seat-edge-available` | 3.70:1 | PASS |
| light | `--fr-seat-held-other` | 35.5 | - | - | PASS |
| light | `--fr-seat-mine` | 51.6 | `--fr-seat-edge-mine` | 6.43:1 | PASS |
| light | `--fr-seat-sold` | 21.4 | - | - | PASS |

## Every pair, both themes

### Light theme - 35 pairs, worst first

| Foreground | Background | Role | Ratio | Floor | |
|---|---|---|---|---|---|
| `--fr-rule` <br>`#807463` | `--fr-surface-inset` <br>`#EDE6DA` | `@ui` | **3.68:1** | 3.0:1 | PASS |
| `--fr-seat-edge-available` <br>`#7E7465` | `--fr-surface-inset` <br>`#EDE6DA` | `@ui` | **3.70:1** | 3.0:1 | PASS |
| `--fr-control-edge` <br>`#7B7264` | `--fr-surface-inset` <br>`#EDE6DA` | `@ui` | **3.82:1** | 3.0:1 | PASS |
| `--fr-rule` <br>`#807463` | `--fr-surface-base` <br>`#FAF6EF` | `@ui` | **4.24:1** | 3.0:1 | PASS |
| `--fr-control-edge` <br>`#7B7264` | `--fr-surface-base` <br>`#FAF6EF` | `@ui` | **4.40:1** | 3.0:1 | PASS |
| `--fr-rule` <br>`#807463` | `--fr-surface-raised` <br>`#FFFFFF` | `@ui` | **4.57:1** | 3.0:1 | PASS |
| `--fr-control-edge` <br>`#7B7264` | `--fr-surface-raised` <br>`#FFFFFF` | `@ui` | **4.74:1** | 3.0:1 | PASS |
| `--fr-seat-ink` <br>`#1C1A16` | `--fr-seat-held-other` <br>`#AA7E45` | `@text` | **4.78:1** | 4.5:1 | PASS |
| `--fr-focus-ring` <br>`#0A6A82` | `--fr-surface-inset` <br>`#EDE6DA` | `@ui` | **4.98:1** | 3.0:1 | PASS |
| `--fr-focus-ring` <br>`#0A6A82` | `--fr-surface-base` <br>`#FAF6EF` | `@ui` | **5.74:1** | 3.0:1 | PASS |
| `--fr-seat-ink-mine` <br>`#EAF6FA` | `--fr-seat-mine` <br>`#1D667B` | `@text` | **5.89:1** | 4.5:1 | PASS |
| `--fr-ink-muted` <br>`#5A5348` | `--fr-surface-inset` <br>`#EDE6DA` | `@text` | **6.12:1** | 4.5:1 | PASS |
| `--fr-focus-ring` <br>`#0A6A82` | `--fr-surface-raised` <br>`#FFFFFF` | `@ui` | **6.18:1** | 3.0:1 | PASS |
| `--fr-countdown-fill` <br>`#0F6A80` | `--fr-surface-raised` <br>`#FFFFFF` | `@ui` | **6.19:1** | 3.0:1 | PASS |
| `--fr-seat-edge-mine` <br>`#12586B` | `--fr-surface-inset` <br>`#EDE6DA` | `@ui` | **6.43:1** | 3.0:1 | PASS |
| `--fr-accent-ink` <br>`#7E4C0D` | `--fr-surface-base` <br>`#FAF6EF` | `@text` | **6.66:1** | 4.5:1 | PASS |
| `--fr-countdown-urgent` <br>`#A82E0E` | `--fr-surface-raised` <br>`#FFFFFF` | `@ui` | **6.86:1** | 3.0:1 | PASS |
| `--fr-ink-muted` <br>`#5A5348` | `--fr-surface-base` <br>`#FAF6EF` | `@text` | **7.05:1** | 4.5:1 | PASS |
| `--fr-accent-ink` <br>`#7E4C0D` | `--fr-surface-raised` <br>`#FFFFFF` | `@text` | **7.18:1** | 4.5:1 | PASS |
| `--fr-screen-ink` <br>`#0B5A6E` | `--fr-surface-base` <br>`#FAF6EF` | `@text` | **7.21:1** | 4.5:1 | PASS |
| `--fr-danger-ink` <br>`#97270F` | `--fr-surface-base` <br>`#FAF6EF` | `@text` | **7.46:1** | 4.5:1 | PASS |
| `--fr-ink-muted` <br>`#5A5348` | `--fr-surface-raised` <br>`#FFFFFF` | `@text` | **7.59:1** | 4.5:1 | PASS |
| `--fr-seat-ink` <br>`#1C1A16` | `--fr-seat-sold` <br>`#A7ACB1` | `@text` | **7.59:1** | 4.5:1 | PASS |
| `--fr-screen-ink` <br>`#0B5A6E` | `--fr-surface-raised` <br>`#FFFFFF` | `@text` | **7.77:1** | 4.5:1 | PASS |
| `--fr-ink-on-accent` <br>`#1C1204` | `--fr-surface-accent` <br>`#E39B2E` | `@text` | **7.91:1** | 4.5:1 | PASS |
| `--fr-danger-ink` <br>`#97270F` | `--fr-surface-raised` <br>`#FFFFFF` | `@text` | **8.04:1** | 4.5:1 | PASS |
| `--fr-ink-on-danger` <br>`#7A2110` | `--fr-surface-danger` <br>`#FBE6E0` | `@text` | **8.52:1** | 4.5:1 | PASS |
| `--fr-screen-bar` <br>`#223039` | `--fr-surface-inset` <br>`#EDE6DA` | `@ui` | **10.92:1** | 3.0:1 | PASS |
| `--fr-seat-ink` <br>`#1C1A16` | `--fr-seat-available` <br>`#E0D6C5` | `@text` | **12.07:1** | 4.5:1 | PASS |
| `--fr-ink` <br>`#2B2620` | `--fr-surface-inset` <br>`#EDE6DA` | `@text` | **12.09:1** | 4.5:1 | PASS |
| `--fr-ink` <br>`#2B2620` | `--fr-surface-base` <br>`#FAF6EF` | `@text` | **13.92:1** | 4.5:1 | PASS |
| `--fr-ink-on-notice` <br>`#E9F2F7` | `--fr-surface-notice` <br>`#16212B` | `@text` | **14.39:1** | 4.5:1 | PASS |
| `--fr-ink` <br>`#2B2620` | `--fr-surface-raised` <br>`#FFFFFF` | `@text` | **14.99:1** | 4.5:1 | PASS |
| `--fr-ink-strong` <br>`#14110C` | `--fr-surface-base` <br>`#FAF6EF` | `@text` | **17.48:1** | 4.5:1 | PASS |
| `--fr-ink-strong` <br>`#14110C` | `--fr-surface-raised` <br>`#FFFFFF` | `@text` | **18.83:1** | 4.5:1 | PASS |

### Dark theme - 35 pairs, worst first

| Foreground | Background | Role | Ratio | Floor | |
|---|---|---|---|---|---|
| `--fr-seat-edge-available` <br>`#626E7D` | `--fr-surface-inset` <br>`#080B10` | `@ui` | **3.80:1** | 3.0:1 | PASS |
| `--fr-rule` <br>`#707D89` | `--fr-surface-raised` <br>`#151C25` | `@ui` | **4.07:1** | 3.0:1 | PASS |
| `--fr-control-edge` <br>`#78848F` | `--fr-surface-raised` <br>`#151C25` | `@ui` | **4.49:1** | 3.0:1 | PASS |
| `--fr-rule` <br>`#707D89` | `--fr-surface-base` <br>`#0D1117` | `@ui` | **4.49:1** | 3.0:1 | PASS |
| `--fr-rule` <br>`#707D89` | `--fr-surface-inset` <br>`#080B10` | `@ui` | **4.68:1** | 3.0:1 | PASS |
| `--fr-seat-ink` <br>`#F2F5F8` | `--fr-seat-held-other` <br>`#88673D` | `@text` | **4.73:1** | 4.5:1 | PASS |
| `--fr-control-edge` <br>`#78848F` | `--fr-surface-base` <br>`#0D1117` | `@ui` | **4.95:1** | 3.0:1 | PASS |
| `--fr-control-edge` <br>`#78848F` | `--fr-surface-inset` <br>`#080B10` | `@ui` | **5.16:1** | 3.0:1 | PASS |
| `--fr-seat-ink-mine` <br>`#04222B` | `--fr-seat-mine` <br>`#32B5CA` | `@text` | **6.78:1** | 4.5:1 | PASS |
| `--fr-countdown-urgent` <br>`#FF8A63` | `--fr-surface-raised` <br>`#151C25` | `@ui` | **7.40:1** | 3.0:1 | PASS |
| `--fr-ink-muted` <br>`#A2ADBA` | `--fr-surface-raised` <br>`#151C25` | `@text` | **7.53:1** | 4.5:1 | PASS |
| `--fr-ink-muted` <br>`#A2ADBA` | `--fr-surface-base` <br>`#0D1117` | `@text` | **8.31:1** | 4.5:1 | PASS |
| `--fr-danger-ink` <br>`#FF9C7E` | `--fr-surface-raised` <br>`#151C25` | `@text` | **8.42:1** | 4.5:1 | PASS |
| `--fr-seat-ink` <br>`#F2F5F8` | `--fr-seat-sold` <br>`#42474D` | `@text` | **8.57:1** | 4.5:1 | PASS |
| `--fr-ink-muted` <br>`#A2ADBA` | `--fr-surface-inset` <br>`#080B10` | `@text` | **8.65:1** | 4.5:1 | PASS |
| `--fr-countdown-fill` <br>`#4FC9E0` | `--fr-surface-raised` <br>`#151C25` | `@ui` | **8.79:1** | 3.0:1 | PASS |
| `--fr-accent-ink` <br>`#EAB05A` | `--fr-surface-raised` <br>`#151C25` | `@text` | **8.86:1** | 4.5:1 | PASS |
| `--fr-ink-on-accent` <br>`#1C1204` | `--fr-surface-accent` <br>`#E8A93F` | `@text` | **8.95:1** | 4.5:1 | PASS |
| `--fr-danger-ink` <br>`#FF9C7E` | `--fr-surface-base` <br>`#0D1117` | `@text` | **9.29:1** | 4.5:1 | PASS |
| `--fr-accent-ink` <br>`#EAB05A` | `--fr-surface-base` <br>`#0D1117` | `@text` | **9.78:1** | 4.5:1 | PASS |
| `--fr-screen-ink` <br>`#6ED4EA` | `--fr-surface-raised` <br>`#151C25` | `@text` | **10.02:1** | 4.5:1 | PASS |
| `--fr-focus-ring` <br>`#5FD8F0` | `--fr-surface-raised` <br>`#151C25` | `@ui` | **10.26:1** | 3.0:1 | PASS |
| `--fr-screen-ink` <br>`#6ED4EA` | `--fr-surface-base` <br>`#0D1117` | `@text` | **11.06:1** | 4.5:1 | PASS |
| `--fr-focus-ring` <br>`#5FD8F0` | `--fr-surface-base` <br>`#0D1117` | `@ui` | **11.33:1** | 3.0:1 | PASS |
| `--fr-ink-on-danger` <br>`#FFC3B0` | `--fr-surface-danger` <br>`#2B1310` | `@text` | **11.37:1** | 4.5:1 | PASS |
| `--fr-focus-ring` <br>`#5FD8F0` | `--fr-surface-inset` <br>`#080B10` | `@ui` | **11.79:1** | 3.0:1 | PASS |
| `--fr-ink` <br>`#DDE4EC` | `--fr-surface-raised` <br>`#151C25` | `@text` | **13.38:1** | 4.5:1 | PASS |
| `--fr-seat-edge-mine` <br>`#8CE4F6` | `--fr-surface-inset` <br>`#080B10` | `@ui` | **13.65:1** | 3.0:1 | PASS |
| `--fr-seat-ink` <br>`#F2F5F8` | `--fr-seat-available` <br>`#1F242B` | `@text` | **14.26:1** | 4.5:1 | PASS |
| `--fr-ink-on-notice` <br>`#E9F2F7` | `--fr-surface-notice` <br>`#16212B` | `@text` | **14.39:1** | 4.5:1 | PASS |
| `--fr-ink` <br>`#DDE4EC` | `--fr-surface-base` <br>`#0D1117` | `@text` | **14.76:1** | 4.5:1 | PASS |
| `--fr-ink` <br>`#DDE4EC` | `--fr-surface-inset` <br>`#080B10` | `@text` | **15.37:1** | 4.5:1 | PASS |
| `--fr-ink-strong` <br>`#F4F7FA` | `--fr-surface-raised` <br>`#151C25` | `@text` | **15.95:1** | 4.5:1 | PASS |
| `--fr-screen-bar` <br>`#D2ECF4` | `--fr-surface-inset` <br>`#080B10` | `@ui` | **15.99:1** | 3.0:1 | PASS |
| `--fr-ink-strong` <br>`#F4F7FA` | `--fr-surface-base` <br>`#0D1117` | `@text` | **17.60:1** | 4.5:1 | PASS |

## Not measured, and why

A token may be exempted from a contrast floor only by declaring `@decor` with an
explicit reason. The script fails if a reason is missing, so this list cannot
quietly grow.

| Token | Reason given |
|---|---|
| `--fr-screen-glow` | the projector falloff under the SCREEN bar. It is a gradient stop on the seat-map field, carries no state, and nothing is ever read on top of it. |
| `--fr-rule-quiet` | the cosmetic divider between list rows. Removing it loses no information — the meaning-bearing rule is --fr-rule, which is held to 3:1. |
| `--fr-poster-empty-mark` | the perforation motif drawn in the missing-poster box. The words in that box use --fr-ink-muted on --fr-surface-inset, which is measured. |

---

*End of generated output.*
