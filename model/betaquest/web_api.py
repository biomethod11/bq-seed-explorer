from __future__ import annotations
from collections import OrderedDict
from typing import Any, Callable
from . import bingosync, profile, seed_report
from .bingosync import canonical_seed
from .profile import PROFILE_VERSION, TIER_LABELS, TIER_ORDER, load_effort_bands
from .region_names import display_name
from .routes import LEVEL_NOTES, SeedRouter, describe_steps, goal_targets
from .seed_report import SeedSolves, explain_seed, opener_text
from .world import World
KEEP_SEEDS = 4
MAX_TARGETS = 30
_WORLD: World | None = None
_SESSIONS: OrderedDict[int, 'SeedSession'] = OrderedDict()

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

    def __init__(self, seed: int) -> None:
        self.solves = SeedSolves(seed, _world())
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

def session(seed: int | str) -> SeedSession:
    number = canonical_seed(seed)
    if number in _SESSIONS:
        _SESSIONS.move_to_end(number)
    else:
        _SESSIONS[number] = SeedSession(number)
        while len(_SESSIONS) > KEEP_SEEDS:
            _SESSIONS.popitem(last=False)
    return _SESSIONS[number]

def _square_summary(state: SeedSession, index: int, goal, estimate, openers: dict[str, str]) -> dict[str, Any]:
    lowest = state.lowest_tier(goal.name)
    return {'index': index, 'name': goal.name, 'lowest_tier': lowest, 'lowest_tier_label': TIER_LABELS[lowest] if lowest else 'No route found', 'difficulty': round(estimate.difficulty_score, 1) if goal.cost is not None else None, 'cost': None if goal.cost is None else round(goal.cost, 1), 'after_sky_chest': goal.after_sky_chest, 'opened_by': openers.get(goal.name)}

def overview(seed: int | str, attribute: bool=False) -> dict[str, Any]:
    state = session(seed)
    report = explain_seed(state.solves.seed, attribute=attribute, solves=state.solves)
    scored = state.solves.analysis(state.score_tier())
    openers = state.openers()
    start = state.router('glitchless').seed_world
    return {'seed': report.seed, 'filename': report.filename, 'profile_version': PROFILE_VERSION, 'report': report.to_dict(), 'effort_bands': list(load_effort_bands()), 'scored_at': state.score_tier(), 'start': {age: display_name(start.start_region(age) or '?', with_raw=False) for age in ('child', 'adult')}, 'squares': [_square_summary(state, index, goal, estimate, openers) for index, (goal, estimate) in enumerate(zip(scored.score.goals, scored.goal_difficulty))]}

def _route_payload(router: SeedRouter, route: dict | None) -> dict[str, Any] | None:
    if route is None:
        return None
    return {'age': route['age'], 'loading_zones': route['count'], 'level': route['level'], 'level_note': LEVEL_NOTES[route['level']], 'without_target': route.get('without_target', True), 'ends_in': display_name(route['region'], with_raw=False), 'steps': describe_steps(router, route['steps'])}

def square(seed: int | str, index: int) -> dict[str, Any]:
    state = session(seed)
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
    return {**summary, 'seed': state.solves.seed, 'kind': goal.requirement_kind, 'note': goal.note, 'factors': list(estimate.factors), 'confidence': estimate.confidence_label, 'scored_at': state.score_tier(), 'route_tier': route_tier, 'route_tier_label': TIER_LABELS[route_tier], 'start': display_name(start, with_raw=False) if start else None, 'places_needed': len(targets), 'routes_shown': len(routes), 'routes': routes}
