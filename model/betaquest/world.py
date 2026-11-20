from __future__ import annotations
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Iterator
_GRAPH_PATH = Path(__file__).resolve().parent.parent / 'data' / 'world_graph.json'
EPONA_SCENES = frozenset({'Hyrule Field', 'Lon Lon Ranch', 'Lake Hylia', 'Gerudo Valley', 'Gerudo Fortress'})
MOUNTED_SUFFIX = ' (on Epona)'
REMEMBERING_SUFFIX = ' (remembering Epona)'
VANILLA_ITEM_GRANTS: dict[str, dict[str, int]] = {'Bomb Bag': {'Bombs': 1}, 'Buy Magic Bean': {'Magic Bean': 10}, 'Buy Hylian Shield': {'Hylian Shield': 1}, 'Buy Deku Shield': {'Deku Shield': 1}, 'Deku Shield Drop': {'Deku Shield': 1}, 'RBA Water Temple Keys': {'Small Key (Water Temple)': 29}}

def item_grants(vanilla_item: str) -> dict[str, int]:
    grants = {vanilla_item: 1}
    for item, count in VANILLA_ITEM_GRANTS.get(vanilla_item, {}).items():
        grants[item] = max(grants.get(item, 0), count)
    return grants
UPGRADE_LEVELS: dict[str, int] = {'Graveyard Dampe Race Hookshot Chest': 1, 'Water Temple Longshot Chest': 2, 'GC Darunias Joy': 1, 'Spirit Temple Silver Gauntlets Chest': 2, 'Ganons Castle Shadow Trial Golden Gauntlets Chest': 3, 'ZD Diving Minigame': 1, 'LH Adult Fishing': 2, 'Kak 10 Gold Skulltula Reward': 1, 'Kak 30 Gold Skulltula Reward': 2}

def add_grants(items: Any, location_name: str, vanilla_item: str) -> list[str]:
    level = UPGRADE_LEVELS.get(location_name)
    if level is not None:
        items[vanilla_item] = max(items.get(vanilla_item, 0), level)
        return [vanilla_item]
    grants = item_grants(vanilla_item)
    for item, count in grants.items():
        items[item] = items.get(item, 0) + count
    return list(grants)

@dataclass(frozen=True)
class Exit:
    name: str
    dest_region: str
    rule: str
    index: int | None
    spool_slot: int | None = None
    same_index_dest_region: str | None = None
    refire_of: 'Exit | None' = None
    refire_ids: tuple[int, ...] = ()
    ride: bool = False
    mounted_of: 'Exit | None' = None
    age_after: str | None = None

    def arrival_age(self, age: str) -> str:
        if self.age_after == 'swap':
            return 'adult' if age == 'child' else 'child'
        return self.age_after or age

    @property
    def is_shuffled(self) -> bool:
        return self.index is not None or self.spool_slot is not None

@dataclass(frozen=True)
class Location:
    name: str
    rule: str
    type: str | None
    vanilla_item: str | None
    alternate: bool = False
    walk_steps: int = 0

