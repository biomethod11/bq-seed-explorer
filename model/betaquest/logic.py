from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable
from .rules import DEFAULT_SETTINGS, RuleEvaluator
from .world import MOUNTED_SUFFIX, REMEMBERING_SUFFIX, SeedWorld, World, add_grants
AGES = ('child', 'adult')
ROOT_REGION = 'Root'

@dataclass
class SearchResult:
    reached: set[tuple[str, str]]
    collected_locations: set[str]
    items: Counter
    events: set[str]
    spheres: list[set[str]]
    unknown_identifiers: set[str]
    start_region: str | None
    iterations: int

    @property
    def reached_regions(self) -> set[str]:
        return {region for region, _ in self.reached if not region.endswith((MOUNTED_SUFFIX, REMEMBERING_SUFFIX))}

    def can_reach(self, region: str, age: str | None=None) -> bool:
        if age is None:
            return any(((region, a) in self.reached for a in AGES))
        return (region, age) in self.reached

    def has_item(self, item: str, count: int=1) -> bool:
        return self.items[item] >= count

    def location_reached(self, location: str) -> bool:
        return location in self.collected_locations

class _Context:
    __slots__ = ('age', 'region', '_state')

    def __init__(self, state: '_State') -> None:
        self._state = state
        self.age = 'child'
        self.region = ROOT_REGION

    def has(self, item: str, count: int=1) -> bool:
        if item in self._state.events:
            return True
        return self._state.items[item] >= count

    def is_reachable(self, region: str, age: str) -> bool:
        return (region, age) in self._state.reached

@dataclass
class _State:
    reached: set[tuple[str, str]] = field(default_factory=set)
    collected_locations: set[str] = field(default_factory=set)
    items: Counter = field(default_factory=Counter)
    events: set[str] = field(default_factory=set)

def solve(seed_world: SeedWorld, settings: dict[str, Any] | None=None, max_iterations: int=200) -> SearchResult:
    world = seed_world.world
    evaluator = RuleEvaluator(items=world.item_names, events=world.event_names, settings={**DEFAULT_SETTINGS, **(settings or {})})
    state = _State()
    ctx = _Context(state)
    for age in AGES:
        if ROOT_REGION in world.regions:
            state.reached.add((ROOT_REGION, age))
    spheres: list[set[str]] = []
    iterations = 0
    open_work: dict[tuple[str, str], list[list]] = {}

    def work_for(region: str, age: str) -> list[list]:
        exits = []
        for exit_ in seed_world.exits_from(region):
            destinations = seed_world.exit_destinations(exit_)
            if destinations:
                arrives = exit_.arrival_age(age)
                exits.append((exit_.rule, [(dest, arrives) for dest in destinations]))
        return [list(world.region_events(region).items()), list(world.region_locations.get(region, ())), exits]
    for iterations in range(1, max_iterations + 1):
        changed = False
        sphere: set[str] = set()
        for key in list(state.reached):
            region, age = key
            if region not in world.regions:
                continue
            work = open_work.get(key)
            if work is None:
                work = open_work[key] = work_for(region, age)
            events, locations, exits = work
            ctx.age = age
            ctx.region = region
            if events:
                still_open = []
                for entry in events:
                    event_name, rule = entry
                    if event_name in state.events:
                        continue
                    if evaluator.evaluate(rule, ctx):
                        state.events.add(event_name)
                        changed = True
                    else:
                        still_open.append(entry)
                work[0] = still_open
            if locations:
                still_open = []
                for location in locations:
                    if location.name in state.collected_locations:
                        continue
                    if not evaluator.evaluate(location.rule, ctx):
                        still_open.append(location)
                        continue
                    state.collected_locations.add(location.name)
                    sphere.add(location.name)
                    changed = True
                    if location.vanilla_item:
                        if location.type == 'Event':
                            state.events.add(location.vanilla_item)
                        else:
                            add_grants(state.items, location.name, location.vanilla_item)
                work[1] = still_open
            if exits:
                still_open = []
                for entry in exits:
                    rule, targets = entry
                    if all((target in state.reached for target in targets)):
                        continue
                    if not evaluator.evaluate(rule, ctx):
                        still_open.append(entry)
                        continue
                    for target in targets:
                        if target in state.reached:
                            continue
                        state.reached.add(target)
                        changed = True
                work[2] = still_open
        if sphere:
            spheres.append(sphere)
        if not changed:
            break
    else:
        raise RuntimeError(f'reachability solver did not converge after {max_iterations} iterations')
    return SearchResult(reached=set(state.reached), collected_locations=set(state.collected_locations), items=Counter(state.items), events=set(state.events), spheres=spheres, unknown_identifiers=set(evaluator.unknown_identifiers), start_region=seed_world.start_region('child'), iterations=iterations)

def solve_filename(name: str, world: World | None=None, settings: dict[str, Any] | None=None) -> SearchResult:
    from .shuffle import predict_entrance_table
    world = world or World.load()
    table = predict_entrance_table(name)
    seed_world = SeedWorld(world, table['resolve'], spool_table=table['effective_spool_table'])
    return solve(seed_world, settings=settings)
