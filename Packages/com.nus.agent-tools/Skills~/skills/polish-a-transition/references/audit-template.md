# Audit template

## Activity audit

**Activity:** <name> · **Entry points:** <prefab(s)>, <main script(s)> · **Watched in the editor:** yes / no

| # | Beat | Today (evidence) | Verdict | Fix | Uses | Size |
|---|---|---|---|---|---|---|
| 1 | Enter | Instant SetActive (`Panel.cs:120`) | Missing | Wire the shared fade-in-on-enable | shared component | S |
| 2 | Reveal | All 12 nodes appear on one frame (`Editor.cs:88`) | Missing | Staggered reveal, after the intro closes | extract from <activity> | M |
| … | | | | | | |

Verdicts: **OK**, **Inconsistent** (exists, differs from the vocabulary), **Missing**, **Broken** (stuck,
jumps, fights, dead input, with the path that reaches it), **Latent** (real, but nothing reaches it today),
**Unconfirmed** (couldn't trace it; say what would settle it).
Sizes: **S** wiring only · **M** extract or adapt a shared component · **L** new motion code.

**Shared files this plan touches:** <file> (also used by <activities>)
**Left for later:** <what and why>

## Beat audit (one beat across activities)

**Beat:** <name> · **House treatment:** <from the vocabulary>

| Activity | Today (evidence) | Verdict | Fix |
|---|---|---|---|

## Starter motion vocabulary (for a project with none)

Write this into the project's own interaction doc and point its CLAUDE.md at it. One treatment per beat:

| Beat | Treatment | Values |
|---|---|---|
| Enter | Fade + settle | 0.25 s, from 98% scale, unscaled |
| Reveal | Staggered deal-in, after the intro | 0.09 s apart, 0.45 s each, land at 1.08× |
| Hover / press | Lift / dip | 1.03× / 0.95× |
| Drop | Ease into slot; refused drops ease back | 0.3 s |
| Verdict | Right and wrong colours on the item | project colours |
| Attention | Pulse on the item; view frames it | ~1.5 pulses a second |
| Exit | Fade out, hand over | 0.2 s |