class World:

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.meta: dict[str, Any] = raw['meta']
        self.spawn_indices: dict[str, int] = raw['spawn_indices']
        self.entrances: dict[int, dict] = {int(k): v for k, v in raw['entrances'].items()}
        self.regions: dict[str, dict] = raw['regions']
        self._add_remembering_regions()
        self.region_exits: dict[str, list[Exit]] = {}
        self.region_locations: dict[str, list[Location]] = {}
        for name, region in self.regions.items():
            self.region_exits[name] = [Exit(name=dest, dest_region=dest, rule=info['rule'], index=info['index'], spool_slot=info.get('spool_slot'), same_index_dest_region=info.get('same_index_dest_region'), ride=bool(info.get('ride')), age_after=info.get('age_after')) for dest, info in region['exits'].items()]
            self.region_locations[name] = [Location(name=loc_name, rule=info['rule'], type=info.get('type'), vanilla_item=info.get('vanilla_item'), alternate=bool(info.get('alternate_of')), walk_steps=info.get('walk_steps', 0)) for loc_name, info in region['locations'].items()]

    @classmethod
    def load(cls, path: Path | None=None) -> 'World':
        path = path or _GRAPH_PATH
        return cls(json.loads(path.read_text(encoding='utf-8')))

    @cached_property
    def item_names(self) -> set[str]:
        names = {loc.vanilla_item for locs in self.region_locations.values() for loc in locs if loc.vanilla_item}
        names |= {'Bombs', 'Nuts', 'Sticks', 'Bombchus', 'Arrows', 'Magic Meter', 'Ocarina', 'Bottle', 'Scarecrow', 'Distant Scarecrow', 'Progressive Wallet', 'Progressive Scale', 'Progressive Strength Upgrade', 'Progressive Hookshot', 'Deku Shield', 'Hylian Shield', 'Fairy', 'Magic Bean'}
        return {n for n in names if n}

    @cached_property
    def event_names(self) -> set[str]:
        names: set[str] = set()
        for region in self.regions.values():
            names |= set(region.get('events') or {})
        for locs in self.region_locations.values():
            for loc in locs:
                if loc.type == 'Event' and loc.vanilla_item:
                    names.add(loc.vanilla_item)
        return names

    def region_events(self, region: str) -> dict[str, str]:
        return self.regions[region].get('events') or {}

    def dest_region_of_index(self, index: int) -> str | None:
        record = self.entrances.get(index)
        return record['dest_region'] if record else None

    def is_coarse(self, index: int) -> bool:
        record = self.entrances.get(index)
        return bool(record and record.get('coarse'))

    def mounted_region_of(self, area: str) -> str | None:
        return self._mounted_regions.get(area)

    @cached_property
    def _mounted_regions(self) -> dict[str, str]:
        return {region['mounted_of']: name for name, region in self.regions.items() if region.get('mounted_of')}

    def is_mounted(self, region: str | None) -> bool:
        return bool(region and (self.regions.get(region) or {}).get('mounted_of'))

    def _add_remembering_regions(self) -> None:
        horse = self._epona_scene_regions_of(self.regions, self.raw['entrances'])
        for name, region in list(self.regions.items()):
            if name in horse or region.get('mounted_of') or region.get('remembering_of'):
                continue
            if name.endswith(REMEMBERING_SUFFIX):
                continue
            copy = {key: value for key, value in region.items() if key not in ('exits', 'locations', 'events', 'arrival_refire')}
            copy.update(exits={}, locations={}, events={}, remembering_of=name)
            self.regions[name + REMEMBERING_SUFFIX] = copy
        self.epona_scene_regions = frozenset(horse)

    @staticmethod
    def _epona_scene_regions_of(regions: dict, entrances: dict) -> set[str]:
        scene: dict[str, str] = {}
        for record in entrances.values():
            dest = record.get('dest_region')
            if dest in regions and record.get('scene') not in (None, '?'):
                scene.setdefault(dest, record['scene'])
        changed = True
        while changed:
            changed = False
            for name, region in regions.items():
                if name not in scene or region.get('mounted_of'):
                    continue
                for dest, info in region['exits'].items():
                    if info.get('index') is None and dest in regions and (dest not in scene):
                        scene[dest] = scene[name]
                        changed = True
        return {name for name, value in scene.items() if value in EPONA_SCENES and (not regions[name].get('mounted_of'))}

    def remembering_region_of(self, region: str) -> str | None:
        name = region + REMEMBERING_SUFFIX
        return name if name in self.regions else None

    def is_remembering(self, region: str | None) -> bool:
        return bool(region and (self.regions.get(region) or {}).get('remembering_of'))

    def is_state_copy(self, region: str | None) -> bool:
        return self.is_mounted(region) or self.is_remembering(region)

    def is_sink(self, region: str) -> bool:
        return bool(self.regions.get(region, {}).get('sink'))

    def __iter__(self) -> Iterator[str]:
        return iter(self.regions)
MAX_REFIRE_HOPS = 32

