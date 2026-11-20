from __future__ import annotations
import ast
from typing import Any
from .discovery import compute_for_filename
from .logic import solve
from .rules import BOTTLE_ITEMS, BQ_CHILD_SWORD, BQ_CHILD_USABLE, DEFAULT_SETTINGS, RBA_STRENGTH_ITEMS, STRENGTH_UPGRADE, RuleEvaluator
from .world import SeedWorld, World, add_grants, item_grants
FARORES_WIND_REGION = 'Farores Wind Warp'
SKY_TEMPLE_REGION = 'Sky Temple'
UNLIFTABLE_EXIT_RULES = frozenset({'False', 'skip_child_zelda'})
AGE_ONLY_EXITS: dict[tuple[str, str], str] = {('Market', 'Market Bazaar'): 'is_child', ('Market', 'Market Potion Shop'): 'is_child', ('Market', '__scripted_00AD__'): 'is_child', ('Market', '__scripted_029A__'): 'is_child', ('Kak Potion Shop Back', 'Kak Backyard'): 'is_adult', ('Hyrule Field', '__scripted_050F__'): 'is_child', ('Kak Windmill', '__scripted_0503__'): 'is_adult', ('GF Entrances Behind Crates', '__grotto_1D__'): 'is_adult', ('Market', 'Market Shooting Gallery'): 'is_child', ('Market', 'Market Bombchu Bowling'): 'is_child', ('Market', 'Market Treasure Chest Game'): 'is_child', ('Market', 'Market Mask Shop'): 'is_child', ('Hyrule Castle Grounds', '__scripted_007A__'): 'is_child', ('Hyrule Castle Grounds', '__scripted_047E__'): 'is_child', ('Lon Lon Ranch', '__scripted_0476__'): 'is_adult', ('Gerudo Fortress', '__scripted_03B0__'): 'is_adult', ('Temple of Time', '__scripted_058C__'): 'is_adult', ('Beyond Door of Time', '__scripted_0590__'): 'is_adult', ('Kakariko Village', '__scripted_0513__'): 'is_adult', ('Hyrule Field', '__scripted_00CD__'): 'is_child', ('Root Exits', 'Child Spawn'): 'is_child', ('Root Exits', 'Adult Spawn'): 'is_adult'}
CLOSED_EXITS: frozenset[tuple[str, str]] = frozenset({('Forest Temple Before Boss', 'Forest Temple Basement')})
AGE_ONLY_LOCATIONS: dict[str, str] = {'LH GS Lab Crate': 'is_adult', 'Market GS Guard House': 'is_child', 'Market 10 Big Poes': 'is_adult'}
AGE_ONLY_EVENTS: dict[str, str] = {'Wake Up Adult Talon': 'is_adult'}
CHILD_UNUSABLE_ITEMS: frozenset[str] = frozenset({'Hookshot', 'Longshot', 'Progressive Hookshot'})
COUNTED_UPGRADES: frozenset[str] = frozenset({'Progressive Hookshot', 'Progressive Scale', 'Progressive Wallet'})
NOTABLE_MISSING = ('Zeldas Lullaby', 'Sarias Song', 'Song of Time', 'Eponas Song', 'Suns Song', 'Song of Storms', 'Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire', 'Progressive Hookshot', 'Bomb Bag', 'Bow', 'Megaton Hammer', 'Iron Boots', 'Hover Boots', 'Lens of Truth', 'Forest Medallion', 'Fire Medallion', 'Water Medallion', 'Shadow Medallion', 'Spirit Medallion', 'Light Medallion', 'Gerudo Membership Card')
BARE_BOMBCHUS = 'Bombchus'
FOUND_BOMBCHUS = ('Bombchus (5)', 'Bombchus (10)', 'Bombchus (20)')
_MAX_DEPTH = 200

def sourced_names(world: World) -> frozenset[str]:
    names: set[str] = set(world.event_names)
    for locations in world.region_locations.values():
        for location in locations:
            if location.vanilla_item and location.type != 'Event':
                names |= set(item_grants(location.vanilla_item))
    return frozenset(names)

