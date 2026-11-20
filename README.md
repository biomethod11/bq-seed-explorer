# Beta Quest Seed Explorer

The source of **https://bq-seed-explorer.pages.dev**, a page for looking up an Ocarina of Time
[Beta Quest](https://github.com/mzxrules/Beta-Quest) bingo seed: its
[BingoSync](https://bingosync.com) board, how hard each square is, which squares need
glitches and which glitch opens each one, and a route from a new file to every place a
square needs.

Everything runs in the visitor's browser. The page makes the board with BingoSync's own
generator, predicts Beta Quest's shuffled doors from the seed's file name, and solves the
seed with a reachability model written in Python, run by [Pyodide](https://pyodide.org)
in a Web Worker. There is no server.

## What is here

| Path | What it is |
|---|---|
| `page/` | The page: `index.html`, `styles.css`, `app.js`, `worker.js` (runs the model), `board.js` (BingoSync's board in the browser), `_headers` (cache rules for Cloudflare Pages) |
| `page/build_info.json` | The model version, the Pyodide version and the effort quantiles the page uses to place a seed's workload |
| `model/betaquest/` | The model, exactly as the site runs it. Comments and docstrings are stripped from this copy, so it is not the easiest code to read |
| `model/data/` | The world graph, the goal mapping and the other data the model reads |
| `build_site.py` | Assembles `site/`, the folder the host serves |

## Running it locally

Needs Python 3.11 or newer and Node.js.

```
npm install                 # Pyodide, pinned in package.json
python build_site.py        # downloads BingoSync's generator files, checks them, writes site/
python -m http.server 8000 --directory site
```

Then open http://localhost:8000.

## What the numbers mean

* **Skill floor** is the lowest of three glitch tiers (glitchless, common, hard) at which
  the model finds a route to every square.
* **Workload** and each square's difficulty are model estimates. They have not been
  checked against timed games, so read them as rough rankings, not minutes.
* A **route** is the fewest loading zones the model finds from where a new file starts,
  not the fastest way. Each step reads what the seed lets you collect by the end, apart
  from what the place itself gives.

## Licence

The code here is under the MIT licence ([LICENSE](LICENSE)). The third-party work it
builds on keeps its own licence: see [THIRD_PARTY.md](THIRD_PARTY.md).
