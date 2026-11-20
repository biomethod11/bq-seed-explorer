from __future__ import annotations
import heapq
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable
from .logic import AGES, ROOT_REGION, SearchResult
from .rules import DEFAULT_SETTINGS, RuleEvaluator
from .world import Exit, SeedWorld, World, add_grants
EdgeCost = Callable[[World, 'DiscoveryWeights', str, Exit, str], float]

@dataclass(frozen=True)
class DiscoveryWeights:
    step_cost: float = 1.0
    region_class: dict[str, float] = field(default_factory=lambda: {'overworld': 1.0, 'interior': 1.1, 'dungeon': 2.5, 'unmodeled': 2.0})
    entrance_kind: dict[str, float] = field(default_factory=lambda: {'Grotto': 4.0, 'Grave': 1.8, 'Hideout': 2.0, 'SpecialInterior': 1.3, 'Scripted': 2.2, 'Interior': 1.0, 'Overworld': 1.0, 'Dungeon': 1.0, 'DungeonSpecial': 1.0, 'ChildBoss': 1.0, 'AdultBoss': 1.0, 'SpecialBoss': 1.0, 'BlueWarp': 1.0, 'WarpSong': 1.0, 'OwlDrop': 1.0, 'Spawn': 1.0, 'Extra': 1.0, 'OverworldOneWay': 1.0})
    default_entrance_kind: float = 1.5
    fanout_weight: float = 0.35
    internal_step_cost: float = 0.25

@dataclass
class DiscoveryResult:
    region_cost: dict[tuple[str, str], float]
    location_cost: dict[str, float]
    item_cost: dict[str, float]
    unreachable_regions: set[str]
    weights: DiscoveryWeights
    location_region: dict[str, str] = field(default_factory=dict)
    location_zone: dict[str, str] = field(default_factory=dict)
    region_zone: dict[str, str] = field(default_factory=dict)
    event_cost: dict[str, float] = field(default_factory=dict)
    entrance_cost: dict[int, float] = field(default_factory=dict)
    location_item: dict[str, str | None] = field(default_factory=dict)

    def cost_of_region(self, region: str, age: str | None=None) -> float | None:
        if age is not None:
            return self.region_cost.get((region, age))
        candidates = [self.region_cost[region, a] for a in AGES if (region, a) in self.region_cost]
        return min(candidates) if candidates else None

    def cost_of_item(self, item: str) -> float | None:
        return self.item_cost.get(item)

    def cost_of_location(self, location: str) -> float | None:
        return self.location_cost.get(location)

    def cost_of_event(self, event: str) -> float | None:
        return self.event_cost.get(event)

    def cost_of_entrance(self, entrance_id: int) -> float | None:
        return self.entrance_cost.get(entrance_id)

    def hardest_items(self, limit: int=15) -> list[tuple[str, float]]:
        return sorted(self.item_cost.items(), key=lambda kv: -kv[1])[:limit]

def classify_region(world: World, region: str) -> str:
    data = world.regions.get(region, {})
    if data.get('synthetic'):
        return 'unmodeled'
    if data.get('dungeon'):
        return 'dungeon'
    if data.get('time_passes') or data.get('hint'):
        return 'overworld'
    return 'interior'

def _edge_weight(world: World, weights: DiscoveryWeights, region: str, exit_: Exit, edge_cost: EdgeCost | None=None, age: str | None=None) -> float:
    if exit_.refire_of is not None:
        return _edge_weight(world, weights, region, exit_.refire_of, edge_cost, age) + len(exit_.refire_ids) * weights.step_cost * weights.entrance_kind['Scripted']
    if exit_.mounted_of is not None:
        data = world.regions.get(region, {})
        real = data.get('mounted_of') or data.get('remembering_of') or region
        return _edge_weight(world, weights, real, exit_.mounted_of, edge_cost, age)
    if edge_cost is not None:
        return edge_cost(world, weights, region, exit_, age)
    if not exit_.is_shuffled:
        return weights.internal_step_cost
    region_mult = weights.region_class.get(classify_region(world, region), 1.0)
    kind = None
    if exit_.index is not None:
        record = world.entrances.get(exit_.index)
        if record:
            kind = record.get('type')
    if exit_.spool_slot is not None:
        kind = 'Grotto'
    kind_mult = weights.entrance_kind.get(kind, weights.default_entrance_kind) if kind is not None else weights.default_entrance_kind
    n_exits = len(world.region_exits.get(region, ()))
    single_action = (world.regions.get(region) or {}).get('single_action')
    if single_action:
        n_exits = 1
        kind_mult = weights.entrance_kind.get(single_action, weights.default_entrance_kind)
    fanout = weights.fanout_weight * math.log2(n_exits) if n_exits > 1 else 0.0
    return weights.step_cost * region_mult * kind_mult + fanout
_EVALUATORS: dict[tuple[int, str], tuple[World, RuleEvaluator]] = {}

