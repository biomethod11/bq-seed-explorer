from __future__ import annotations
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from . import profile as _profile_module
from .bingosync import analyze_seed, canonical_seed, filename_for_seed, native_board
from .discovery import seed_world_for_filename
from .logic import solve
from .profile import PROFILE_VERSION, TIER_LABELS, TIER_ORDER, TIER_SETTINGS, SeedProfile, _tier_result, profile_seed
from .region_names import display_name
from .world import World
SETTING_LABELS: dict[str, str] = {'glitch_oi': 'Ocarina Items', 'glitch_qpa': 'QPA (burn webs and torches with a stick or sword)', 'logic_dc_jump': "Dodongo's Cavern jump from the climb to the far bridge (adult)", 'logic_zora_with_cucco': "Zora's River waterfall skip with a cucco (child)", 'logic_water_north_basement': 'Water Temple north basement without the Longshot', 'logic_water_north_basement_ledge_jump': 'Water Temple north basement ledge jump', 'logic_water_bk_jump_dive': 'Water Temple boss key jump and dive', 'logic_water_central_bow': 'Water Temple central pillar switch with the Bow', 'logic_water_river_gs': 'Water Temple river Skulltula without the Longshot', 'logic_water_falling_platform_gs_hookshot': 'Water Temple falling-platform Skulltula with the Hookshot', 'glitch_equip_swap': 'Equip Swap', 'glitch_megaflip': 'Megaflip', 'glitch_vine_clip': 'Vine Clip', 'glitch_superslide': 'Superslide', 'bq_water_no_zora_tunic': 'Water Temple without the Zora Tunic', 'glitch_dc_switch_trick': "Dodongo's Cavern staircase switch with Bombchus or the Bracelet", 'logic_spirit_child_bombchu': 'Spirit Temple child bridge switch with a Bombchu', 'glitch_light_trial_rock_skip': 'Light Trial entrance rock skip with explosives', 'glitch_suns_song_boss_door': "Sun's Song by Ocarina Items in a boss room (opens the boss door)", 'glitch_llr_tower_clip': 'Lon Lon Ranch tower clip (adult)', 'glitch_lh_tree_isg_hookshot': 'Lake Hylia tree Skulltula with the Hookshot under ISG', 'glitch_zd_tunnel_hookshot': "Zora's Domain frozen tunnel with the Hookshot (adult)", 'glitch_child_golden_scale': 'Golden Scale fishing prize as child', 'glitch_dmc_fairy_child': 'Crater Great Fairy boulder with no items (child)', 'glitch_hba_without_bow': 'Horseback archery without the Bow', 'glitch_kak_gallery_void': 'Kakariko gallery void-out entry (child)', 'logic_trail_gs_lower': 'Death Mountain Trail lower red-rock Skulltula without the Hammer', 'logic_trail_gs_upper': 'Death Mountain Trail upper red-rock Skulltula without the Hammer', 'logic_wasteland_crossing': 'Backwalking over the Wasteland quicksand', 'glitch_kak_door_clip_child': 'Kakariko Potion Shop back door and Bazaar door clips (child)', 'glitch_gtg_door_clip_child': 'Gerudo Training Ground door clip (child)', 'glitch_door_of_time_skip': 'Door of Time Skip', 'glitch_dc_mouth_sword_climb': "Dodongo's Cavern sword-only climb to the Bomb Bag chest", 'glitch_rba': 'Reverse Bottle Adventure (RBA)', 'glitch_bomb_hover': 'Bomb Hover', 'glitch_zero_hp_arrival': 'Reaching a loading zone at 0 HP', 'glitch_forest_ledge_precise': 'Forest Temple outside ledge by precise movement', 'glitch_jabu_adult_clip': 'Jabu-Jabu clip as adult', 'glitch_zd_tunnel_adult': "Zora's Domain frozen tunnel with no items (adult)", 'glitch_damage_flag_corruption': 'Damage flag corruption', 'glitch_gc_dmc_child': 'Goron City statue into the crater (child)', 'glitch_rft_js_clip_child': "Royal Family's Tomb jumpslash clip (child)", 'glitch_dmc_fairy_adult': 'Crater Great Fairy boulder by HESS, Megaflip or Hover Boots (adult)', 'glitch_kak_gallery_clip': 'Kakariko gallery clip with a bomb (child)', 'glitch_child_water_temple': 'Water Temple from Lake Hylia (child)', 'glitch_gv_tent_child_clip': "Gerudo Valley carpenters' tent clip (child)", 'glitch_gv_octorok_megasidehop_child': 'Gerudo Valley silver rock megasidehop (child)', 'glitch_llr_tower_oob_death': 'Lon Lon Ranch tower out-of-bounds death', 'glitch_spirit_qpa_weirdshot': 'Spirit Temple QPA weirdshot', 'glitch_minimum_item_routes': 'The minimum-item routes (not yet rated; placed at hard)'}
SETTING_PREREQUISITES: dict[str, tuple[str, ...]] = {'glitch_suns_song_boss_door': ('glitch_oi',)}
POCKET_ALWAYS = frozenset({'Child Spawn', 'Adult Spawn', 'Root Exits', 'Sky Temple'})
HEAVIEST = 5
UNROUTED_SHOWN = 8
Unreached = Callable[[Mapping[str, Any]], set[str]]

