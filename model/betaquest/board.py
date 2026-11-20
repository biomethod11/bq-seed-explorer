from __future__ import annotations
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from .discovery import DiscoveryResult, compute_for_filename
from .world import World
_GOALS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'goals.json'

@dataclass(frozen=True)
class GoalScore:
    name: str
    tier: int
    requirement_kind: str
    cost: float | None
    satisfiable: bool
    locations_used: list[str]
    note: str
    base_cost: float | None = None
    discovery_chain: list[str] = field(default_factory=list)
    after_sky_chest: bool = False
GOAL_DISCOVERY_CHAINS: dict[str, list[dict[str, str]]] = {'Light Arrows': [{'kind': 'location', 'name': 'Spirit Temple Mirror Shield Chest', 'label': 'find and obtain the Mirror Shield'}, {'kind': 'event', 'name': 'Defeat Twinrova', 'label': 'find and defeat Twinrova for the Spirit Medallion'}, {'kind': 'event', 'name': 'Defeat Bongo Bongo', 'label': 'find and defeat Bongo Bongo for the Shadow Medallion'}], 'Lens of Truth': [{'kind': 'item', 'name': 'Ocarina', 'label': 'find Fairy Ocarina access'}, {'kind': 'location', 'name': 'Song from Impa', 'label': "find Zelda/Impa access and learn Zelda's Lullaby"}], 'Keaton Mask': [{'kind': 'location', 'name': 'HC Zeldas Letter', 'label': "find Zelda and obtain Zelda's Letter"}, {'kind': 'region', 'name': 'Kakariko Village', 'label': 'find Kakariko Village and show the letter to the gate guard'}], 'Skull Mask': [{'kind': 'location', 'name': 'HC Zeldas Letter', 'label': "find Zelda and obtain Zelda's Letter"}, {'kind': 'region', 'name': 'Kakariko Village', 'label': 'find the Kakariko gate guard'}, {'kind': 'location', 'name': 'Market Mask Shop Item 6', 'label': 'find the Mask Shop and obtain/sell the Keaton Mask'}], 'Spooky Mask': [{'kind': 'location', 'name': 'HC Zeldas Letter', 'label': "complete Zelda's Letter access"}, {'kind': 'region', 'name': 'Kakariko Village', 'label': 'complete the Keaton Mask sale'}, {'kind': 'location', 'name': 'Market Mask Shop Item 5', 'label': 'return for the Skull Mask'}, {'kind': 'region', 'name': 'Lost Woods', 'label': 'find the Lost Woods Skull Kid'}], 'Bunny Hood': [{'kind': 'location', 'name': 'HC Zeldas Letter', 'label': "complete Zelda's Letter access"}, {'kind': 'region', 'name': 'Kakariko Village', 'label': 'complete the Keaton Mask sale'}, {'kind': 'region', 'name': 'Lost Woods', 'label': 'complete the Skull Mask sale'}, {'kind': 'location', 'name': 'Market Mask Shop Item 8', 'label': 'return for the Spooky Mask'}, {'kind': 'region', 'name': 'Graveyard', 'label': 'find the Graveyard child and sell the Spooky Mask'}], 'Mask of Truth': [{'kind': 'location', 'name': 'HC Zeldas Letter', 'label': "complete Zelda's Letter access"}, {'kind': 'region', 'name': 'Kakariko Village', 'label': 'complete the Keaton Mask sale'}, {'kind': 'region', 'name': 'Lost Woods', 'label': 'complete the Skull Mask sale'}, {'kind': 'region', 'name': 'Graveyard', 'label': 'complete the Spooky Mask sale'}, {'kind': 'region', 'name': 'Hyrule Field', 'label': 'complete the Bunny Hood sale'}], 'Cow in House': [{'kind': 'item', 'name': 'Ocarina', 'label': 'find Fairy Ocarina access'}, {'kind': 'location', 'name': 'Song from Malon', 'label': "find Malon and learn Epona's Song"}, {'kind': 'region', 'name': 'Lon Lon Ranch', 'label': 'find Lon Lon Ranch and win the cow event'}], 'Two Fairy Spells': [{'kind': 'item', 'name': 'Ocarina', 'label': 'find Fairy Ocarina access'}, {'kind': 'location', 'name': 'Song from Impa', 'label': "find Zelda/Impa access and learn Zelda's Lullaby"}], 'Blue Potion': [{'kind': 'item', 'name': 'Odd Mushroom', 'label': "obtain the Odd Mushroom (Cojiro's trade as adult, or the Gerudo Fortress roof chest as child)"}, {'kind': 'item', 'name': 'Odd Potion', 'label': "find Granny's shop and trade her the Odd Mushroom (child needs Equip Swap)"}], 'Milk 4 Cows': [{'kind': 'item', 'name': 'Ocarina', 'label': 'find Fairy Ocarina access'}, {'kind': 'location', 'name': 'Song from Malon', 'label': "find Malon and learn Epona's Song"}], 'Plant Bean in Death Mountain Crater': [{'kind': 'location', 'name': 'ZR Magic Bean Salesman', 'label': 'find the bean salesman and buy a Magic Bean'}], 'Plant Bean in Gerudo Valley': [{'kind': 'location', 'name': 'ZR Magic Bean Salesman', 'label': 'find the bean salesman and buy a Magic Bean'}], 'Plant 3 Magic Beans': [{'kind': 'location', 'name': 'ZR Magic Bean Salesman', 'label': 'find the bean salesman and buy at least three Magic Beans'}], 'Plant 4 Magic Beans': [{'kind': 'location', 'name': 'ZR Magic Bean Salesman', 'label': 'find the bean salesman and buy at least four Magic Beans'}]}
GOAL_FINAL_DISCOVERY_LABELS = {'Light Arrows': 'find the Temple of Time as adult and trigger the Light Arrow cutscene', 'Keaton Mask': 'find the Market Mask Shop and obtain the Keaton Mask', 'Skull Mask': 'return to the Market Mask Shop and obtain the Skull Mask', 'Spooky Mask': 'return to the Market Mask Shop and obtain the Spooky Mask', 'Bunny Hood': 'return to the Market Mask Shop and obtain the Bunny Hood', 'Mask of Truth': 'return to the Market Mask Shop and obtain the Mask of Truth', 'Lens of Truth': 'find Bottom of the Well and obtain the Lens of Truth', 'Cow in House': 'find Lon Lon Ranch as adult and win the cow', 'Two Fairy Spells': 'find and activate two separately shuffled Great Fairy fountains', 'Blue Potion': "return to Granny's shop with the required wallet and buy Blue Potion", 'Milk 4 Cows': 'find and milk four cows in their separately shuffled regions', 'Plant Bean in Death Mountain Crater': 'find the Death Mountain Crater soft-soil patch and plant the bean', 'Plant Bean in Gerudo Valley': 'find the Gerudo Valley soft-soil patch and plant the bean', 'Plant 3 Magic Beans': 'find and plant three distinct soft-soil patches', 'Plant 4 Magic Beans': 'find and plant four distinct soft-soil patches'}
SKY_TEMPLE_ENTRANCE_IDS: tuple[int, ...] = (160,)
_BOTTLE_LOCATIONS = ('Kak Anju as Child', 'LLR Talons Chickens', 'LH Underwater Item', 'Market 10 Big Poes')
_FAIRY_SOURCE_LOCATIONS = ('Market Potion Shop Item 4', 'Kak Potion Shop Item 8', 'Free Fairies')

