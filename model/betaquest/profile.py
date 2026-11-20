from __future__ import annotations
import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence
from .bingosync import MatchedSeedAnalysis, _GENERATOR as _BINGOSYNC_GENERATOR_PATH, _GENERATOR_BASE as _BINGOSYNC_GENERATOR_BASE_PATH, _RUNNER as _BINGOSYNC_RUNNER_PATH, _SERVER_RUNNER as _BINGOSYNC_SERVER_RUNNER_PATH, analyze_seed, canonical_seed, filename_for_seed, native_board
from .board import _GOALS_PATH
from .discovery import seed_world_for_filename
from .difficulty import _CALIBRATION_PATH as _DIFFICULTY_CALIBRATION_PATH, _completion_probability, _quantile
from .relaxed import FARORES_WIND_REGION, NOTABLE_MISSING, UNLIFTABLE_EXIT_RULES, item_aware_free_world
from .rules import DEFAULT_SETTINGS, _HELPERS_PATH
from .shuffle import _DATA_PATH as _ENTRANCES_PATH
from .tiers import COMMON_GLITCHES, GLITCHLESS, HARD_GLITCHES
from .world import World, _GRAPH_PATH
_PROFILE_BASE_VERSION = '3.5-tiered'
_SCORING_INPUTS: tuple[tuple[str, Path], ...] = (('world_graph', _GRAPH_PATH), ('goals', _GOALS_PATH), ('entrances', _ENTRANCES_PATH), ('logic_helpers', _HELPERS_PATH), ('difficulty_calibration', _DIFFICULTY_CALIBRATION_PATH), ('bingosync_generator', _BINGOSYNC_GENERATOR_PATH), ('bingosync_generator_base', _BINGOSYNC_GENERATOR_BASE_PATH), ('bingosync_server_runner', _BINGOSYNC_SERVER_RUNNER_PATH), ('bingosync_runner', _BINGOSYNC_RUNNER_PATH), *((f'python_{module}', Path(__file__).resolve().with_name(f'{module}.py')) for module in ('profile', 'bingosync', 'board', 'difficulty', 'discovery', 'logic', 'rules', 'world', 'shuffle', 'seed', 'filename', 'rng', 'tiers', 'rba', 'minimum_items', 'relaxed')))

@lru_cache(maxsize=1)
def _model_fingerprint() -> str:
    digest = hashlib.sha256()
    for label, path in _SCORING_INPUTS:
        payload = path.read_bytes().replace(b'\r\n', b'\n')
        digest.update(f'{label}:{len(payload)}:'.encode('utf-8'))
        digest.update(payload)
    digest.update(repr(sorted(DEFAULT_SETTINGS.items())).encode('utf-8'))
    digest.update(repr(sorted(((tier, sorted(settings.items())) for tier, settings in TIER_SETTINGS.items()))).encode('utf-8'))
    return digest.hexdigest()[:8]

def _profile_version() -> str:
    return f'{_PROFILE_BASE_VERSION}+{_model_fingerprint()}'
TIER_ORDER = ('glitchless', 'common_glitches', 'hard_glitches')
TIER_SETTINGS: dict[str, dict[str, Any]] = {'glitchless': GLITCHLESS, 'common_glitches': COMMON_GLITCHES, 'hard_glitches': HARD_GLITCHES}
PROFILE_VERSION = _profile_version()
UNPROVEN_MARGINAL_MAX = 2
TIER_LABELS = {'glitchless': 'Glitchless', 'common_glitches': 'Common Glitches', 'hard_glitches': 'Hard Glitches', 'unproven_marginal': 'Unproven (near miss)', 'unproven': 'Unproven', 'impossible': 'Impossible', 'trapped': 'Trapped start'}
UNREACHABLE_TIERS = ('impossible', 'trapped')
ACCESS_ORDER = (*TIER_ORDER, 'unproven_marginal', 'unproven', *UNREACHABLE_TIERS)
DEFAULT_EFFORT_BANDS: tuple[float, float, float, float] = (45.4, 48.11, 50.816, 53.984)
EFFORT_LABELS = ('Light', 'Moderate', 'Heavy', 'Punishing', 'Brutal')
_CALIBRATION_PATH = Path(__file__).resolve().parent.parent / 'data' / 'profile_calibration.json'

@lru_cache(maxsize=1)
def load_effort_bands() -> tuple[float, ...]:
    if not _CALIBRATION_PATH.exists():
        return DEFAULT_EFFORT_BANDS
    try:
        bands = json.loads(_CALIBRATION_PATH.read_text(encoding='utf-8'))['effort_bands']
        cuts = tuple((float(value) for value in bands))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_EFFORT_BANDS
    return cuts if len(cuts) == len(EFFORT_LABELS) - 1 else DEFAULT_EFFORT_BANDS

