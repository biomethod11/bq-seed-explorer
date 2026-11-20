// Reproduce BingoSync's native Ocarina of Time Beta Quest board for one seed.
// The generator and base are vendored verbatim under data/sources; this wrapper
// only supplies Node's module context and converts its 1-indexed board to JSON.
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const seed = process.argv[2];
if (!/^\d{1,6}$/.test(seed) || Number(seed) < 1 || Number(seed) > 999999) {
  throw new Error("seed must be an integer from 1 through 999999");
}

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
const oneIndexed = context.bingoGenerator(context.bingoList, { seed });
process.stdout.write(JSON.stringify(oneIndexed.slice(1)));
