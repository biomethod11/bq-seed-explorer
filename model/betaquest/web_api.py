from __future__ import annotations
import re
from collections import OrderedDict
from typing import Any, Callable
from . import bingosync, profile, seed_report
from .bingosync import canonical_seed
from .profile import PROFILE_VERSION, TIER_LABELS, TIER_ORDER, load_effort_bands
from .region_names import display_name
from .routes import LEVEL_NOTES, SeedRouter, describe_steps, goal_targets
from .seed_report import SeedSolves, explain_seed, opener_text
from .world import World

def _plural(count: str, one: str, many: str) -> str:
    return f"{count} {(one if count == '1' else many)}"
FACTOR_WORDING: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str]], ...] = tuple(((re.compile(pattern), words) for pattern, words in (('very high world-specific discovery workload \\((?P<cost>[\\d.]+)\\)', lambda m: f"very far to find on this seed (cost {m['cost']})"), ('high world-specific discovery workload \\((?P<cost>[\\d.]+)\\)', lambda m: f"far to find on this seed (cost {m['cost']})"), ('objective is spread across (?P<n>\\d+) separately discovered regions', lambda m: f"spread across {_plural(m['n'], 'area', 'areas')} you have to find separately"), ('requires at least (?P<n>\\d+) qualifying checks', lambda m: f"needs at least {_plural(m['n'], 'pickup or check', 'pickups or checks')}"), ('requires (?P<n>\\d+) serial prerequisite discoveries before the final objective', lambda m: 'needs 1 other thing found first' if m['n'] == '1' else f"needs {m['n']} other things found first, one after another"), ('access is harder than about (?P<percent>\\d+%) of calibrated random worlds for this goal', lambda m: f"harder to reach than on about {m['percent']} of random seeds"), ('goal uses a conservative proxy rather than a directly observable completion event', lambda m: 'the model checks a stand-in for this goal, not the goal itself'), ('completion is represented by a region/event proxy', lambda m: 'the model counts reaching the right place or event as finishing it'), ('goal-specific Monte Carlo calibration unavailable; absolute access curve used', lambda m: 'no random-seed comparison for this goal, so a general scale is used'), ('multiple high-damage Iron Knuckle fights', lambda m: 'several hard-hitting Iron Knuckle fights'), ('requires several full dungeon boss completions', lambda m: 'needs several whole dungeons beaten, bosses included'), ('boss fight and its combat prerequisites', lambda m: 'a boss fight, and the gear to win it'), ('combat execution is not represented by reachability alone', lambda m: "the fights add difficulty the route doesn't show"), ('room clears require navigation and puzzle execution', lambda m: 'clearing the rooms takes puzzle solving, not just getting there'), ('keys must be found while preserving enough of them unused', lambda m: 'you have to find keys and leave enough of them unused'), ('Spirit Temple adult loadout and statue-room execution', lambda m: 'needs adult Spirit Temple gear and the statue room'), ('Sky Temple spawn damage, survival loadout, and three Iron Knuckles', lambda m: 'Sky Temple: damage when you land, gear to survive, and three Iron Knuckles'))))

def plain_factor(text: str) -> str:
    for pattern, words in FACTOR_WORDING:
        match = pattern.fullmatch(text)
        if match:
            return words(match)
    return text
KEEP_SEEDS = 4
MAX_TARGETS = 30
_WORLD: World | None = None
_SESSIONS: OrderedDict[tuple[int, int], 'SeedSession'] = OrderedDict()

def use_board_source(board_for: Callable[[int], list[dict]]) -> None:

    def native_board(seed: int | str, node: str | None=None) -> list[dict]:
        return [dict(goal) for goal in board_for(canonical_seed(seed))]
    for module in (bingosync, profile, seed_report):
        module.native_board = native_board
    _SESSIONS.clear()

def pin_model_version(version: str) -> None:
    global PROFILE_VERSION
    PROFILE_VERSION = version
    profile.PROFILE_VERSION = version
    seed_report.PROFILE_VERSION = version

def _world() -> World:
    global _WORLD
    if _WORLD is None:
        _WORLD = World.load()
    return _WORLD