@dataclass(frozen=True)
class TierResult:
    tier: str
    feasible: bool
    unreached_goals: int
    reached_regions: int
    reached_locations: int
    median_goal_cost: float | None
    maximum_goal_cost: float | None
    partial_makespan: float | None
    full_makespan: float | None
    effort: float | None
    hardest_goal: str | None
    unreached_goal_names: list[str] = field(default_factory=list)
    total_goals: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class SeedProfile:
    seed: int
    profile_version: str
    access_tier: str
    access_tier_label: str
    access_rank: int
    effort: float | None
    effort_band: str | None
    residual: int
    tier_unlocks: dict[str, int]
    tier_unlock_goals: dict[str, list[str]]
    completion_probability: float | None
    tiers: dict[str, TierResult]
    solves_used: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['tiers'] = {name: result.to_dict() for name, result in self.tiers.items()}
        return payload

    @property
    def proven(self) -> bool:
        return self.access_tier in TIER_ORDER

    @property
    def sort_key(self) -> tuple[int, float]:
        if not self.proven:
            return (self.access_rank, float(self.residual))
        return (self.access_rank, float(self.effort if self.effort is not None else 100.0))

def _partial_makespan(costs: Sequence[float], players: int=2) -> float | None:
    if not costs:
        return None
    lanes = [0.0] * max(1, players)
    for cost in sorted(costs, reverse=True):
        lanes[lanes.index(min(lanes))] += cost
    return max(lanes)

def board_effort(goal_scores: Sequence[float], makespan: float | None, unreached: int) -> float | None:
    if unreached > 0 or not goal_scores:
        return None
    mean = statistics.fmean(goal_scores)
    upper_quartile = _quantile(goal_scores, 0.75)
    upper_decile = _quantile(goal_scores, 0.9)
    bottleneck = max(goal_scores)
    workload = 0.0 if makespan is None else 100.0 * (1.0 - math.exp(-float(makespan) / 450.0))
    effort = 0.34 * workload + 0.24 * upper_decile + 0.2 * upper_quartile + 0.14 * mean + 0.08 * bottleneck
    return max(0.0, min(100.0, effort))

def effort_band(effort: float | None, bands: Sequence[float] | None=None) -> str | None:
    if effort is None:
        return None
    for label, cut in zip(EFFORT_LABELS, bands if bands is not None else load_effort_bands()):
        if effort < cut:
            return label
    return EFFORT_LABELS[-1]

def recalibrate_bands(efforts: Sequence[float], divisions: int=5) -> list[float]:
    usable = sorted((e for e in efforts if e is not None))
    if not usable:
        return list(DEFAULT_EFFORT_BANDS)
    return [round(_quantile(usable, i / divisions), 3) for i in range(1, divisions)]
AGE_AWARE_IMPOSSIBLE = True

def _unreachable_tier(seed: int, world: World, hard: TierResult, notes: list[str]) -> str:
    hard_settings = TIER_SETTINGS['hard_glitches']
    filename = filename_for_seed(canonical_seed(seed))

    def free_world_blocks(strict_age: bool) -> bool:
        relaxed, missing = item_aware_free_world(world, filename, hard_settings, strict_age=strict_age)
        free = _tier_result('hard_glitches', analyze_seed(seed, world=relaxed, settings=hard_settings))
        if free.feasible:
            return False
        lacking = [name for name in NOTABLE_MISSING if name in missing]
        notes.append(f'impossible: {free.unreached_goals} of {free.total_goals} squares still have no route when every rule in the world is replaced by True except where it needs something this seed can never collect' + (f" ({', '.join(lacking)})" if lacking else '') + (' and, on doors and deaths, the age Link can be there' if strict_age else '') + ". Farore's Wind returns, sealed boss-room exits and skip_child_zelda keep their rules, since nothing can lift them. Only the entrance permutation decides this, so no glitch or ruling can reach those squares")
        return True
    if free_world_blocks(False):
        return 'impossible'
    if hard.total_goals and hard.unreached_goals == hard.total_goals:
        notes.append("trapped: not one board square is reachable, the Clipper shape -- Link's starting pocket holds nothing that opens an exit out of it. Every rule free DOES complete this board, so this rests on the pocket's exit rules rather than on connectivity")
        return 'trapped'
    if AGE_AWARE_IMPOSSIBLE and free_world_blocks(True):
        return 'impossible'
    notes.append("'unproven' means the solver found no route, not that the seed is impossible: known real completions still land in the unproven buckets, so this classification is not proof of impossibility")
    return 'unproven_marginal' if hard.unreached_goals <= UNPROVEN_MARGINAL_MAX else 'unproven'

def _tier_result(tier: str, analysis: MatchedSeedAnalysis) -> TierResult:
    payload_goals = analysis.score.goals
    costs = [g.cost for g in payload_goals if g.cost is not None]
    unreached_goal_names = [g.name for g in payload_goals if g.requirement_kind == 'unmapped' or not g.satisfiable or g.cost is None]
    unreached = len(unreached_goal_names)
    feasible = bool(payload_goals) and unreached == 0
    goal_scores = [g.difficulty_score for g in analysis.goal_difficulty]
    full = analysis.score.workload_split().makespan if feasible else None
    partial = full if full is not None else _partial_makespan(costs)
    hardest = None
    if analysis.board_difficulty.hardest_goals:
        hardest = analysis.board_difficulty.hardest_goals[0]['name']
    return TierResult(tier=tier, feasible=feasible, unreached_goals=unreached, reached_regions=analysis.reached_regions, reached_locations=analysis.reached_locations, median_goal_cost=statistics.median(costs) if costs else None, maximum_goal_cost=max(costs, default=None), partial_makespan=partial, full_makespan=full, effort=board_effort(goal_scores, full, unreached), hardest_goal=hardest, unreached_goal_names=unreached_goal_names, total_goals=len(payload_goals))