def _count_location_cost(discovery: DiscoveryResult, locations: list[str] | tuple[str, ...], count: int):
    zones: dict[str, list[tuple[float, str]]] = {}
    for location in locations:
        cost = discovery.cost_of_location(location)
        if cost is None:
            continue
        zone = discovery.location_zone.get(location) or discovery.location_region.get(location, location)
        zones.setdefault(zone, []).append((cost, location))
    if sum((len(entries) for entries in zones.values())) < count:
        return None
    dp: dict[int, tuple[float, list[str]]] = {0: (0.0, [])}
    for zone in sorted(zones):
        entries = sorted(zones[zone])
        options = [(k, entries[k - 1][0], [location for _, location in entries[:k]]) for k in range(1, len(entries) + 1)]
        updated = dict(dp)
        for have, (base_cost, base_used) in dp.items():
            for take, charge, chosen in options:
                total = min(count, have + take)
                candidate = base_cost + charge
                if total not in updated or candidate < updated[total][0]:
                    updated[total] = (candidate, base_used + chosen)
        dp = updated
    best = dp.get(count)
    if best is None:
        return None
    return (best[0], best[1])

def _heart_capacity_cost(discovery: DiscoveryResult, target_hearts: int):
    needed = (target_hearts - 3) * 4
    sources: dict[str, list[tuple[float, int, str]]] = {}
    for location, region in discovery.location_region.items():
        cost = discovery.cost_of_location(location)
        if cost is None:
            continue
        item = discovery.location_item.get(location)
        units = 4 if item == 'Heart Container' else 1 if item == 'Piece of Heart' else 0
        if units:
            zone = discovery.location_zone.get(location, region)
            sources.setdefault(zone, []).append((cost, units, location))
    dp: dict[int, tuple[float, list[str]]] = {0: (0.0, [])}
    for entries in sources.values():
        entries.sort()
        options = [(0, 0.0, [])]
        units = 0
        used = []
        for cost, value, location in entries:
            units += value
            used = used + [location]
            options.append((units, cost, used))
        updated = dict(dp)
        for have, (base_cost, base_used) in dp.items():
            for add, cost, chosen in options[1:]:
                total = min(needed, have + add)
                candidate = (base_cost + cost, base_used + chosen)
                if total not in updated or candidate[0] < updated[total][0]:
                    updated[total] = candidate
        dp = updated
    return dp.get(needed)