class SeedWorld:

    def __init__(self, world: World, resolve: Callable[[int], dict], spool_table: list[int] | None=None) -> None:
        self.world = world
        self._resolve = resolve
        self._spool_table = spool_table
        self._dest_cache: dict[int, str | None] = {}
        self._spool_dest_cache: dict[int, str | None] = {}
        self._actual_cache: dict[int, int] = {}
        self._refire_exits: dict[str, list[Exit]] | None = None
        self._exits_cache: dict[str, tuple[Exit, ...]] = {}
        self._beyond_cache: tuple[SeedWorld, dict[str, tuple[tuple[Exit, tuple[str, ...]], ...]]] | None = None

    def destinations_beyond(self, other: SeedWorld, region: str) -> tuple[tuple[Exit, tuple[str, ...]], ...]:
        if self._beyond_cache is None or self._beyond_cache[0] is not other:
            self._beyond_cache = (other, {})
        found = self._beyond_cache[1].get(region)
        if found is None:
            static = len(self.world.region_exits.get(region, ()))

            def edges(world: SeedWorld) -> dict[tuple, tuple[Exit, tuple[str, ...]]]:
                exits = world.exits_from(region)
                out = {}
                for position, e in enumerate(exits):
                    if position >= static or e.index is not None or e.spool_slot is not None:
                        dests = world.exit_destinations(e)
                        out[e.name, e.rule, e.age_after, dests] = (e, dests)
                return out
            mine, theirs = (edges(self), edges(other))
            found = tuple((edge for key, edge in mine.items() if key not in theirs))
            self._beyond_cache[1][region] = found
        return found

    def exits_from(self, region: str) -> tuple[Exit, ...]:
        if self._refire_exits is None:
            self._refire_exits = self._build_refire_exits()
            for build in (self._build_mounted_exits, self._build_remembering_exits):
                for source, edges in build().items():
                    self._refire_exits.setdefault(source, []).extend(edges)
        cached = self._exits_cache.get(region)
        if cached is None:
            static = self.world.region_exits.get(region, ())
            extra = self._refire_exits.get(region)
            cached = tuple(static) + tuple(extra) if extra else tuple(static)
            self._exits_cache[region] = cached
        return cached

    def _build_mounted_exits(self) -> dict[str, list[Exit]]:
        out: dict[str, list[Exit]] = {}
        field = self.world.mounted_region_of('Hyrule Field')
        if field is None:
            return out
        for source, exits in self.world.region_exits.items():
            for exit_ in exits:
                if exit_.index is None or exit_.spool_slot is not None:
                    continue
                record = self.world.entrances.get(self.exit_resolved_entrance(exit_)) or {}
                if record.get('epona_spawn'):
                    target = field
                elif exit_.ride:
                    target = record.get('mounted_region')
                else:
                    continue
                if not target:
                    continue
                out.setdefault(source, []).append(Exit(name=f'__epona_{exit_.index:04X}__', dest_region=target, rule=f'is_adult and ({exit_.rule})', index=None, mounted_of=exit_))
        return out

    def _build_remembering_exits(self) -> dict[str, list[Exit]]:
        world = self.world
        out: dict[str, list[Exit]] = {}
        field = world.mounted_region_of('Hyrule Field')
        horse = world.epona_scene_regions

        def landing(exit_: Exit, dest: str) -> str | None:
            if dest not in horse:
                return world.remembering_region_of(dest)
            if not exit_.is_shuffled:
                return world.mounted_region_of(dest) or dest
            record = world.entrances.get(self.exit_resolved_entrance(exit_)) or {}
            if record.get('epona_spawn'):
                return field
            return record.get('mounted_region') or dest

        def edge(source: str, exit_: Exit, target: str) -> None:
            tag = f'{exit_.index:04X}' if exit_.index is not None else exit_.name
            out.setdefault(source, []).append(Exit(name=f'__epona_mem_{tag}__', dest_region=target, rule=f'is_adult and ({exit_.rule})', index=None, mounted_of=exit_))
        for source, exits in world.region_exits.items():
            if world.is_mounted(source):
                for exit_ in exits:
                    if not exit_.ride or exit_.index is None:
                        continue
                    for dest in self.exit_destinations(exit_):
                        if dest in world.regions and dest not in horse:
                            target = world.remembering_region_of(dest)
                            if target:
                                edge(source, exit_, target)
                continue
            ghost = world.remembering_region_of(source)
            if ghost is None:
                continue
            for exit_ in exits:
                if exit_.name.startswith(('__save_reset', '__death_reset')):
                    continue
                if exit_.dest_region == 'Farores Wind Warp':
                    continue
                for dest in self.exit_destinations(exit_):
                    if dest not in world.regions or world.is_sink(dest):
                        continue
                    target = landing(exit_, dest)
                    if target:
                        edge(ghost, exit_, target)
        return out

    def _build_refire_exits(self) -> dict[str, list[Exit]]:
        out: dict[str, list[Exit]] = {}
        for source, exits in self.world.region_exits.items():
            for exit_ in exits:
                if exit_.index is None:
                    continue
                death = exit_.name.startswith('__death_reset')
                save = exit_.name.startswith('__save_reset')
                arrival = self.exit_resolved_entrance(exit_)
                landing = self.exit_destination(exit_)
                rule = exit_.rule
                fired: list[int] = []
                for _ in range(MAX_REFIRE_HOPS):
                    record = self.world.entrances.get(arrival) or {}
                    if record.get('type') == 'Grotto' or record.get('unmodeled_sink'):
                        break
                    if arrival in fired:
                        break
                    death_rule = (self.world.regions.get(landing) or {}).get('arrival_refire')
                    if death_rule is None:
                        break
                    target = self.resolved_dest(arrival)
                    if target is None:
                        break
                    if death_rule != 'True':
                        rule = f'({rule}) and ({death_rule})'
                    fired.append(arrival)
                    out.setdefault(source, []).append(Exit(name=(f'__refire_death_{exit_.index:04X}' if death else f'__refire_save_{exit_.index:04X}' if save else f'__refire_{exit_.index:04X}') + ('__' if len(fired) == 1 else f'_x{len(fired)}__'), dest_region=target, rule=rule, index=None, refire_of=exit_, refire_ids=tuple(fired), age_after=exit_.age_after))
                    landing = target
                    arrival = self.resolved_entrance(arrival)
        return out

    def resolved_entrance(self, index: int) -> int:
        if index not in self._actual_cache:
            self._actual_cache[index] = self._resolve(index)['result_entrance_id']
        return self._actual_cache[index]

    def resolved_dest(self, index: int) -> str | None:
        if index not in self._dest_cache:
            actual = self.resolved_entrance(index)
            self._dest_cache[index] = self.world.dest_region_of_index(actual)
        return self._dest_cache[index]

    def resolved_spool_entrance(self, slot: int) -> int:
        return self._spool_table[slot]

    def resolved_dest_via_spool(self, slot: int) -> str | None:
        if slot not in self._spool_dest_cache:
            actual = self.resolved_spool_entrance(slot)
            self._spool_dest_cache[slot] = self.world.dest_region_of_index(actual)
        return self._spool_dest_cache[slot]

    def exit_resolved_entrance(self, exit_: Exit) -> int | None:
        if exit_.spool_slot is not None and self._spool_table is not None:
            return self.resolved_spool_entrance(exit_.spool_slot)
        if exit_.index is not None:
            return self.resolved_entrance(exit_.index)
        return None

    def exit_destination(self, exit_: Exit) -> str | None:
        actual = self.exit_resolved_entrance(exit_)
        if exit_.same_index_dest_region is not None and actual == exit_.index:
            return exit_.same_index_dest_region
        if exit_.spool_slot is not None and self._spool_table is not None:
            return self.resolved_dest_via_spool(exit_.spool_slot)
        if not exit_.is_shuffled:
            return exit_.dest_region
        return self.resolved_dest(exit_.index)

    def exit_destinations(self, exit_: Exit) -> tuple[str, ...]:
        primary = self.exit_destination(exit_)
        if primary is None:
            return ()
        destinations = [primary]
        arrival = self.exit_resolved_entrance(exit_)
        seen: set[int] = set()
        while arrival is not None and arrival not in seen:
            seen.add(arrival)
            record = self.world.entrances.get(arrival) or {}
            is_grotto = record.get('type') == 'Grotto' or (record.get('coarse') and record.get('scene') == 'Grottos' and record.get('unmodeled_sink'))
            if not is_grotto:
                break
            resolution = self._resolve(arrival)
            if resolution.get('grotto_case'):
                break
            next_arrival = resolution.get('result_entrance_id')
            if not isinstance(next_arrival, int) or next_arrival == arrival:
                break
            next_dest = self.world.dest_region_of_index(next_arrival)
            if next_dest is None:
                break
            if next_dest not in destinations:
                destinations.append(next_dest)
            arrival = next_arrival
        return tuple(destinations)

    def start_region(self, age: str='child') -> str | None:
        return self.resolved_dest(self.world.spawn_indices[age])
