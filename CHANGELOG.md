# Changelog

Newest first. Every entry says what changed for somebody using the tool, not
what changed in the tree.

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