def _sky_temple_evidence(discovery: DiscoveryResult, entrances=SKY_TEMPLE_ENTRANCE_IDS):
    access = min(((cost, entrance) for entrance in entrances if (cost := discovery.cost_of_entrance(entrance)) is not None)) if any((discovery.cost_of_entrance(entrance) is not None for entrance in entrances)) else None
    if access is None:
        return None
    fairy_source = _count_location_cost(discovery, _FAIRY_SOURCE_LOCATIONS, 1)
    survival_options = []
    five_hearts = _heart_capacity_cost(discovery, 5)
    if five_hearts:
        survival_options.append((five_hearts[0], ['5-heart capacity'] + five_hearts[1]))
    two_bottles = _count_location_cost(discovery, _BOTTLE_LOCATIONS, 2)
    if two_bottles and fairy_source:
        survival_options.append((two_bottles[0] + fairy_source[0], ['two bottled fairies'] + two_bottles[1] + fairy_source[1]))
    nayru, magic = (discovery.cost_of_item('Nayrus Love'), discovery.cost_of_item('Magic Meter'))
    if nayru is not None and magic is not None:
        survival_options.append((nayru + magic, ["Nayru's Love with magic"]))
    if not survival_options:
        return None
    survival_cost, used = min(survival_options, key=lambda option: option[0])
    return (access[0] + survival_cost, [f'entrance: 0x{access[1]:04X}'] + used)
for _sword_goal in ('3 Swords & 3 Tunics', '3 Swords & 3 Shields', '3 Swords & 3 Boots', '3 Swords, Tunics, Boots and Shields'):
    GOAL_DISCOVERY_CHAINS[_sword_goal] = [{'kind': 'region', 'name': 'Temple of Time', 'label': 'find the Temple of Time and pull the Master Sword'}]
    GOAL_FINAL_DISCOVERY_LABELS[_sword_goal] = 'collect the remaining sword and equipment checks'
GOAL_DISCOVERY_CHAINS['Milk'] = GOAL_DISCOVERY_CHAINS['Milk 4 Cows']
GOAL_FINAL_DISCOVERY_LABELS['Milk'] = 'find and milk a cow'
GOAL_DISCOVERY_CHAINS['Defeat Ganondorf'] = [*GOAL_DISCOVERY_CHAINS['Light Arrows'], {'kind': 'location', 'name': 'ToT Light Arrows Cutscene', 'label': 'return to the Temple of Time for the Light Arrows'}]
GOAL_FINAL_DISCOVERY_LABELS['Defeat Ganondorf'] = 'find Ganondorf and defeat him'

def serial_charges(costs: list[float], back: float) -> list[float]:
    charges: list[float] = []
    walked = 0.0
    for cost in costs:
        charge = cost - walked if cost >= walked else back * cost
        charges.append(charge)
        walked += charge
    return charges

def walk_back_ratio(discovery: DiscoveryResult) -> float:
    return discovery.weights.internal_step_cost / discovery.weights.step_cost

def chain_charges(base_cost: float, locations_used: list[str], step_costs: list[float], discovery: DiscoveryResult) -> list[float]:
    back = walk_back_ratio(discovery)
    if len(locations_used) == 1:
        return serial_charges(step_costs + [base_cost], back)
    return serial_charges(step_costs, back) + [base_cost]