class Relaxer:

    def __init__(self, evaluator: RuleEvaluator, missing: frozenset[str], age: str | None=None, levels: dict[str, int] | None=None, strict_age: bool | str=False) -> None:
        self.evaluator = evaluator
        self.missing = missing
        self.levels = levels
        self.age = age
        self.strict_age = strict_age
        self._rules: dict[str, bool] = {}
        self._macros: dict[str, bool] = {}

    def holds(self, rule: str) -> bool:
        cached = self._rules.get(rule)
        if cached is None:
            cached = self._walk(self.evaluator.parse(rule), {}, 0)
            self._rules[rule] = cached
        return cached

    def _held(self, name: str) -> bool:
        if name == BARE_BOMBCHUS:
            return any((found not in self.missing for found in FOUND_BOMBCHUS))
        if name not in self.missing:
            return True
        if name == STRENGTH_UPGRADE:
            return any((glove not in self.missing for glove in RBA_STRENGTH_ITEMS))
        return False

    def _known(self, token: str) -> str | None:
        ev = self.evaluator
        resolved = ev._by_escaped.get(token)
        if resolved is None:
            spaced = ev._item_name(token)
            if spaced in ev.items or spaced in ev.events:
                resolved = spaced
        return resolved

    @staticmethod
    def _unbind(node: ast.AST, env: dict) -> tuple[ast.AST, dict]:
        while isinstance(node, ast.Name) and node.id in env:
            node, env = env[node.id]
        return (node, env)

    def _token(self, node: ast.AST, env: dict) -> str | None:
        node, _ = self._unbind(node, env)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return str(node.value)
        return None

    def _walk(self, node: ast.AST, env: dict, depth: int) -> bool:
        if depth > _MAX_DEPTH:
            return True
        ev = self.evaluator
        if isinstance(node, ast.BoolOp):
            parts = (self._walk(v, env, depth + 1) for v in node.values)
            return all(parts) if isinstance(node.op, ast.And) else any(parts)
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and (value in ev.items or value in ev.events):
                return self._held(value)
            return True
        if isinstance(node, ast.Tuple):
            token = self._token(node.elts[0], env) if node.elts else None
            if token is None:
                return True
            item = ev._by_escaped.get(token, ev._item_name(token))
            if self.levels is not None and item in COUNTED_UPGRADES and (len(node.elts) > 1):
                count, _ = self._unbind(node.elts[1], env)
                if isinstance(count, ast.Constant) and isinstance(count.value, int):
                    return self.levels.get(item, 0) >= count.value
            return self._held(item)
        if isinstance(node, ast.Name):
            if node.id in env:
                bound, bound_env = env[node.id]
                return self._walk(bound, bound_env, depth + 1)
            return self._name(node.id, depth)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return self._call(node, env, depth)
        if isinstance(node, ast.Compare):
            return self._compare(node, env)
        return True

    def _setting_value(self, node: ast.AST, env: dict) -> tuple[bool, Any]:
        node, _ = self._unbind(node, env)
        if isinstance(node, ast.Constant):
            return (True, node.value)
        if isinstance(node, ast.Name) and node.id != 'age' and (node.id in self.evaluator.settings):
            return (True, self.evaluator.settings[node.id])
        if self.strict_age and self.age and isinstance(node, ast.Name) and (node.id == 'age'):
            return (True, self.age)
        return (False, None)

    def _item_operand(self, node: ast.AST, env: dict) -> str | None:
        node, _ = self._unbind(node, env)
        if isinstance(node, ast.Name) and node.id != 'age' and (node.id not in self.evaluator.settings):
            return self._known(node.id) or node.id
        return None

    def _compare(self, node: ast.Compare, env: dict) -> bool:
        if any((not isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops)):
            return True
        operands = [node.left, *node.comparators]
        items = [self._item_operand(operand, env) for operand in operands]
        if all((item is not None for item in items)):
            for op, left, right in zip(node.ops, items, items[1:]):
                if (left == right) != isinstance(op, ast.Eq):
                    return False
            return True
        values = []
        for operand in operands:
            known, value = self._setting_value(operand, env)
            if not known:
                return True
            values.append(value)
        for op, left, right in zip(node.ops, values, values[1:]):
            if (left == right) != isinstance(op, ast.Eq):
                return False
        return True

    def _name(self, name: str, depth: int) -> bool:
        ev = self.evaluator
        if name in ev.macros:
            params, body = ev.macros[name]
            if params:
                return True
            cached = self._macros.get(name)
            if cached is None:
                self._macros[name] = True
                cached = self._walk(body, {}, depth + 1)
                if name in ('can_child_attack', 'can_child_damage'):
                    cached = cached or self._held(BQ_CHILD_SWORD)
                self._macros[name] = cached
            return cached
        if name == 'has_bottle':
            return any((self._held(bottle) for bottle in BOTTLE_ITEMS))
        resolved = self._known(name)
        if resolved is not None:
            return self._held(resolved)
        return True

    def _call(self, node: ast.Call, env: dict, depth: int) -> bool:
        ev = self.evaluator
        name = node.func.id
        if name == 'here' and node.args:
            return self._walk(node.args[0], env, depth + 1)
        if name == 'at' and len(node.args) > 1:
            return self._walk(node.args[1], env, depth + 1)
        if name == 'can_use' and node.args:
            token = self._token(node.args[0], env)
            if token is not None:
                resolved = ev._by_escaped.get(token, ev._item_name(token))
                if self.age == 'child' and resolved in CHILD_UNUSABLE_ITEMS:
                    return False
                if resolved in BQ_CHILD_USABLE:
                    return self._held(resolved)
        if name not in ev.macros:
            return True
        params, body = ev.macros[name]
        if len(params) != len(node.args):
            return True
        bound = {p: (a, env) for p, a in zip(params, node.args)}
        return self._walk(body, bound, depth + 1)

