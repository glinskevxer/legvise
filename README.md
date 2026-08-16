# legvise

Cross-venue arbitrage scanning for a desk that keeps inventory on every venue it
trades. Books, fee ladders and balances go in; priced and sized plans come out.
Nothing here talks to an exchange and nothing here sends an order.

## What it is for

The desk is **prefunded**. There is BTC and USD sitting on Kraken, and BTC and
USD sitting on OKX, and when the two books cross the desk buys on one and sells
on the other against balances that are already there. No transfer happens at
trade time. Somebody moves the inventory back later, on a slower clock, and the
cost of doing that is charged against the plans that caused the imbalance.

That single fact drives most of the design. A leg is limited by the inventory on
its own venue, the rebalancing cost is amortised rather than paid up front, and
a plan that pushes an asset over its ceiling is allowed but priced.

## The number it produces

Every plan carries the same decomposition, and it is checked rather than assumed:

    net = gross - fees - slippage - rebalance

`gross` is touch to touch, which is the optimistic number a naive scanner stops
at. `slippage` is what sweeping the book for the actual size costs against that
touch. `fees` crosses two venue fee ladders, each resolved from the desk's own
trailing thirty day volume. `rebalance` is this plan's share of the transfer
that will put the inventory back.

A plan that clears the desk's minimum edge after all four is worth looking at.
A plan that clears it after only the first is the reason most crypto arbitrage
backtests do not survive contact with a venue.

## Two kinds of opportunity

**Cross venue.** Buy the base on one venue, sell it on another. Two legs, two
fee schedules, and a pairing window: two books that are each fresh can still be
four hundred milliseconds apart, and pricing a spread across that gap prices
something that never existed.

**Triangular.** USD to BTC to ETH and back to USD, all on one venue. No transfer
story and no pairing problem, but three hops means three taker fees, which is
about forty eight basis points on a loop that screened at four.

## Getting started

```
python -m pip install -e ".[dev]" -c constraints.txt
legvise --help
```

Set up two venues and the market they share:

```
legvise venue add kraken Kraken --staleness-ms 750 --depth-bps 35 --cap 250000
legvise venue add okx OKX --staleness-ms 400 --depth-bps 20 --cap 500000
legvise instrument add kraken BTC-USD --tick 0.01 --lot 0.0001 \
    --min-notional 10 --max-notional 500000
legvise instrument add okx BTC-USD --tick 0.1 --lot 0.00001 \
    --min-notional 10 --max-notional 500000
```

Load the fee ladders and the desk's trailing volume:

```
legvise fee set-ladder kraken 0:10:16 1000000:6:10 25000000:0:6
legvise fee record-volume kraken 2000000
legvise fee rate kraken
legvise fee funding kraken 50000 --fee-asset OKB --fee-asset-price 50
```

Record what the desk is holding and the bands it wants to stay inside:

```
legvise inventory set-balance kraken BTC 5
legvise inventory set-band kraken BTC --floor 1 --target 5 --ceiling 9
legvise inventory show
legvise inventory room kraken BTC
legvise inventory concentration --mark BTC:100000 --mark USD:1
legvise inventory reconcile --holds kraken:BTC:5 --tolerance BTC:0.0001
```

Declare how inventory moves back, and which venues will use each network:

```
legvise network add USDT TRX --fee 1 --min-withdraw 10 \
    --confirmations 20 --block-minutes 0.05
legvise network support kraken USDT TRX
legvise network routes USDT kraken okx
```

Feed in books and scan:

```
legvise book load kraken BTC-USD --bid 99.00:2 --ask 100.00:1
legvise book touch BTC-USD
legvise book imbalance kraken BTC-USD
legvise scan run --min-edge-bps 3 --size 0.5
legvise plan list S20250801.0000
legvise plan rank S20250801.0000
```

## Settings

Eleven options on a scheduled `scan run` is a configuration file written badly.
Put the numbers in a file instead and pass it once:

```
legvise --config legvise.toml config show
legvise config defaults
legvise config check legvise.toml
```

```toml
[scan]
min_edge_bps = "4"
window_ms = 400
size = "0.5"
```

A flag still wins, for that run only, so trying a wider floor for one scan does
not mean editing the desk's settings and remembering to put them back. The
`from` column in `config show` says which of the three levels decided each
number, because a value of 2 that somebody set and a value of 2 nobody ever
touched look identical otherwise. A key the tool does not recognise is refused
rather than ignored, which is the difference between a typo you find now and a
desk that traded on the default for a month.

## Looking after the file