def _apply_discovery_chain(score: GoalScore, discovery: DiscoveryResult) -> GoalScore:
    chain = GOAL_DISCOVERY_CHAINS.get(score.name)
    if not chain or score.cost is None:
        return score
    costs: list[float] = []
    labels: list[str] = []
    for step in chain:
        cost = chain_step_cost(step, discovery)
        if cost is None:
            return GoalScore(name=score.name, tier=score.tier, requirement_kind=score.requirement_kind, cost=None, satisfiable=False, locations_used=score.locations_used, note=f"serial prerequisite unreachable: {step['label']}", base_cost=score.cost, discovery_chain=labels + [step['label']])
        costs.append(cost)
        labels.append(step['label'])
    labels.append(GOAL_FINAL_DISCOVERY_LABELS.get(score.name, f'complete the final check: {score.name}'))
    return GoalScore(name=score.name, tier=score.tier, requirement_kind=score.requirement_kind, cost=sum(chain_charges(score.cost, score.locations_used, costs, discovery)), satisfiable=True, locations_used=score.locations_used, note=score.note, base_cost=score.cost, discovery_chain=labels)

def chain_step_cost(step: dict[str, str], discovery: DiscoveryResult) -> float | None:
    if step['kind'] == 'location':
        return discovery.cost_of_location(step['name'])
    if step['kind'] == 'event':
        return discovery.cost_of_event(step['name'])
    if step['kind'] == 'item':
        return discovery.cost_of_item(step['name'])
    return discovery.cost_of_region(step['name'])

@lru_cache(maxsize=1)
def load_goal_definitions() -> list[dict]:
    return json.loads(_GOALS_PATH.read_text(encoding='utf-8'))

def _cheaper_of_chain_or_direct(goal: dict, discovery: DiscoveryResult) -> GoalScore:
    req = goal['requirement']
    direct = req['unchained_locations']
    chained = score_goal({**goal, 'requirement': {'kind': req['kind'], 'count': req['count'], 'locations': [loc for loc in req['locations'] if loc not in direct]}}, discovery)
    costs = sorted(((cost, loc) for loc in direct if (cost := discovery.cost_of_location(loc)) is not None))
    if costs and (chained.cost is None or costs[0][0] < chained.cost):
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=req['kind'], cost=costs[0][0], satisfiable=True, locations_used=[costs[0][1]], note=goal['note'], base_cost=costs[0][0])
    return chained

