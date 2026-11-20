from __future__ import annotations
import ast
import heapq
import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from .bingosync import canonical_seed, filename_for_seed
from .logic import _Context, solve
from .profile import TIER_SETTINGS
from .region_names import display_name
from .rules import DEFAULT_SETTINGS, RuleEvaluator
from .shuffle import predict_entrance_table
from .world import SeedWorld, World
AGES = ('child', 'adult')
WARP = '__save_or_warp__'
WARP_HUB = 'Root Exits'
DOOR_KINDS = ('__grotto', '__scripted', '__exit_')
RESET_KINDS = ('__save_reset', '__death_reset')
NEVER_LAND = ('Root', 'Farores Wind Warp')
ITEM_ALIASES = frozenset({'Hookshot', 'Longshot', 'Silver_Gauntlets', 'Golden_Gauntlets'})
SONG_WARPS = frozenset((f'{song} Warp' for song in ('Minuet of Forest', 'Bolero of Fire', 'Serenade of Water', 'Requiem of Spirit', 'Nocturne of Shadow', 'Prelude of Light')))
LEVEL_NOTES = {0: 'doors only', 1: 'no route by doors alone: this one uses a save warp, a warp song or dying', 2: 'no route without dying: a death re-fires the entrance you arrived by'}
_LABELS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'scripted_exit_labels.json'

@lru_cache(maxsize=1)
def scripted_exit_labels() -> dict[int, str]:
    raw = json.loads(_LABELS_PATH.read_text(encoding='utf-8'))
    return {int(code, 16): name for code, name in raw.items()}

@dataclass(frozen=True)
class Target:
    label: str
    places: tuple[tuple[str, str], ...]
    age: str | None = None
    gives: tuple[str, ...] = ()

class _Holdings:
    __slots__ = ('items', 'events', 'reached')

    def __init__(self, result: Any, lacking: frozenset[str]) -> None:
        self.items = Counter(result.items)
        for name in lacking:
            if self.items[name] > 0:
                self.items[name] -= 1
        self.events = set(result.events) - lacking
        self.reached = result.reached

    @classmethod
    def nothing(cls, result: Any) -> '_Holdings':
        empty = cls.__new__(cls)
        empty.items, empty.events, empty.reached = (Counter(), set(), result.reached)
        return empty
_REGION_USED = re.compile('^region: (?P<region>.+?)(?: \\((?P<age>child|adult|either)\\))?$')

def goal_targets(world: World, locations_used: list[str]) -> list[Target]:
    homes: dict[str, list[tuple[str, str]]] = {}
    copies: dict[str, list[tuple[str, str]]] = {}
    gives: dict[str, str] = {}
    for region, locations in world.region_locations.items():
        if world.is_state_copy(region):
            continue
        for location in locations:
            (copies if location.alternate else homes).setdefault(location.name, []).append((region, location.rule))
            if location.vanilla_item:
                gives.setdefault(location.name, location.vanilla_item)
    events: dict[str, list[tuple[str, str]]] = {}
    for region in world.regions:
        if world.is_state_copy(region):
            continue
        for event, rule in world.region_events(region).items():
            events.setdefault(event, []).append((region, rule))
    targets = []
    for used in locations_used:
        if used.startswith('event: '):
            name = used[len('event: '):]
            places = events.get(name, [])
            targets.append(Target(name, tuple(places), gives=(name,)))
        elif used.startswith('region: '):
            match = _REGION_USED.match(used)
            region = match['region'] if match else used[len('region: '):]
            age = match['age'] if match and match['age'] in AGES else None
            targets.append(Target(display_name(region, with_raw=False), ((region, 'True'),), age))
        else:
            places = homes.get(used) or copies.get(used) or []
            item = gives.get(used)
            targets.append(Target(used, tuple(places), gives=(item,) if item else ()))
    return targets