def _evaluator_for(world: World, settings: dict[str, Any]) -> RuleEvaluator:
    key = (id(world), repr(sorted(settings.items())))
    cached = _EVALUATORS.get(key)
    if cached is not None and cached[0] is world:
        return cached[1]
    if len(_EVALUATORS) >= 16:
        _EVALUATORS.clear()
    evaluator = RuleEvaluator(items=world.item_names, events=world.event_names, settings=settings)
    _EVALUATORS[key] = (world, evaluator)
    return evaluator

def compute(seed_world: SeedWorld, search: SearchResult | None=None, weights: DiscoveryWeights | None=None, settings: dict[str, Any] | None=None, edge_cost: EdgeCost | None=None, serial_age_switch_cost: float | None=None) -> DiscoveryResult:
    world = seed_world.world
    weights = weights or DiscoveryWeights()
    evaluator = _evaluator_for(world, {**DEFAULT_SETTINGS, **(settings or {})})
    region_cost: dict[tuple[str, str], float] = {}
    location_cost: dict[str, float] = {}
    item_cost: dict[str, float] = {}
    events: set[str] = set()
    event_cost: dict[str, float] = {}
    entrance_cost: dict[int, float] = {}
    items: dict[str, int] = {}
    version: dict[tuple, int] = {}
    watchers: dict[tuple, list[tuple[list[int], int]]] = {}

    def bump(key: tuple) -> None:
        version[key] = version.get(key, 0) + 1
        for queue, serial in watchers.pop(key, ()):
            heapq.heappush(queue, serial)

    def stale(seen: dict[tuple, int]) -> bool:
        return any((version.get(key, 0) != gen for key, gen in seen.items()))

    class Ctx:
        __slots__ = ('age', 'region', 'touched')

        def __init__(self) -> None:
            self.touched: set[tuple] = set()

        def has(self, item: str, count: int=1) -> bool:
            self.touched.add(('has', item))
            return item in events or items.get(item, 0) >= count

        def is_reachable(self, region: str, age: str) -> bool:
            self.touched.add(('region', region, age))
            return (region, age) in region_cost
    ctx = Ctx()

    def snapshot_touched() -> dict[tuple, int]:
        return {key: version.get(key, 0) for key in ctx.touched}

    def watch(queue: list[int], serial: int) -> None:
        for key in ctx.touched:
            watchers.setdefault(key, []).append((queue, serial))

    def due(queue: list[int]) -> Iterator[int]:
        passed: list[int] = []
        position = -1
        while queue:
            serial = heapq.heappop(queue)
            if serial <= position:
                passed.append(serial)
                continue
            position = serial
            yield serial
        for serial in passed:
            heapq.heappush(queue, serial)
    heap: list[tuple[float, str, str]] = []
    for age in AGES:
        if ROOT_REGION in world.regions:
            heapq.heappush(heap, (0.0, ROOT_REGION, age))
    blocked_exits: dict[int, tuple[float, str, str, Exit, dict[tuple, int]]] = {}
    pending_locations: dict[int, tuple[float, str, str, Any, dict[tuple, int]]] = {}
    pending_events: dict[int, tuple[float, str, str, str, str, dict[tuple, int]]] = {}
    exit_queue: list[int] = []
    location_queue: list[int] = []
    event_queue: list[int] = []
    next_serial = count()
    frontier_cost = 0.0
    frontier_age: str | None = None

    def opened_at(base_cost: float, age: str) -> float:
        if serial_age_switch_cost is None or frontier_age is None or frontier_age == age or (frontier_cost <= base_cost):
            return max(base_cost, frontier_cost)
        anchor = min(item_cost.get('Time Travel', 0.0), frontier_cost)
        return max(base_cost, anchor) + (frontier_cost - anchor) + serial_age_switch_cost

    def safe_eval(rule: str, region: str, age: str) -> bool:
        ctx.age = age
        ctx.region = region
        ctx.touched = set()
        return bool(evaluator.evaluate(rule, ctx))

    def collect(location, cost: float) -> None:
        cost += location.walk_steps * weights.internal_step_cost
        location_cost[location.name] = cost
        if not location.vanilla_item:
            return
        if location.type == 'Event':
            events.add(location.vanilla_item)
            bump(('has', location.vanilla_item))
        else:
            for item in add_grants(items, location.name, location.vanilla_item):
                item_cost.setdefault(item, cost)
                bump(('has', item))
        item_cost.setdefault(location.vanilla_item, cost)

    def try_relax(base_cost: float, region: str, age: str, exit_: Exit) -> bool:
        if not safe_eval(exit_.rule, region, age):
            return False
        cost = opened_at(base_cost, age) + _edge_weight(world, weights, region, exit_, edge_cost, age)
        actual_entrance = seed_world.exit_resolved_entrance(exit_)
        if actual_entrance is not None:
            entrance_cost[actual_entrance] = min(entrance_cost.get(actual_entrance, math.inf), cost)
        destinations = seed_world.exit_destinations(exit_)
        if not destinations:
            return True
        for hop, dest in enumerate(destinations):
            if dest not in world.regions:
                continue
            hop_cost = cost + hop * weights.step_cost * weights.default_entrance_kind
            arrives = exit_.arrival_age(age)
            if hop_cost < region_cost.get((dest, arrives), math.inf):
                heapq.heappush(heap, (hop_cost, dest, arrives))
        return True

    def drain() -> None:
        while event_queue or location_queue or exit_queue:
            for serial in due(event_queue):
                entry = pending_events.get(serial)
                if entry is None:
                    continue
                base, reg, age, name, rule, seen = entry
                if name in events:
                    del pending_events[serial]
                    continue
                if not stale(seen):
                    continue
                if safe_eval(rule, reg, age):
                    del pending_events[serial]
                    events.add(name)
                    bump(('has', name))
                    event_cost.setdefault(name, opened_at(base, age))
                else:
                    pending_events[serial] = (base, reg, age, name, rule, snapshot_touched())
                    watch(event_queue, serial)
            for serial in due(location_queue):
                entry = pending_locations.get(serial)
                if entry is None:
                    continue
                base, reg, age, location, seen = entry
                if location.name in location_cost:
                    del pending_locations[serial]
                    continue
                if not stale(seen):
                    continue
                if safe_eval(location.rule, reg, age):
                    del pending_locations[serial]
                    collect(location, opened_at(base, age))
                else:
                    pending_locations[serial] = (base, reg, age, location, snapshot_touched())
                    watch(location_queue, serial)
            for serial in due(exit_queue):
                entry = blocked_exits.get(serial)
                if entry is None:
                    continue
                base, reg, age, exit_, seen = entry
                if not stale(seen):
                    continue
                if try_relax(base, reg, age, exit_):
                    del blocked_exits[serial]
                else:
                    blocked_exits[serial] = (base, reg, age, exit_, snapshot_touched())
                    watch(exit_queue, serial)
    while heap:
        cost, region, age = heapq.heappop(heap)
        key = (region, age)
        if key in region_cost and cost >= region_cost[key]:
            continue
        region_cost[key] = cost
        bump(('region', region, age))
        frontier_cost = cost
        frontier_age = age
        for event_name, rule in world.region_events(region).items():
            if event_name in events:
                continue
            if safe_eval(rule, region, age):
                events.add(event_name)
                bump(('has', event_name))
                event_cost.setdefault(event_name, cost)
            else:
                serial = next(next_serial)
                pending_events[serial] = (cost, region, age, event_name, rule, snapshot_touched())
                watch(event_queue, serial)
        for location in world.region_locations.get(region, ()):
            if location.name in location_cost:
                continue
            if safe_eval(location.rule, region, age):
                collect(location, cost)
            else:
                serial = next(next_serial)
                pending_locations[serial] = (cost, region, age, location, snapshot_touched())
                watch(location_queue, serial)
        for exit_ in seed_world.exits_from(region):
            if not try_relax(cost, region, age, exit_):
                serial = next(next_serial)
                blocked_exits[serial] = (cost, region, age, exit_, snapshot_touched())
                watch(exit_queue, serial)
        drain()
    reached = {r for r, _ in region_cost}
    unreachable = set(world.regions) - reached
    return DiscoveryResult(region_cost=region_cost, location_cost=location_cost, item_cost=item_cost, unreachable_regions=unreachable, weights=weights, location_region={location.name: region for region, locations in world.region_locations.items() for location in locations if not location.alternate}, location_zone={location.name: world.regions.get(region, {}).get('dungeon') or world.regions.get(region, {}).get('hint') or region for region, locations in world.region_locations.items() for location in locations if not location.alternate}, region_zone={region: data.get('dungeon') or data.get('hint') or region for region, data in world.regions.items()}, event_cost=event_cost, entrance_cost=entrance_cost, location_item={location.name: location.vanilla_item for locations in world.region_locations.values() for location in locations})

def seed_world_for_filename(name: str, world: World | None=None, sacred_chest_opened: bool=False) -> SeedWorld:
    from .shuffle import predict_entrance_table
    world = world or World.load()
    table = predict_entrance_table(name, sacred_chest_opened=sacred_chest_opened)
    return SeedWorld(world, table['resolve'], spool_table=table['effective_spool_table'])

def compute_for_filename(name: str, world: World | None=None, weights: DiscoveryWeights | None=None, settings: dict[str, Any] | None=None, edge_cost: EdgeCost | None=None, seed_world: SeedWorld | None=None) -> DiscoveryResult:
    seed_world = seed_world or seed_world_for_filename(name, world)
    return compute(seed_world, weights=weights, settings=settings, edge_cost=edge_cost)

def reaches_beyond(opened: SeedWorld, fresh: SeedWorld, searched: DiscoveryResult) -> bool:
    reached = searched.region_cost
    for region in {region for region, _age in reached}:
        for exit_, destinations in opened.destinations_beyond(fresh, region):
            for age in AGES:
                if (region, age) not in reached:
                    continue
                landing = exit_.arrival_age(age)
                if any(((dest, landing) not in reached for dest in destinations)):
                    return True
    return False