def score_goal(goal: dict, discovery: DiscoveryResult, sky_temple_beaten: bool=False) -> GoalScore:
    req = goal['requirement']
    kind = req['kind']
    if kind == 'unmapped':
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[], note='goal has no location mapping yet -- see data/goals.json')
    if kind == 'sky_temple':
        if sky_temple_beaten:
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=0.0, satisfiable=True, locations_used=['beaten before the chest'], note=goal['note'])
        evidence = _sky_temple_evidence(discovery, tuple(req.get('entrances', SKY_TEMPLE_ENTRANCE_IDS)))
        if evidence is None:
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[], note="Sky Temple's per-seed sacred grotto or a survival loadout (5 hearts, two bottled fairies, or Nayru's Love with magic) is unreachable")
        cost, used = evidence
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=cost, satisfiable=True, locations_used=used, note=goal['note'])
    if kind == 'heart_capacity':
        result = _heart_capacity_cost(discovery, req.get('count') or 0)
        if result is None:
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[], note=f"fewer than {req.get('count')} hearts are provably reachable")
        cost, used = result
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=cost, satisfiable=True, locations_used=used, note=goal['note'])
    if kind in ('iron_knuckles', 'stalfos', 'white_wolfos'):
        sources = []
        for evidence in req.get('evidence', []):
            if evidence.get('regions'):
                costs = sorted(((cost, region) for region in evidence['regions'] if (cost := discovery.cost_of_region(region)) is not None))
                if costs:
                    sources.append((costs[0][0], evidence['units'], evidence['name'], [f'region: {costs[0][1]}']))
                continue
            if evidence.get('survival') == 'sky_temple':
                if sky_temple_beaten:
                    sources.append((0.0, evidence['units'], evidence['name'], ['beaten before the chest']))
                    continue
                result = _sky_temple_evidence(discovery, tuple(evidence.get('entrances', SKY_TEMPLE_ENTRANCE_IDS)))
                if result:
                    sources.append((result[0], evidence['units'], evidence['name'], result[1]))
                continue
            result = _count_location_cost(discovery, evidence.get('locations', []), 1)
            if result:
                sources.append((result[0], evidence['units'], evidence['name'], result[1]))
        needed = req.get('count') or 1
        dp: dict[int, tuple[float, list[str]]] = {0: (0.0, [])}
        for cost, units, label, used in sources:
            updated = dict(dp)
            for have, (base_cost, base_used) in dp.items():
                total = min(needed, have + units)
                candidate = (base_cost + cost, base_used + [label] + used)
                if total not in updated or candidate[0] < updated[total][0]:
                    updated[total] = candidate
            dp = updated
        if needed not in dp:
            enemy = {'iron_knuckles': 'Iron Knuckles', 'stalfos': 'Stalfos', 'white_wolfos': 'White Wolfos'}[kind]
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[], note=f'fewer than {needed} distinct {enemy} are provably reachable')
        cost, used = dp[needed]
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=cost, satisfiable=True, locations_used=used, note=goal['note'])
    if kind == 'region':
        age = req.get('age')
        costs = []
        for region in req.get('regions', []):
            cost = discovery.cost_of_region(region, age=age)
            if cost is not None:
                costs.append((cost, region))
        costs.sort()
        needed = req.get('count') or 1
        if len(costs) < needed:
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[f'region: {region}' for _, region in costs], note=f"only {len(costs)}/{needed} required regions reachable as {age or 'either age'}")
        used = costs[:needed]
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=used[-1][0], satisfiable=True, locations_used=[f'region: {region}' for _, region in used], note=goal['note'])
    if kind == 'event':
        costs = [(cost, event) for event in req.get('events', []) if (cost := discovery.cost_of_event(event)) is not None]
        costs.sort()
        needed = req.get('count') or 1
        if len(costs) < needed:
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[f'event: {event}' for _, event in costs], note=f'only {len(costs)}/{needed} required events reached')
        used = costs[:needed]
        return _apply_discovery_chain(GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=sum((cost for cost, _ in used)), satisfiable=True, locations_used=[f'event: {event}' for _, event in used], note=goal['note']), discovery)
    if kind == 'groups':
        completed = []
        for group in req.get('groups', []):
            within = group.get('count') or 1
            if group.get('locations'):
                result = _count_location_cost(discovery, group['locations'], within)
                if result:
                    cost, used = result
                    if group.get('access_event'):
                        ready = discovery.cost_of_event(group['access_event'])
                        if ready is None:
                            continue
                        cost = max(cost, ready)
                        used = used + [f"event: {group['access_event']}"]
                    completed.append((cost, group['name'], used))
            elif group.get('regions'):
                costs = sorted(((cost, region) for region in group['regions'] if (cost := discovery.cost_of_region(region, age=group.get('age'))) is not None))
                if len(costs) >= within:
                    used = costs[:within]
                    completed.append((sum((cost for cost, _ in used)), group['name'], [f"region: {region} ({group.get('age') or 'either'})" for _, region in used]))
            elif group.get('events'):
                costs = sorted(((cost, event) for event in group['events'] if (cost := discovery.cost_of_event(event)) is not None))
                if len(costs) >= within:
                    used = costs[:within]
                    completed.append((sum((cost for cost, _ in used)), group['name'], [f'event: {event}' for _, event in used]))
        completed.sort()
        needed = req.get('count') or len(req.get('groups', []))
        if len(completed) < needed:
            return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[name for _, name, _ in completed], note=f'only {len(completed)}/{needed} required groups completable')
        used_groups = completed[:needed]
        return _apply_discovery_chain(GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=sum((cost for cost, _, _ in used_groups)), satisfiable=True, locations_used=[loc for _, _, locs in used_groups for loc in locs], note=goal['note']), discovery)
    if req.get('unchained_locations'):
        return _cheaper_of_chain_or_direct(goal, discovery)
    costs = []
    for loc in req['locations']:
        c = discovery.cost_of_location(loc)
        if c is not None:
            costs.append((c, loc))
    costs.sort()
    needed = req['count'] or 1
    if len(costs) < needed:
        return GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=None, satisfiable=False, locations_used=[loc for _, loc in costs], note=f'only {len(costs)}/{needed} required locations reachable on this seed')
    chosen = _count_location_cost(discovery, req['locations'], needed)
    cost, used = chosen if chosen is not None else (costs[needed - 1][0], [loc for _, loc in costs[:needed]])
    return _apply_discovery_chain(GoalScore(name=goal['name'], tier=goal['tier'], requirement_kind=kind, cost=cost, satisfiable=True, locations_used=used, note=goal['note'], base_cost=cost), discovery)

