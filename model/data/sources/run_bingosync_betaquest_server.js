// Persistent variant of run_bingosync_betaquest.js: serves repeated board
// requests over stdin/stdout instead of exiting after one, so a scan doesn't
// pay Node's interpreter startup cost (tens of ms) on every single seed.
//
// Protocol: one seed (decimal digits) per stdin line -> one JSON line on
// stdout, either the 25-goal board array or {"error": "message"}. A malformed
// or out-of-range seed reports an error line and keeps the server running,
// rather than throwing and exiting -- one bad request must not kill the rest
// of a scan.
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const readline = require("readline");

const sourceRoot = __dirname;
const generatorSource = fs.readFileSync(
  path.join(sourceRoot, "ocarina_of_time_beta_quest_generator.js"), "utf8"
);
const context = {
  require: (modulePath) => require(path.resolve(sourceRoot, modulePath)),
};
vm.runInNewContext(generatorSource, context, {
  filename: "ocarina_of_time_beta_quest_generator.js",
});

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on("line", (line) => {
  const seed = line.trim();
  try {
    if (!/^\d{1,6}$/.test(seed) || Number(seed) < 1 || Number(seed) > 999999) {
      throw new Error("seed must be an integer from 1 through 999999");
    }
    const oneIndexed = context.bingoGenerator(context.bingoList, { seed });
    process.stdout.write(JSON.stringify(oneIndexed.slice(1)) + "\n");
  } catch (err) {
    const message = (err && err.message) || String(err);
    process.stdout.write(JSON.stringify({ error: message }) + "\n");
  }
});

rl.on("close", () => {
  process.exit(0);
});