```
legvise db status
legvise db tables
legvise db applied
legvise db prune --keep-days 30
legvise db verify
legvise db vacuum
```

`book_level` is the table that grows without bound. `legvise db prune` takes the
old snapshots out and `legvise db vacuum` gives the space back. Pruning keeps
two things whatever their age: the newest snapshot of every market, because
dropping it retires the market without saying so, and any session with a fill
against it, because that pair is the record of a trade.

`legvise db verify` reads the whole book back and re-derives what it can. It
cannot fail on a file this tool wrote and nothing else touched, which is the
point of running it after a restore.

## Is anything missing

```
legvise report desk
```

One command, and a list of what is not set up. A scan that silently uses four
of five venues looks exactly like one that used all five.

## Reading what happened

```
legvise report session S20250801.0000
legvise scan refusals
legvise report inventory
```

The decision ledger holds what never became a plan at all:

```
legvise audit stages S20250801.0000
legvise audit session S20250801.0000 --stage screened
legvise audit shape S20250801.0000
legvise audit clauses S20250801.0000
```

The refusal counts are the useful half. Three EDGE.01 refusals means the market
was quiet; three CAP.01 refusals means the desk was at its own limit and the
market had nothing to do with it, and a plan count cannot tell those apart.

Once orders have gone out, record the fills and ask what the plan actually made:

```
legvise fill record S20250801.0000/P000 0 tr-8812 --price 100.02 --size 0.5
legvise fill outcome S20250801.0000/P000
legvise fill attribution S20250801.0000/P000
legvise report edge
```

Attribution splits the missing edge into reasons that have different fixes:
price drift is a latency problem, fee drift means the nightly volume job did not
run, a shortfall is a sizing problem, and one leg filling alone is an incident
rather than a cost.

## Looking for loops

```
legvise loop screen kraken --start USD
legvise loop graph kraken
legvise loop run --start USD --amount 10000 --min-edge-bps 3
```

`screen` is a screen. The numbers it prints ignore depth and every fee.

## Design

- **Exact decimals everywhere.** Floats are refused at the door. A fee owed
  rounds up and a rebate earned rounds down, which are opposite directions on
  purpose.
- **The clock is a dependency.** Nothing calls `datetime.now`; the scanner is
  handed a clock, and tests hand it one that does not move.
- **Every refusal quotes a clause.** The rule book is in `docs/rules.md`,
  generated from the code that enforces it, and the clause is stored on the plan
  so refusals can be counted later.
- **The layer map is generated too.** `docs/architecture.md` is built from the
  imports the modules actually have, not from what anybody meant.
- **Layers point downwards.** `model` knows nothing about `store`, `market`
  knows nothing about `cli`, and a check in `legvise.tools` keeps it that way.
- **The book of record is one SQLite file.** An operator can copy it to a laptop
  and open it.

## Checks

Beyond lint, types and tests, the repository checks itself:

| check | what it refuses |
| --- | --- |
| `check_layers` | an import that points up the layers |
| `check_wiring` | a module the command tree cannot reach |
| `check_tests` | a module with no test module, or the reverse |
| `check_cli` | a group that is not registered, or a command with no help |
| `check_help` | help that exists and says nothing |
| `check_sql` | `SELECT *`, an interpolated value, or SQL outside the store |
| `check_indexes` | a foreign key with no index on the child side |
| `check_migrations` | a migration edited after it shipped |
| `check_markers` | a leftover TODO, or a test that is quietly skipped |
| `check_naming` | a test name that is a label rather than a sentence |
| `check_rules` | a clause nobody raises, or a refusal with no clause |
| `check_errors` | an exception the package does not own |
| `check_package` | metadata that disagrees with the code |
| `check_changelog` | a changelog that lags the version the code reports |
| `check_readme` | this file describing a command that does not exist |

`docs/commands.md` is the whole tree on one page, generated the same way.

Run everything the way CI does:

```
./check.sh
```

## Layout

    src/legvise/model      the records, and what they refuse to be
    src/legvise/store      SQLite, migrations, one repository per aggregate
    src/legvise/market     depth walking, staleness, tick and lot conformance
    src/legvise/fees       fee ladders and what one leg costs
    src/legvise/risk       inventory bands and exposure caps
    src/legvise/routing    transfer routes and amortised rebalancing cost
    src/legvise/scan       the cross venue and triangular passes
    src/legvise/ledger     expected against realised
    src/legvise/report     session and edge reports, CSV and JSON
    src/legvise/cli        the command tree
    src/legvise/tools      the checks above, and the generated documents