class SeedSession:

    def __init__(self, seed: int, card: int | None=None) -> None:
        self.solves = SeedSolves(seed, _world(), card=card)
        self._routers: dict[str, SeedRouter] = {}

    @property
    def profile(self):
        return self.solves.profile

    def score_tier(self) -> str:
        return self.profile.access_tier if self.profile.proven else 'hard_glitches'

    def lowest_tier(self, name: str) -> str | None:
        for tier in TIER_ORDER:
            if name not in self.profile.tiers[tier].unreached_goal_names:
                return tier
        return None

    def router(self, tier: str) -> SeedRouter:
        if tier not in self._routers:
            self._routers[tier] = SeedRouter(self.solves.seed, world=self.solves.world, tier=tier)
        return self._routers[tier]

    def openers(self) -> dict[str, str]:
        attributed = self.solves._attributed
        if attributed is None:
            return {}
        return {reason.square: opener_text(reason) for reasons in attributed.values() for reason in reasons}

def session(seed: int | str, card: int | str | None=None) -> SeedSession:
    number = canonical_seed(seed)
    key = (number, number if card is None else canonical_seed(card))
    if key in _SESSIONS:
        _SESSIONS.move_to_end(key)
    else:
        _SESSIONS[key] = SeedSession(*key)
        while len(_SESSIONS) > KEEP_SEEDS:
            _SESSIONS.popitem(last=False)
    return _SESSIONS[key]

def _square_summary(state: SeedSession, index: int, goal, estimate, openers: dict[str, str]) -> dict[str, Any]:
    lowest = state.lowest_tier(goal.name)
    return {'index': index, 'name': goal.name, 'lowest_tier': lowest, 'lowest_tier_label': TIER_LABELS[lowest] if lowest else 'No route found', 'difficulty': round(estimate.difficulty_score, 1) if goal.cost is not None else None, 'cost': None if goal.cost is None else round(goal.cost, 1), 'after_sky_chest': goal.after_sky_chest, 'opened_by': openers.get(goal.name)}

def overview(seed: int | str, attribute: bool=False, card: int | str | None=None) -> dict[str, Any]:
    state = session(seed, card)
    report = explain_seed(state.solves.seed, attribute=attribute, solves=state.solves)
    scored = state.solves.analysis(state.score_tier())
    openers = state.openers()
    start = state.router('glitchless').seed_world
    return {'seed': report.seed, 'filename': report.filename, 'card_seed': report.card_seed, 'profile_version': PROFILE_VERSION, 'report': report.to_dict(), 'effort_bands': list(load_effort_bands()), 'scored_at': state.score_tier(), 'start': {age: display_name(start.start_region(age) or '?', with_raw=False) for age in ('child', 'adult')}, 'squares': [_square_summary(state, index, goal, estimate, openers) for index, (goal, estimate) in enumerate(zip(scored.score.goals, scored.goal_difficulty))]}

def _route_payload(router: SeedRouter, route: dict | None) -> dict[str, Any] | None:
    if route is None:
        return None
    return {'age': route['age'], 'loading_zones': route['count'], 'level': route['level'], 'level_note': LEVEL_NOTES[route['level']], 'without_target': route.get('without_target', True), 'ends_in': display_name(route['region'], with_raw=False), 'steps': describe_steps(router, route['steps'])}

def square(seed: int | str, index: int, card: int | str | None=None) -> dict[str, Any]:
    state = session(seed, card)
    scored = state.solves.analysis(state.score_tier())
    goal, estimate = (scored.score.goals[index], scored.goal_difficulty[index])
    summary = _square_summary(state, index, goal, estimate, state.openers())
    route_tier = summary['lowest_tier'] or 'hard_glitches'
    at_tier = state.solves.analysis(route_tier).score.goals[index]
    router = state.router(route_tier)
    start = router.seed_world.start_region('child')
    targets = goal_targets(router.world, at_tier.locations_used)
    routes = []
    for target in targets[:MAX_TARGETS]:
        found = router.route_to(start, target) if start and target.places else None
        routes.append({'target': target.label, 'route': _route_payload(router, found)})
    return {**summary, 'seed': state.solves.seed, 'card_seed': state.solves.card, 'kind': goal.requirement_kind, 'note': goal.note, 'factors': [plain_factor(factor) for factor in estimate.factors], 'confidence': estimate.confidence_label, 'scored_at': state.score_tier(), 'route_tier': route_tier, 'route_tier_label': TIER_LABELS[route_tier], 'start': display_name(start, with_raw=False) if start else None, 'places_needed': len(targets), 'routes_shown': len(routes), 'routes': routes}