class SeedRouter:

    def __init__(self, seed: int, world: World | None=None, tier: str='glitchless') -> None:
        self.seed = canonical_seed(seed)
        self.world = world or World.load()
        self.settings = TIER_SETTINGS[tier]
        self.tier = tier
        table = predict_entrance_table(filename_for_seed(self.seed))
        self.seed_world = SeedWorld(self.world, table['resolve'], spool_table=table['effective_spool_table'])
        self.result = solve(self.seed_world, settings=self.settings)
        self._resolve = table['resolve']
        self._evaluator = RuleEvaluator(items=self.world.item_names, events=self.world.event_names, settings={**DEFAULT_SETTINGS, **self.settings})
        self._ctx = _Context(self.result)
        self._locations = {(region, loc.name): loc for region, locs in self.world.region_locations.items() for loc in locs}

    def landing(self, entrance: int) -> str | None:
        fired = self._resolve(entrance)['result_entrance_id'] & 65535
        return self.world.dest_region_of_index(fired)

    def _context(self, lacking: frozenset[str]) -> _Context:
        if not lacking:
            return self._ctx
        cache = self.__dict__.setdefault('_lacking', {})
        if lacking not in cache:
            cache[lacking] = _Context(_Holdings(self.result, lacking))
        return cache[lacking]

    def needs_something(self, rule: str, region: str, age: str) -> bool:
        if rule.strip() in ('True', ''):
            return False
        if '_nothing' not in self.__dict__:
            self._nothing = _Context(_Holdings.nothing(self.result))
        ctx = self._nothing
        ctx.age, ctx.region = (age, region)
        try:
            return not self._evaluator.evaluate(rule, ctx)
        except Exception:
            return True

    def holds(self, rule: str, region: str, age: str, lacking: frozenset[str]=frozenset()) -> bool:
        ctx = self._context(lacking)
        ctx.age, ctx.region = (age, region)
        try:
            return bool(self._evaluator.evaluate(rule, ctx))
        except Exception:
            return False

    @staticmethod
    def usable(exit_: Any, level: int) -> bool:
        name = exit_.name
        if getattr(exit_, 'mounted_of', None) or name.startswith(('__epona', '__suns')):
            return False
        if not name.startswith('__') or name.startswith(DOOR_KINDS):
            return True
        if name.startswith(RESET_KINDS):
            return level >= 1
        if name.startswith('__refire'):
            return level >= 2
        return False

    def search(self, start: str, age: str, level: int=0, avoid: frozenset[str]=frozenset(), lacking: frozenset[str]=frozenset()) -> tuple[dict, dict]:
        world, sw = (self.world, self.seed_world)
        dist: dict[str, int] = {start: 0}
        prev: dict[str, tuple | None] = {start: None}
        heap: list[tuple[int, int, str]] = [(0, 0, start)]
        order = 0
        while heap:
            cost, _, region = heapq.heappop(heap)
            if cost > dist.get(region, 1 << 30) or region not in world.regions:
                continue
            if level >= 1 and region != WARP_HUB and (cost + 1 < dist.get(WARP_HUB, 1 << 30)):
                dist[WARP_HUB], prev[WARP_HUB] = (cost + 1, (region, WARP))
                order += 1
                heapq.heappush(heap, (cost + 1, order, WARP_HUB))
            for exit_ in sw.exits_from(region):
                if not self.usable(exit_, level) or not self.holds(exit_.rule, region, age, lacking):
                    continue
                if avoid and self.items_named(exit_.rule) & avoid:
                    continue
                for dest in sw.exit_destinations(exit_):
                    if world.is_state_copy(dest) or dest in NEVER_LAND:
                        continue
                    if exit_.name.startswith('__refire'):
                        step = 1 + len(exit_.refire_ids)
                    else:
                        step = 1 if exit_.index is not None else 0
                    if cost + step < dist.get(dest, 1 << 30):
                        dist[dest], prev[dest] = (cost + step, (region, exit_))
                        order += 1
                        heapq.heappush(heap, (cost + step, order, dest))
        return (dist, prev)

    @staticmethod
    def path(prev: dict, target: str) -> list[tuple[str, Any, str]]:
        steps = []
        while prev.get(target):
            region, exit_ = prev[target]
            steps.append((region, exit_, target))
            target = region
        return steps[::-1]

    def collectable(self, region: str, location: str | None, age: str) -> bool:
        loc = self._locations.get((region, location)) if location else None
        return loc is None or self.holds(loc.rule, region, age)

    def route_at(self, hub: str, region: str, location: str | None, level: int) -> dict | None:
        options = []
        for age in AGES:
            dist, prev = self._search_cached(hub, age, level)
            if region in dist and self.collectable(region, location, age):
                options.append((dist[region], age, prev))
        if not options:
            return None
        count, age, prev = min(options, key=lambda o: (o[0], o[1]))
        return {'age': age, 'count': count, 'level': level, 'ages': sorted({a for _, a, _ in options}), 'steps': self.path(prev, region)}

    def route(self, hub: str, region: str, location: str | None=None) -> dict | None:
        for level in (0, 1, 2):
            found = self.route_at(hub, region, location, level)
            if found is not None:
                return found
        return None

    def search_states(self, start: str, start_age: str, level: int=0, lacking: frozenset[str]=frozenset()) -> tuple[dict, dict]:
        world, sw = (self.world, self.seed_world)
        origin = (start, start_age)
        dist: dict[tuple[str, str], int] = {origin: 0}
        prev: dict[tuple[str, str], tuple | None] = {origin: None}
        heap: list[tuple[int, int, tuple[str, str]]] = [(0, 0, origin)]
        order = 0
        while heap:
            cost, _, node = heapq.heappop(heap)
            region, age = node
            if cost > dist.get(node, 1 << 30) or region not in world.regions:
                continue
            if level >= 1 and region != WARP_HUB:
                hub = (WARP_HUB, age)
                if cost + 1 < dist.get(hub, 1 << 30):
                    dist[hub], prev[hub] = (cost + 1, (node, WARP))
                    order += 1
                    heapq.heappush(heap, (cost + 1, order, hub))
            for exit_ in sw.exits_from(region):
                if not self.usable(exit_, level) or not self.holds(exit_.rule, region, age, lacking):
                    continue
                arrival = exit_.arrival_age(age)
                for dest in sw.exit_destinations(exit_):
                    if world.is_state_copy(dest) or dest in NEVER_LAND:
                        continue
                    if exit_.name.startswith('__refire'):
                        step = 1 + len(exit_.refire_ids)
                    else:
                        step = 1 if exit_.index is not None else 0
                    nxt = (dest, arrival)
                    if cost + step < dist.get(nxt, 1 << 30):
                        dist[nxt], prev[nxt] = (cost + step, (node, exit_))
                        order += 1
                        heapq.heappush(heap, (cost + step, order, nxt))
        return (dist, prev)

    @staticmethod
    def path_states(prev: dict, node: tuple[str, str]) -> list[tuple[str, Any, str, str, str]]:
        steps = []
        while prev.get(node):
            (region, age), exit_ = prev[node]
            steps.append((region, exit_, node[0], age, node[1]))
            node = (region, age)
        return steps[::-1]

    def route_to(self, start: str, target: Target, start_age: str='child') -> dict | None:
        lacking = frozenset(target.gives)
        found = self._route_to(start, start_age, target, lacking)
        if found is None and lacking:
            found = self._route_to(start, start_age, target, frozenset())
            if found is not None:
                found['without_target'] = False
        return found

    def _route_to(self, start: str, start_age: str, target: Target, lacking: frozenset[str]) -> dict | None:
        ages = (target.age,) if target.age else AGES
        for level in (0, 1, 2):
            dist, prev = self._states_cached(start, start_age, level, lacking)
            options = [(dist[region, age], age, region) for region, rule in target.places for age in ages if (region, age) in dist and self.holds(rule, region, age, lacking)]
            if options:
                count, age, region = min(options)
                return {'age': age, 'count': count, 'level': level, 'region': region, 'steps': self.path_states(prev, (region, age)), 'without_target': True}
        return None

    def _states_cached(self, start: str, start_age: str, level: int, lacking: frozenset[str]):
        cache = self.__dict__.setdefault('_state_searches', {})
        key = (start, start_age, level, lacking)
        if key not in cache:
            cache[key] = self.search_states(start, start_age, level, lacking)
        return cache[key]

    def items_named(self, rule: str) -> frozenset[str]:
        cache = self.__dict__.setdefault('_named', {})
        if rule not in cache:
            found: set[str] = set()
            self._collect(self._evaluator.parse(rule), found, set())
            cache[rule] = frozenset(found)
        return cache[rule]

    def _collect(self, node: Any, found: set[str], seen: set[str]) -> None:
        ev = self._evaluator
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and (node.func.id in ev.macros):
            for arg in node.args:
                self._collect(arg, found, seen)
            return
        if isinstance(node, ast.Name):
            token = node.id
            macro = ev.macros.get(token)
            if macro is not None and token in ITEM_ALIASES:
                found.add(token.replace('_', ' '))
                return
            if macro is not None:
                if not macro[0] and token not in seen:
                    seen.add(token)
                    self._collect(macro[1], found, seen)
                return
            item = ev._by_escaped.get(token) or ev._item_name(token)
            if item in ev.items:
                found.add(item)
            return
        for child in ast.iter_child_nodes(node):
            self._collect(child, found, seen)

    def route_items(self, found: dict) -> frozenset[str]:
        names: set[str] = set()
        for _region, exit_, _dest in found['steps']:
            if exit_ != WARP:
                names |= self.items_named(exit_.rule)
        return frozenset(names)

    def alternatives(self, hub: str, region: str, location: str | None=None, limit: int=3) -> list[dict]:
        best = self.route(hub, region, location)
        if best is None:
            return []
        found: list[dict] = []
        shorter = self.route_at(hub, region, location, 2)
        if shorter is not None and shorter['count'] < best['count']:
            shorter['why'] = 'shorter'
            found.append(shorter)
        avoid = self.route_items(best)
        for route in found:
            avoid |= self.route_items(route)
        while avoid and len(found) < limit:
            options = []
            for age in AGES:
                dist, prev = self._search_cached(hub, age, 2, avoid=frozenset(avoid))
                if region in dist and self.collectable(region, location, age):
                    options.append((dist[region], age, prev))
            if not options:
                break
            count, age, prev = min(options, key=lambda o: (o[0], o[1]))
            route = {'age': age, 'count': count, 'level': 2, 'steps': self.path(prev, region), 'why': 'without ' + ', '.join(sorted(avoid))}
            found.append(route)
            more = self.route_items(route)
            if not more:
                break
            avoid |= more
        return found

    @staticmethod
    def uses(route: dict) -> str:
        kinds = set()
        for _region, exit_, _dest in route['steps']:
            if exit_ == WARP or exit_.name.startswith(RESET_KINDS):
                kinds.add('a save warp or warp song')
            elif exit_.name.startswith('__refire'):
                kinds.add('deaths')
        return ' and '.join(sorted(kinds)) if kinds else 'doors only'

    def _search_cached(self, hub: str, age: str, level: int, avoid: frozenset[str]=frozenset(), lacking: frozenset[str]=frozenset()):
        cache = self.__dict__.setdefault('_searches', {})
        key = (hub, age, level, avoid, lacking)
        if key not in cache:
            cache[key] = self.search(hub, age, level, avoid, lacking)
        return cache[key]

