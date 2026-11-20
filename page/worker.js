// Runs the betaquest package under Pyodide, off the page's main thread.
//
// Messages in:  { id, call: "overview" | "square", args: {...} }
// Messages out: { id, ok: true, result } or { id, ok: false, error }, and
//               { status: "..." } while Python loads.
// Calls run one at a time, in the order they arrive; each is a synchronous Python call.
import { loadBoardGenerator } from "./board.js";

const here = (path) => new URL(path, import.meta.url).href;
let ready = null;

async function start() {
  self.postMessage({ status: "Loading Python (the first visit downloads about 13 MB)…" });
  // build.json names the bundle's hash; fetching the bundle by it means a browser never
  // runs a cached model older than the page it was served with.
  // Pyodide sits under its version (pyodide/314.0.7/), so a host can cache it for good.
  const response = await fetch(here("./build.json"), { cache: "no-cache" });
  if (!response.ok) throw new Error(`could not load build.json: ${response.status}`);
  const info = await response.json();
  const pyodideUrl = here(`./pyodide/${info.pyodide_version}/`);
  const { loadPyodide } = await import(`${pyodideUrl}pyodide.mjs`);
  const [py, board, bundle] = await Promise.all([
    loadPyodide({ indexURL: pyodideUrl }),
    loadBoardGenerator(here("./sources/")),
    fetch(here(`./py/betaquest.zip?v=${info.bundle}`)).then((response) => {
      if (!response.ok) throw new Error(`could not load the model: ${response.status}`);
      return response.arrayBuffer();
    }),
  ]);
  self.postMessage({ status: "Loading the model…" });
  py.unpackArchive(bundle, "zip", { extractDir: "/bq" });
  py.globals.set("board_json", (seed) => JSON.stringify(board(seed)));
  py.globals.set("model_version", info.profile_version);
  // The bundle is stripped of comments and prose, which changes its own fingerprint; the
  // build checked it answers as the full model does, so it carries that model's version.
  await py.runPythonAsync(`
import json, sys
sys.path.insert(0, "/bq")
from betaquest import web_api
web_api.use_board_source(lambda seed: json.loads(board_json(seed)))
web_api.pin_model_version(model_version)
def page_call(name, args_json):
    if name not in ("overview", "square"):
        raise ValueError(f"unknown call {name}")
    return json.dumps(getattr(web_api, name)(**json.loads(args_json)))
`);
  return py.globals.get("page_call");
}

self.onmessage = async (event) => {
  const { id, call, args } = event.data;
  try {
    ready ||= start();
    const pageCall = await ready;
    const result = JSON.parse(pageCall(call, JSON.stringify(args)));
    self.postMessage({ id, ok: true, result });
  } catch (error) {
    // A Python error's message ends with its last line, which says what went wrong.
    const text = String(error && error.message ? error.message : error).trim().split("\n");
    self.postMessage({ id, ok: false, error: text[text.length - 1] });
  }
};