def relax_world(world: World, relaxer: Relaxer) -> World:
    strict = bool(relaxer.strict_age)
    on_items = relaxer.strict_age == 'all'
    child = Relaxer(relaxer.evaluator, relaxer.missing, 'child', relaxer.levels, strict)
    adult = Relaxer(relaxer.evaluator, relaxer.missing, 'adult', relaxer.levels, strict)
    child_items, adult_items = (child, adult)
    if strict and (not on_items):
        child_items = Relaxer(relaxer.evaluator, relaxer.missing, 'child', relaxer.levels)
        adult_items = Relaxer(relaxer.evaluator, relaxer.missing, 'adult', relaxer.levels)

    def fixed(rule: str, age: str | None=None, items: bool=False) -> str:
        as_child = age != 'is_adult' and (child_items if items else child).holds(rule)
        as_adult = age != 'is_child' and (adult_items if items else adult).holds(rule)
        if as_child and as_adult:
            return 'True'
        return 'is_child' if as_child else 'is_adult' if as_adult else 'False'
    regions: dict[str, Any] = {}
    for name, region in world.raw['regions'].items():
        exits = {}
        for key, exit_ in region['exits'].items():
            keep = name == FARORES_WIND_REGION or exit_['rule'].strip() in UNLIFTABLE_EXIT_RULES
            if (name, key) in CLOSED_EXITS:
                exits[key] = {**exit_, 'rule': 'False'}
                continue
            exits[key] = exit_ if keep else {**exit_, 'rule': fixed(exit_['rule'], AGE_ONLY_EXITS.get((name, key)))}
        copy = {**region, 'exits': exits, 'locations': {key: {**location, 'rule': fixed(location['rule'], AGE_ONLY_LOCATIONS.get(key), True)} for key, location in region['locations'].items()}, 'events': {key: fixed(rule, AGE_ONLY_EVENTS.get(key), True) for key, rule in (region.get('events') or {}).items()}}
        if 'arrival_refire' in region:
            copy['arrival_refire'] = fixed(region['arrival_refire'])
        regions[name] = copy
    return World({**world.raw, 'regions': regions})

def _pooled_levels(world: World, *pairs: tuple[Any, Any | None]) -> dict[str, int]:
    pooled: dict[str, int] = {}
    for search, discovery in pairs:
        if search is None:
            continue
        for item, level in _upgrade_levels(world, search, discovery).items():
            pooled[item] = max(pooled.get(item, 0), level)
    return pooled

def _upgrade_levels(world: World, search: Any, discovery: Any | None) -> dict[str, int]:
    levels = {item: count for item, count in search.items.items() if item in COUNTED_UPGRADES}
    counts: dict[str, int] = {}
    for location in discovery.location_cost if discovery is not None else ():
        item = discovery.location_item.get(location)
        if item:
            add_grants(counts, location, item)
    for item in COUNTED_UPGRADES:
        level = max(levels.get(item, 0), counts.get(item, 0))
        if level:
            levels[item] = level
    return levels

def item_aware_free_world(world: World, filename: str, settings: dict[str, Any] | None=None, max_passes: int=200, strict_age: bool | str=False, search_first: bool=True) -> tuple[World, frozenset[str]]:
    from .shuffle import predict_entrance_table
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    evaluator = RuleEvaluator(items=world.item_names, events=world.event_names, settings=merged)
    sourced = sourced_names(world)
    table = predict_entrance_table(filename)
    chest_table = predict_entrance_table(filename, sacred_chest_opened=True)
    missing: frozenset[str] = sourced
    levels: dict[str, int] = {}
    pooled = not search_first
    for _ in range(max_passes):
        relaxed = relax_world(world, Relaxer(evaluator, missing, levels=levels, strict_age=strict_age))
        seed_world = SeedWorld(relaxed, table['resolve'], spool_table=table['effective_spool_table'])
        search = solve(seed_world, settings=settings)
        held = {item for item, count in search.items.items() if count > 0}
        held |= search.events
        chest_world = chest_search = None
        if any((region == SKY_TEMPLE_REGION for region, _age in search.reached)):
            chest_world = SeedWorld(relaxed, chest_table['resolve'], spool_table=chest_table['effective_spool_table'])
            chest_search = solve(chest_world, settings=settings)
            held |= {item for item, count in chest_search.items.items() if count > 0}
            held |= chest_search.events
        if not pooled:
            now_missing = frozenset(sourced - held)
            now_levels = _pooled_levels(world, (search, None), (chest_search, None))
            if now_missing != missing or now_levels != levels:
                missing, levels = (now_missing, now_levels)
                continue
            pooled = True
        discovery = compute_for_filename(filename, world=relaxed, settings=settings)
        held |= set(discovery.item_cost) | set(discovery.event_cost)
        chest_discovery = None
        if chest_world is not None:
            chest_discovery = compute_for_filename(filename, world=relaxed, settings=settings, seed_world=chest_world)
            held |= set(chest_discovery.item_cost) | set(chest_discovery.event_cost)
        now_missing = frozenset(sourced - held)
        now_levels = _pooled_levels(world, (search, discovery), (chest_search, chest_discovery))
        if now_missing == missing and now_levels == levels:
            return (relaxed, missing)
        missing, levels = (now_missing, now_levels)
    raise RuntimeError(f'item-aware free world did not settle after {max_passes} passes')