@dataclass(frozen=True)
class SquareReason:
    square: str
    tier: str
    opened_by: list[str] = field(default_factory=list)
    needs_all: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class HeavySquare:
    square: str
    difficulty: float
    cost: float | None
    factors: list[str]
    after_sky_chest: bool = False

@dataclass(frozen=True)
class SeedReport:
    seed: int
    filename: str
    card_seed: int
    profile_version: str
    access_tier: str
    access_tier_label: str
    effort: float | None
    effort_band: str | None
    effort_percentile: float | None
    tier_squares: dict[str, list[SquareReason]]
    attributed: bool
    heaviest: list[HeavySquare]
    unrouted: list[str]
    impossible_causes: dict[str, str]
    pocket: list[str]
    stored: dict[str, Any] | None
    notes: list[str]

    @property
    def proven(self) -> bool:
        return self.access_tier in TIER_ORDER

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def setting_label(name: str) -> str:
    return SETTING_LABELS.get(name, name)

def attribute_squares(profile: SeedProfile, unreached: Unreached) -> dict[str, list[SquareReason]]:
    reasons: dict[str, list[SquareReason]] = {}
    for index, tier in enumerate(TIER_ORDER[1:], start=1):
        squares = list(profile.tier_unlock_goals.get(tier) or [])
        if not squares:
            continue
        below = TIER_SETTINGS[TIER_ORDER[index - 1]]
        full = TIER_SETTINGS[tier]
        added = [name for name in full if name not in below]
        opened: dict[str, list[str]] = {square: [] for square in squares}
        for name in added:
            with_prerequisites = {needed: full[needed] for needed in SETTING_PREREQUISITES.get(name, ()) if needed in full}
            still = unreached({**below, **with_prerequisites, name: full[name]})
            for square in squares:
                if square not in still:
                    opened[square].append(name)
        needed: dict[str, list[str]] = {}
        if any((not names for names in opened.values())):
            for name in added:
                still = unreached({key: value for key, value in full.items() if key != name})
                for square in squares:
                    if not opened[square] and square in still:
                        needed.setdefault(square, []).append(name)
        reasons[tier] = [SquareReason(square, tier, opened[square], needed.get(square, [])) for square in squares]
    return reasons

def _impossible_causes(seed: int, world: World, board: list[dict] | None=None) -> dict[str, str]:
    from .relaxed import NOTABLE_MISSING, Relaxer, item_aware_free_world, relax_world
    from .rules import DEFAULT_SETTINGS, RuleEvaluator
    hard = TIER_SETTINGS['hard_glitches']
    filename = filename_for_seed(seed)

    def unrouted(relaxed: World) -> set[str]:
        return set(_tier_result('hard_glitches', analyze_seed(seed, world=relaxed, settings=hard, board=board)).unreached_goal_names)
    relaxed, missing = item_aware_free_world(world, filename, hard, strict_age=True)
    failing = unrouted(relaxed)
    evaluator = RuleEvaluator(items=world.item_names, events=world.event_names, settings={**DEFAULT_SETTINGS, **hard})
    any_age = unrouted(relax_world(world, Relaxer(evaluator, frozenset())))
    by_age = unrouted(relax_world(world, Relaxer(evaluator, frozenset(), strict_age=True)))
    never = [name for name in NOTABLE_MISSING if name in missing]
    causes: dict[str, str] = {}
    for square in sorted(failing):
        if square in any_age:
            causes[square] = 'no door on this seed reaches it'
        elif square in by_age:
            causes[square] = "Link can't get there at the age it needs"
        else:
            causes[square] = 'it needs something you can never get on this seed' + (f" ({', '.join(never)})" if never else '')
    return causes

def _pocket(seed: int, world: World) -> list[str]:
    reached = solve(seed_world_for_filename(filename_for_seed(seed), world), settings=TIER_SETTINGS['hard_glitches']).reached_regions
    rooms = sorted((region for region in reached if region not in POCKET_ALWAYS and region != 'Root' and (not world.is_state_copy(region))))
    return [display_name(region) for region in rooms]