HARD_TIER_SQUARES = frozenset({'Blue Gauntlets', 'Black Gauntlets', 'Green Gauntlets'})

def profile_seed(seed: int | str, world: World | None=None, bands: Sequence[float] | None=None, exhaustive: bool=False) -> SeedProfile:
    seed_number = canonical_seed(seed)
    world = world or World.load()
    results: dict[str, TierResult] = {}
    notes: list[str] = []
    board = native_board(seed_number)
    shared: list = []
    chest_shared: list = []

    def chest_seed_world():
        if not chest_shared:
            chest_shared.append(seed_world_for_filename(filename_for_seed(seed_number), world, sacred_chest_opened=True))
        return chest_shared[0]

    def solve(tier: str) -> TierResult:
        if tier not in results:
            if not shared:
                shared.append(seed_world_for_filename(filename_for_seed(seed_number), world))
            results[tier] = _tier_result(tier, analyze_seed(seed_number, world=world, settings=TIER_SETTINGS[tier], seed_world=shared[0], chest_seed_world=chest_seed_world, board=board))
        return results[tier]

    def unproven_tier(residual: int) -> str:
        return 'unproven_marginal' if residual <= UNPROVEN_MARGINAL_MAX else 'unproven'
    if exhaustive:
        for tier in TIER_ORDER:
            solve(tier)
        access = next((t for t in TIER_ORDER if results[t].feasible), unproven_tier(results['hard_glitches'].unreached_goals))
    else:

        def from_common() -> str:
            if solve('common_glitches').feasible:
                return 'glitchless' if solve('glitchless').feasible else 'common_glitches'
            hard = solve('hard_glitches')
            return 'hard_glitches' if hard.feasible else unproven_tier(hard.unreached_goals)
        if {goal['name'] for goal in board} & HARD_TIER_SQUARES:
            access = from_common()
        elif solve('glitchless').feasible:
            access = 'glitchless'
        else:
            access = from_common()
        notes.append(f"tiers solved: {', '.join(results)}; the others follow, since reachability is monotone in tier")
    residual = results['hard_glitches'].unreached_goals if 'hard_glitches' in results else 0
    proven = access in TIER_ORDER
    if not proven:
        access = _unreachable_tier(seed_number, world, results['hard_glitches'], notes)
    chosen = results.get(access)
    effort = chosen.effort if chosen else None
    unlocks: dict[str, int] = {}
    unlock_goals: dict[str, list[str]] = {}
    previous: TierResult | None = None
    for tier in TIER_ORDER:
        result = results.get(tier)
        if result is None:
            continue
        if previous is not None:
            unlocks[tier] = max(0, previous.unreached_goals - result.unreached_goals)
            still_blocked = Counter(result.unreached_goal_names)
            newly_reachable: list[str] = []
            for name in previous.unreached_goal_names:
                if still_blocked[name]:
                    still_blocked[name] -= 1
                else:
                    newly_reachable.append(name)
            unlock_goals[tier] = newly_reachable
        previous = result
    return SeedProfile(seed=seed_number, profile_version=PROFILE_VERSION, access_tier=access, access_tier_label=TIER_LABELS[access], access_rank=ACCESS_ORDER.index(access), effort=None if effort is None else round(effort, 3), effort_band=effort_band(effort, bands), residual=0 if proven else residual, tier_unlocks=unlocks, tier_unlock_goals=unlock_goals, completion_probability=None if effort is None else round(_completion_probability(effort), 5), tiers=results, solves_used=len(results), notes=notes)

def summarize_profile(profile: SeedProfile) -> str:
    if profile.access_tier == 'impossible':
        return f'seed {profile.seed}: impossible - {profile.residual}/25 goals have no route even with every rule in the world free, so the permutation does not connect them'
    if profile.access_tier == 'trapped':
        return f'seed {profile.seed}: trapped start - not one of the 25 goals is reachable, because nothing in the starting pocket opens an exit out of it'
    if not profile.proven:
        qualifier = 'near miss' if profile.access_tier == 'unproven_marginal' else 'unproven'
        return f'seed {profile.seed}: no modeled route at any tier ({qualifier}) - {profile.residual}/25 goals unrouted'
    reason = profile.tier_unlock_goals.get(profile.access_tier, [])
    tier_reason = '' if not reason else f" for {', '.join(reason)}"
    return f'seed {profile.seed}: playable at {profile.access_tier_label.lower()}{tier_reason} - {profile.effort_band.lower()} workload (effort {profile.effort:.1f}/100)'