def _rule_text(exit_: Any) -> str | None:
    rule = exit_.rule.strip()
    return None if rule in ('True', '') else rule

def _special(exit_: Any) -> tuple[str, str] | None:
    name = exit_.name
    if name.startswith('__grotto'):
        leads = exit_.same_index_dest_region or 'a grotto'
        return ('hole', f'drop into the hole that leads to {display_name(leads, with_raw=False)} in the unshuffled game')
    if name.startswith('__scripted'):
        code = int(name.strip('_').split('_')[1], 16)
        label = scripted_exit_labels().get(code, f'transition 0x{code:04X}')
        source, _, leads = label.partition(' -> ')
        if leads:
            return ('scripted', f'trigger {source}, which leads to {leads} in the unshuffled game')
        return ('scripted', f'trigger the scripted transition {label}')
    if name.startswith('__exit_'):
        return ('scene_exit', 'leave by the scene exit')
    if name.startswith('__save_reset'):
        return ('save', 'save and continue')
    if name.startswith('__death_reset'):
        return ('death', "die here (you restart at this dungeon's entrance door)")
    return None

def describe_steps(router: SeedRouter, steps: list[tuple]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps:
        region, exit_, dest = step[:3]
        described = _describe_step(router, region, exit_, dest, step[3] if len(step) == 5 else None)
        if described is None:
            continue
        if len(step) == 5:
            described['age'] = step[3]
            if step[4] != step[3]:
                described['becomes'] = step[4]
        out.append(described)
    return out

def _describe_step(router: SeedRouter, region: str, exit_: Any, dest: str, age: str | None=None) -> dict[str, Any] | None:

    def _needs(step_exit: Any) -> str | None:
        rule = _rule_text(step_exit)
        if rule is None or (age is not None and (not router.needs_something(rule, region, age))):
            return None
        return rule
    if exit_ != WARP and exit_.name.startswith('__refire') and (exit_.refire_of is not None):
        door = exit_.refire_of
        special = _special(door)
        how = special[1] if special else f"take the door to {display_name(door.name.split(' -> ', 1)[-1], with_raw=False)}"
        arrive = router.landing(door.index) if door.index is not None else None
        deaths = [{'refires': f'0x{fired:04X}', 'arrive': _place(router.landing(fired))} for fired in exit_.refire_ids]
        return {'kind': 'refire', 'at': _place(region), 'do': how, 'arrive': _place(arrive), 'deaths': deaths, 'final': _place(dest), 'needs': _needs(exit_)}
    if exit_ == WARP:
        return {'kind': 'warp', 'at': _place(region), 'do': 'save and continue, or play a warp song (the next step says which)', 'arrive': None, 'needs': None}
    if region == WARP_HUB:
        how = {'Child Spawn': 'continue the save as child', 'Adult Spawn': 'continue the save as adult'}.get(dest, f"play the {dest.replace(' Warp', '')}")
        return {'kind': 'warp', 'at': None, 'do': how, 'arrive': None, 'needs': _needs(exit_)}
    if region in ('Child Spawn', 'Adult Spawn') or region in SONG_WARPS:
        return {'kind': 'appear', 'at': None, 'do': 'you appear', 'arrive': _place(dest), 'needs': None}
    special = _special(exit_)
    if special:
        kind, how = special
    elif exit_.index is None:
        if _needs(exit_) is None:
            return None
        return {'kind': 'walk', 'at': _place(region), 'do': 'walk on', 'arrive': _place(dest), 'needs': _needs(exit_)}
    else:
        kind = 'door'
        how = f"take the door to {display_name(exit_.name.split(' -> ', 1)[-1], with_raw=False)}"
    return {'kind': kind, 'at': _place(region), 'do': how, 'arrive': _place(dest), 'needs': _needs(exit_)}

def _place(region: str | None) -> str | None:
    return None if region is None else display_name(region, with_raw=False)