def effort_percentile(database: Path, effort: float, model_version: str=PROFILE_VERSION) -> float | None:
    below = total = 0
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        for rank, tier in enumerate(TIER_ORDER):
            base = rank * 1000.0
            below += connection.execute('SELECT COUNT(*) FROM seed_results WHERE model_version = ? AND access_tier = ?\n                   AND sort_score >= ? AND sort_score < ?', (model_version, tier, base, base + effort)).fetchone()[0]
            total += connection.execute('SELECT COUNT(*) FROM seed_results WHERE model_version = ? AND access_tier = ?', (model_version, tier)).fetchone()[0]
    return None if total == 0 else below / total

def _compare_stored(row: Mapping[str, Any] | None, profile: SeedProfile) -> dict[str, Any]:
    if row is None:
        return {'found': False, 'current': False, 'matches': False, 'differences': []}
    current = row.get('model_version') == PROFILE_VERSION
    differences: list[str] = []
    if row.get('access_tier') != profile.access_tier:
        differences.append(f"tier {row.get('access_tier')} stored, {profile.access_tier} live")
    stored_effort, live_effort = (row.get('effort'), profile.effort)
    if (stored_effort is None) != (live_effort is None) or (stored_effort is not None and abs(float(stored_effort) - float(live_effort)) > 0.0005):
        differences.append(f'effort {stored_effort} stored, {live_effort} live')
    if int(row.get('residual') or 0) != profile.residual:
        differences.append(f"residual {row.get('residual')} stored, {profile.residual} live")
    return {'found': True, 'current': current, 'model_version': row.get('model_version'), 'matches': current and (not differences), 'differences': differences}

@contextmanager
def _profile_board(board: list[dict]):
    original = _profile_module.native_board
    _profile_module.native_board = lambda seed, node=None: [dict(goal) for goal in board]
    try:
        yield
    finally:
        _profile_module.native_board = original

class SeedSolves:

    def __init__(self, seed: int | str, world: World | None=None, card: int | str | None=None) -> None:
        self.seed = canonical_seed(seed)
        self.card = self.seed if card is None else canonical_seed(card)
        self.world = world or World.load()
        self.filename = filename_for_seed(self.seed)
        self.board = native_board(self.card)
        if self.card == self.seed:
            self.profile = profile_seed(self.seed, world=self.world, exhaustive=True)
        else:
            with _profile_board(self.board):
                self.profile = profile_seed(self.seed, world=self.world, exhaustive=True)
        self._shared = seed_world_for_filename(self.filename, self.world)
        self._chest: list = []
        self._analyses: dict[str, Any] = {}
        self._attributed: dict[str, list[SquareReason]] | None = None

    def _chest_world(self):
        if not self._chest:
            self._chest.append(seed_world_for_filename(self.filename, self.world, sacred_chest_opened=True))
        return self._chest[0]

    def solve(self, settings: Mapping[str, Any]):
        return analyze_seed(self.seed, world=self.world, settings=dict(settings), seed_world=self._shared, chest_seed_world=self._chest_world, board=self.board)

    def analysis(self, tier: str):
        if tier not in self._analyses:
            self._analyses[tier] = self.solve(TIER_SETTINGS[tier])
        return self._analyses[tier]

    def unreached(self, settings: Mapping[str, Any]) -> set[str]:
        return set(_tier_result('overlay', self.solve(settings)).unreached_goal_names)

    def tier_squares(self, attribute: bool=True) -> dict[str, list[SquareReason]]:
        if attribute:
            if self._attributed is None:
                self._attributed = attribute_squares(self.profile, self.unreached)
            return self._attributed
        return {tier: [SquareReason(square, tier) for square in squares] for tier, squares in self.profile.tier_unlock_goals.items() if squares}

def explain_seed(seed: int | str, world: World | None=None, database: Path | None=None, attribute: bool=True, heaviest: int=HEAVIEST, solves: SeedSolves | None=None, card: int | str | None=None) -> SeedReport:
    solves = solves or SeedSolves(seed, world, card=card)
    seed_number, world, filename, profile = (solves.seed, solves.world, solves.filename, solves.profile)
    tier_squares = solves.tier_squares(attribute)
    heavy: list[HeavySquare] = []
    unrouted: list[str] = []
    causes: dict[str, str] = {}
    pocket: list[str] = []
    if profile.proven:
        scored = solves.analysis(profile.access_tier)
        ranked = sorted(zip(scored.score.goals, scored.goal_difficulty), key=lambda pair: (-pair[1].difficulty_score, pair[0].name))
        heavy = [HeavySquare(goal.name, round(estimate.difficulty_score, 1), None if goal.cost is None else round(goal.cost, 1), list(estimate.factors), goal.after_sky_chest) for goal, estimate in ranked[:heaviest]]
    else:
        unrouted = list(profile.tiers['hard_glitches'].unreached_goal_names)
        if profile.access_tier == 'impossible':
            causes = _impossible_causes(seed_number, world, solves.board)
        elif profile.access_tier == 'trapped':
            pocket = _pocket(seed_number, world)
    stored = percentile = None
    if database is not None and Path(database).exists():
        from .scanner import SeedDatabase
        if solves.card == seed_number:
            stored = _compare_stored(SeedDatabase(Path(database)).lookup(seed_number), profile)
        if profile.effort is not None:
            percentile = effort_percentile(Path(database), profile.effort)
    return SeedReport(seed=seed_number, filename=filename, card_seed=solves.card, profile_version=PROFILE_VERSION, access_tier=profile.access_tier, access_tier_label=profile.access_tier_label, effort=profile.effort, effort_band=profile.effort_band, effort_percentile=percentile, tier_squares=tier_squares, attributed=attribute, heaviest=heavy, unrouted=unrouted, impossible_causes=causes, pocket=pocket, stored=stored, notes=[note for note in profile.notes if not note.startswith('tiers solved')])

