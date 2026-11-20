// BingoSync's native Ocarina of Time Beta Quest board, made in the browser.
//
// The generator and its base are the files vendored verbatim under data/sources, the
// same two that data/sources/run_bingosync_betaquest.js runs in Node. This only gives
// them what Node gave them: a `require` for the base and a `module` to export through.
//
// The base is an old seedrandom build that installs `seedrandom` and replaces `random`
// on the `Math` it is handed. It gets a private object whose prototype is the real
// Math, so the page's own Math.random is never replaced.
//
// The seed goes in as a decimal string, as Node's runner passes it: seedrandom mixes a
// number and its string differently, so 274451 and "274451" make different boards.

export const GENERATOR_FILE = "ocarina_of_time_beta_quest_generator.js";
export const BASE_FILE = "generators/generator_bases/srl_generator_v5_blackout.js";

export function makeBoardGenerator(generatorSource, baseSource) {
  const sandboxMath = Object.create(Math);
  const loadBase = new Function(
    "Math",
    "var bingoGenerator, module = { exports: {} };\n" + baseSource + "\nreturn module.exports;",
  );
  const base = loadBase(sandboxMath);
  const loadGenerator = new Function(
    "Math", "require",
    "var bingoGenerator, bingoList;\n" + generatorSource + "\nreturn { bingoGenerator, bingoList };",
  );
  const { bingoGenerator, bingoList } = loadGenerator(sandboxMath, (path) => {
    if (!path.endsWith(BASE_FILE)) throw new Error(`unexpected require: ${path}`);
    return base;
  });

  return function board(seed) {
    const text = String(seed).trim();
    if (!/^\d{1,6}$/.test(text) || Number(text) < 1 || Number(text) > 999999) {
      throw new Error("seed must be an integer from 1 through 999999");
    }
    const oneIndexed = bingoGenerator(bingoList, { seed: String(Number(text)) });
    // The JSON round trip is what Node's runner does before Python reads the board.
    return JSON.parse(JSON.stringify(oneIndexed.slice(1)));
  };
}

export async function loadBoardGenerator(sourcesUrl) {
  const base = sourcesUrl.endsWith("/") ? sourcesUrl : sourcesUrl + "/";
  const [generatorSource, baseSource] = await Promise.all(
    [GENERATOR_FILE, BASE_FILE].map(async (file) => {
      const response = await fetch(base + file);
      if (!response.ok) throw new Error(`could not load ${file}: ${response.status}`);
      return response.text();
    }),
  );
  return makeBoardGenerator(generatorSource, baseSource);
}
