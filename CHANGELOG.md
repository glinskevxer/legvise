# Changelog

Newest first. Every entry says what changed for somebody using the tool, not
what changed in the tree.

## 1.0.0 - 2026-08-20

The settings live in a file now, pruning stopped retiring markets, and there is
a command that reads the whole book back and re-derives it.

- **A settings file.** `legvise --config legvise.toml` reads the scan's numbers
  out of a `[scan]` table, and a flag on the command line still beats it for
  that run. `legvise config show` prints every setting with the level that
  decided it, because a value nobody set and a value somebody set to the same
  number look identical otherwise. A key the tool does not recognise is refused
  rather than ignored.
- **Pruning keeps what is load bearing.** `legvise db prune` replaces
  `legvise book prune`, which dropped every snapshot older than its cutoff, the
  newest one of a market included. A market with no snapshot is a market the
  scanner skips and the desk status calls unconfigured, and nothing said so. The
  newest snapshot of every market now stays whatever its age, and so does any
  session with a fill against it. `--dry-run` counts without deleting, and
  `--keep-days` counts back from the clock for a nightly job.
- **`legvise db verify`.** Reads the whole book and re-derives the plan
  arithmetic, the leg notionals, the foreign keys and the decimal spelling.
  Nothing here can fail on a file this tool wrote and nothing else touched,
  which is the point of running it after a restore.
- **One JSON shape per report.** The printed `--json` and the exported file were
  two dictionaries written months apart and they had already drifted: the
  printed session dropped the symbols and the venues and spelled the clauses as
  an object rather than a list. They are one function now.
- **A SQLite floor.** The retention sweep needs window functions, so the version
  is checked when the file is opened rather than when the query runs.
  `legvise db status` prints it.
- **Twenty three gates.** Sixteen self checks, five generated documents, the end
  to end run, and a check that watches the other checks: every check that exists
  is run by CI and collected by the release gate, and `check.sh` still finds
  them all.

## 0.1.0 - 2026-05-07

First release. A desk with inventory on several venues can set its venues up,
load books, and get priced and sized plans out the other side.

- **Cross venue scanning.** Buy on one venue and sell on another against
  balances already sitting there. Every plan carries the same decomposition:
  `net = gross - fees - slippage - rebalance`, and the arithmetic is checked
  rather than assumed.
- **Triangular scanning.** Loops inside one venue, screened at the touch and
  then priced against depth, because three hops means three taker fees and a
  loop that screens at four basis points does not survive them.
- **Depth aware sizing.** Every price comes from walking the book. Nothing is
  priced off the touch for a size the touch cannot fill.
- **Fee ladders.** Tiered maker and taker rates resolved from the desk's own
  trailing thirty day volume, with venue token discounts and a funding check
  that refuses a discount the desk cannot pay for.
- **Inventory bands.** A floor that refuses a leg and a ceiling that prices one,
  with the rebalancing transfer amortised across the plans that caused it.
- **Exposure caps.** Two that trim a plan and one that stops it, plus per asset
  and per venue concentration limits.
- **Attribution.** Expected against realised, split into price drift, fee drift,
  shortfall and leg risk, because each of those has a different fix.
- **A decision ledger.** Everything the scanner decided, including the pairs it
  screened out and the venues it skipped, so a quiet afternoon can be told apart
  from a misconfigured one.
- **Fifteen self checks.** Layering, wiring, SQL, indexes, migrations, naming,
  the rule book, the errors, the packaging, the README, the changelog and the
  leftover markers, all run in CI and all runnable from `./check.sh`.