def opener_text(reason: SquareReason) -> str:
    tier = TIER_LABELS[reason.tier].lower()
    if reason.opened_by:
        return ', or '.join((setting_label(name) for name in reason.opened_by))
    implied = {needed for name in reason.needs_all for needed in SETTING_PREREQUISITES.get(name, ())}
    needs = [name for name in reason.needs_all if name not in implied]
    if len(needs) == 1:
        return f'{setting_label(needs[0])}, with another of the {tier}'
    if needs:
        return ' and '.join((setting_label(name) for name in needs)) + ', together'
    return f'a combination of {tier}'

def format_report(report: SeedReport) -> str:
    lines = [f'Seed {report.seed} (filename {report.filename}), model {report.profile_version}']
    if report.card_seed != report.seed:
        lines.append(f"Card: BingoSync seed {report.card_seed}, scored on seed {report.seed}'s doors (not compared with the database, which stores each seed with its own card).")
    stored = report.stored
    if stored is not None:
        if not stored['found']:
            lines.append('Database: no stored row for this seed.')
        elif not stored['current']:
            lines.append(f"Database: the stored row is from an older model ({stored['model_version']}).")
        elif stored['matches']:
            lines.append('Database: the stored row matches this live solve.')
        else:
            lines.append('Database: the stored row DIFFERS: ' + '; '.join(stored['differences']))
    lines.append('')
    lines.append(f'Skill floor: {report.access_tier_label}')
    if report.proven:
        if not report.tier_squares:
            lines.append('  Every square has a glitchless route.')
        else:
            lines.append('  Every other square has a glitchless route. These need more' + (', grouped by what opens them:' if report.attributed else ':'))
            for tier in reversed(TIER_ORDER[1:]):
                reasons = report.tier_squares.get(tier, [])
                if not reasons:
                    continue
                lines.append(f'  {TIER_LABELS[tier]}')
                if not report.attributed:
                    lines.extend((f'  * {reason.square}' for reason in reasons))
                    continue
                groups: dict[str, list[str]] = {}
                for reason in reasons:
                    groups.setdefault(opener_text(reason), []).append(reason.square)
                for opener, squares in groups.items():
                    lines.append(f"  * {opener}: {'; '.join(squares)}")
    elif report.access_tier == 'trapped':
        lines.append('  Not one square is reachable: nothing in the starting pocket opens a way out.')
        if report.pocket:
            lines.append('  Link is stuck in: ' + '; '.join(report.pocket))
    elif report.access_tier == 'impossible':
        lines.append(f'  {len(report.impossible_causes)} square(s) have no route even with every rule free:')
        for square, cause in report.impossible_causes.items():
            lines.append(f'  * {square}: {cause}')
    else:
        lines.append(f'  The solver found no route for {len(report.unrouted)} square(s) at any tier. That is not proof they are impossible:')
        for square in report.unrouted[:UNROUTED_SHOWN]:
            lines.append(f'  * {square}')
        if len(report.unrouted) > UNROUTED_SHOWN:
            lines.append(f'  * and {len(report.unrouted) - UNROUTED_SHOWN} more')
    lines.append('')
    if report.effort is not None:
        where = ''
        if report.effort_percentile is not None:
            share = 100 * report.effort_percentile
            shown = f'{share:.1f}' if share < 1 or share > 99 else f'{share:.0f}'
            where = f'; heavier than {shown}% of routable seeds'
        lines.append(f'Workload: {report.effort_band} (effort {report.effort:.1f} of 100{where})')
        lines.append('  An uncalibrated model estimate, not minutes. The heaviest squares:')
        for square in report.heaviest:
            detail = '; '.join(square.factors[:2])
            chest = ' (after beating the Sky Temple)' if square.after_sky_chest else ''
            lines.append(f'  * {square.square}{chest}: {square.difficulty:.1f}' + (f' - {detail}' if detail else ''))
    else:
        lines.append('Workload: none, since no tier routes every square.')
    return '\n'.join(lines)