@dataclass
class BoardScore:
    filename: str
    goals: list[GoalScore]
    solo_cost: float | None
    unsatisfiable: list[GoalScore] = field(default_factory=list)

    @property
    def is_possible(self) -> bool:
        return len(self.unsatisfiable) == 0

    def workload_split(self, n_players: int=2) -> 'WorkloadSplit':
        return split_workload(self.goals, n_players)

def score_board(filename: str, goal_names: list[str], world: World | None=None, discovery: DiscoveryResult | None=None, settings: dict[str, Any] | None=None) -> BoardScore:
    world = world or World.load()
    discovery = discovery or compute_for_filename(filename, world=world, settings=settings)
    definitions = {g['name']: g for g in load_goal_definitions()}
    scores = []
    for name in goal_names:
        if name not in definitions:
            raise KeyError(f'unknown goal name: {name!r}')
        scores.append(score_goal(definitions[name], discovery))
    unsatisfiable = [s for s in scores if not s.satisfiable]
    solo_cost = None if unsatisfiable else max((s.cost for s in scores), default=0.0)
    return BoardScore(filename=filename, goals=scores, solo_cost=solo_cost, unsatisfiable=unsatisfiable)
SKY_CHEST_STEP = 'beat the Sky Temple, open its chest, then save and reset'

def rescore_after_sky_chest(board: BoardScore, goal_names: list[str], discovery: DiscoveryResult, chest_open_discovery: Callable[[], DiscoveryResult], reaches_more: Callable[[DiscoveryResult], bool] | None=None) -> tuple[BoardScore, DiscoveryResult | None]:
    if not board.unsatisfiable:
        return (board, None)
    fight = _sky_temple_evidence(discovery)
    if fight is None:
        return (board, None)
    if reaches_more is not None and (not reaches_more(discovery)):
        return (board, None)
    fight_cost, fight_used = fight
    opened = chest_open_discovery()
    definitions = {g['name']: g for g in load_goal_definitions()}
    scores = []
    for name, fresh in zip(goal_names, board.goals):
        if fresh.satisfiable and fresh.cost is not None:
            scores.append(fresh)
            continue
        after = score_goal(definitions[name], opened, sky_temple_beaten=True)
        if not after.satisfiable or after.cost is None:
            scores.append(fresh)
            continue
        chain = after.discovery_chain or [GOAL_FINAL_DISCOVERY_LABELS.get(name, f'complete the final check: {name}')]
        scores.append(GoalScore(name=after.name, tier=after.tier, requirement_kind=after.requirement_kind, cost=fight_cost + after.cost, satisfiable=True, locations_used=['Sky Temple chest first'] + fight_used + after.locations_used, note=after.note, base_cost=after.base_cost if after.base_cost is not None else after.cost, discovery_chain=[SKY_CHEST_STEP] + chain, after_sky_chest=True))
    unsatisfiable = [s for s in scores if not s.satisfiable]
    solo_cost = None if unsatisfiable else max((s.cost for s in scores), default=0.0)
    return (BoardScore(filename=board.filename, goals=scores, solo_cost=solo_cost, unsatisfiable=unsatisfiable), opened)

@dataclass
class WorkloadSplit:
    player_a: list[GoalScore]
    player_b: list[GoalScore]
    makespan: float | None

    @property
    def cost_a(self) -> float:
        return sum((g.cost for g in self.player_a if g.cost is not None))

    @property
    def cost_b(self) -> float:
        return sum((g.cost for g in self.player_b if g.cost is not None))

def split_workload(goals: list[GoalScore], n_players: int=2) -> WorkloadSplit:
    if n_players != 2:
        raise NotImplementedError('only the 2-player split is implemented')
    satisfiable = sorted((g for g in goals if g.cost is not None), key=lambda g: -g.cost)
    bins: list[list[GoalScore]] = [[], []]
    totals = [0.0, 0.0]
    for g in satisfiable:
        lighter = 0 if totals[0] <= totals[1] else 1
        bins[lighter].append(g)
        totals[lighter] += g.cost
    unsatisfiable_present = any((g.cost is None for g in goals))
    makespan = None if unsatisfiable_present else max(totals)
    return WorkloadSplit(player_a=bins[0], player_b=bins[1], makespan=makespan)
