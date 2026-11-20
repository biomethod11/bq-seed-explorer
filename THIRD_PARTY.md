# Third-party work

* **Beta Quest** by mzxrules, https://github.com/mzxrules/Beta-Quest (MIT, see
  `LICENSES/Beta-Quest.txt`). The model's entrance shuffle reimplements its shuffle.
* **OoT Randomizer**, https://github.com/OoTRandomizer/OoT-Randomizer (MIT, see
  `LICENSES/OoT-Randomizer.txt`). The world graph and `model/data/sources/ootr/LogicHelpers.json`
  are derived from its logic files.
* **BingoSync**, https://github.com/kbuzsaki/bingosync. The page runs its Ocarina of Time
  Beta Quest generator and the `srl_generator_v5_blackout` base so that boards match
  bingosync.com. Its repository states no licence, so they are not copied here:
  `build_site.py` downloads them from commit `245673501ad6` and checks their
  SHA-256.
* **Pyodide**, https://pyodide.org (MPL-2.0), installed from npm by `npm install` and
  served with the site.
