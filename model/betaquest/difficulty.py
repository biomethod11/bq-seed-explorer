from __future__ import annotations
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence
from .board import GoalScore
from .discovery import DiscoveryResult
REFERENCE_FORMAT = 'experienced two-player team, spoiler-free, three-hour blackout'
MODEL_VERSION = '2.4-provisional-v32'
_CALIBRATION_PATH = Path(__file__).resolve().parent.parent / 'data' / 'difficulty_calibration.json'

@dataclass(frozen=True)
class GoalDifficultyEstimate:
    difficulty_score: float
    difficulty_band: str
    completion_probability: float
    model_confidence: float
    confidence_label: str
    topology_search_risk: float
    intrinsic_goal_risk: float
    breadth_risk: float
    execution_risk: float
    serial_dependency_risk: float
    model_uncertainty_risk: float
    topology_percentile: float | None
    random_world_reachability_rate: float | None
    distinct_regions: int
    qualifying_checks: int
    serial_steps: int
    factors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class BoardDifficultyEstimate:
    difficulty_score: float
    difficulty_band: str
    completion_probability: float
    expected_goals_completed: float
    mean_goal_difficulty: float
    upper_quartile_goal_difficulty: float
    bottleneck_goal_difficulty: float
    workload_risk: float
    model_confidence: float
    confidence_label: str
    reference_format: str
    model_version: str
    hardest_goals: list[dict[str, Any]]
    caveats: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def difficulty_band(score: float) -> str:
    if score < 35.0:
        return 'easy'
    if score < 50.0:
        return 'medium'
    if score < 70.0:
        return 'hard'
    return 'very_hard'

def _completion_probability(score: float) -> float:
    return 1.0 / (1.0 + math.exp((score - 48.0) / 10.0))

def _confidence_label(confidence: float) -> str:
    if confidence >= 0.75:
        return 'high'
    if confidence >= 0.45:
        return 'medium'
    return 'low'

@lru_cache(maxsize=1)
def load_topology_calibration() -> dict[str, Any]:
    if not _CALIBRATION_PATH.exists():
        return {}
    return json.loads(_CALIBRATION_PATH.read_text(encoding='utf-8'))

def _interpolated_percentile(cost: float, calibration: Mapping[str, Any]) -> float | None:
    quantiles = calibration.get('cost_quantiles')
    if not quantiles:
        return None
    points = sorted(((float(key), float(value)) for key, value in quantiles.items()))
    if cost <= points[0][1]:
        return max(0.0, min(1.0, points[0][0] * cost / max(points[0][1], 1e-09)))
    for (q0, c0), (q1, c1) in zip(points, points[1:]):
        if cost <= c1:
            if c1 == c0:
                return q1
            return q0 + (q1 - q0) * (cost - c0) / (c1 - c0)
    q, boundary = points[-1]
    tail = 1.0 - math.exp(-(cost - boundary) / max(boundary, 20.0))
    return min(1.0, q + (1.0 - q) * tail)

def _used_regions(score: GoalScore, discovery: DiscoveryResult) -> set[str]:
    regions: set[str] = set()
    for evidence in score.locations_used:
        region = discovery.location_zone.get(evidence) or discovery.location_region.get(evidence)
        if region:
            regions.add(discovery.region_zone.get(region, region))
            continue
        if evidence.startswith('region: '):
            region = evidence.removeprefix('region: ').split(' (', 1)[0]
            regions.add(region)
    return regions

def _required_count(definition: Mapping[str, Any]) -> int:
    requirement = definition.get('requirement', {})
    count = requirement.get('count')
    if isinstance(count, int) and count > 0:
        return count
    if requirement.get('kind') == 'groups':
        groups = requirement.get('groups', [])
        return max(1, len(groups))
    return 1

def _execution_risk(name: str, kind: str, count: int) -> tuple[float, list[str]]:
    lowered = name.lower()
    risk = 8.0
    factors: list[str] = []
    if kind == 'sky_temple' or 'sky temple' in lowered:
        return (96.0, ['Sky Temple spawn damage, survival loadout, and three Iron Knuckles'])
    if kind == 'iron_knuckles' or 'iron knuckle' in lowered:
        risk = max(risk, 76.0)
        factors.append('multiple high-damage Iron Knuckle fights')
    if re.search('beat \\d+ dungeons', lowered):
        risk = max(risk, 82.0)
        factors.append('requires several full dungeon boss completions')
    elif any((token in lowered for token in ('ganondorf', 'bongo-bongo', 'volvagia', 'morpha', 'barinade', 'king dodongo', 'queen gohma'))):
        risk = max(risk, 58.0)
        factors.append('boss fight and its combat prerequisites')
    elif lowered.startswith(('defeat ', 'kill ', 'beat ')):
        risk = max(risk, min(65.0, 28.0 + count * 4.0))
        factors.append('combat execution is not represented by reachability alone')
    if 'silver rupee room' in lowered:
        risk = max(risk, min(70.0, 28.0 + count * 5.0))
        factors.append('room clears require navigation and puzzle execution')
    if 'unused key' in lowered:
        risk = max(risk, 42.0)
        factors.append('keys must be found while preserving enough of them unused')
    if 'both rusty switches' in lowered:
        risk = max(risk, 72.0)
        factors.append('Spirit Temple adult loadout and statue-room execution')
    if kind == 'groups':
        risk = max(risk, 24.0)
    elif kind == 'count':
        risk = max(risk, min(42.0, 12.0 + count * 2.0))
    return (min(100.0, risk), factors)

def estimate_goal_difficulty(native_goal: Mapping[str, Any], definition: Mapping[str, Any], score: GoalScore, discovery: DiscoveryResult, calibration: Mapping[str, Any] | None=None) -> GoalDifficultyEstimate:
    calibration_root = calibration if calibration is not None else load_topology_calibration()
    goal_calibration = calibration_root.get('goals', {}).get(score.name, {})
    factors: list[str] = []
    regions = _used_regions(score, discovery)
    checks = sum((1 for item in score.locations_used if item in discovery.location_region))
    required = _required_count(definition)
    checks = max(checks, required if score.satisfiable else len(score.locations_used))
    serial_steps = max(0, len(score.discovery_chain) - 1)
    if not score.satisfiable or score.cost is None:
        confidence = 0.25 if score.requirement_kind != 'unmapped' else 0.1
        reason = 'mapped goal is not currently proven reachable' if score.requirement_kind != 'unmapped' else 'goal mapping is incomplete'
        return GoalDifficultyEstimate(difficulty_score=100.0, difficulty_band='very_hard', completion_probability=0.0, model_confidence=confidence, confidence_label=_confidence_label(confidence), topology_search_risk=100.0, intrinsic_goal_risk=min(100.0, (float(native_goal.get('difficulty', score.tier)) - 1) / 24 * 100), breadth_risk=100.0, execution_risk=100.0, serial_dependency_risk=100.0 if serial_steps else 0.0, model_uncertainty_risk=100.0, topology_percentile=None, random_world_reachability_rate=goal_calibration.get('reachable_rate'), distinct_regions=len(regions), qualifying_checks=checks, serial_steps=serial_steps, factors=[reason])
    cost = float(score.cost)
    absolute_access = 100.0 * (1.0 - math.exp(-cost / 80.0))
    percentile = _interpolated_percentile(cost, goal_calibration)
    reachable_rate = goal_calibration.get('reachable_rate')
    if percentile is None:
        percentile = absolute_access / 100.0
        factors.append('goal-specific Monte Carlo calibration unavailable; absolute access curve used')
    if reachable_rate is None:
        reachable_rate = 0.75
    topology_risk = 0.65 * absolute_access + 0.25 * percentile * 100.0 + 0.1 * (1.0 - float(reachable_rate)) * 100.0
    tier = max(1.0, min(25.0, float(native_goal.get('difficulty', score.tier))))
    intrinsic_risk = (tier - 1.0) / 24.0 * 100.0
    region_breadth = 1.0 - math.exp(-max(0, len(regions) - 1) / 4.0)
    check_breadth = 1.0 - math.exp(-max(0, checks - 1) / 10.0)
    count_breadth = 1.0 - math.exp(-max(0, required - 1) / 7.0)
    breadth_risk = 100.0 * (0.5 * region_breadth + 0.3 * check_breadth + 0.2 * count_breadth)
    execution_risk, execution_factors = _execution_risk(score.name, score.requirement_kind, required)
    factors.extend(execution_factors)
    serial_risk = 100.0 * (1.0 - math.exp(-serial_steps / 2.5))
    uncertainty_risk = 8.0
    mapping_confidence = str(definition.get('confidence', 'medium')).lower()
    if mapping_confidence != 'high':
        uncertainty_risk += 15.0
        factors.append('goal uses a conservative proxy rather than a directly observable completion event')
    if score.requirement_kind in {'region', 'event'}:
        uncertainty_risk += 20.0
        factors.append('completion is represented by a region/event proxy')
    if score.requirement_kind in {'sky_temple', 'iron_knuckles'}:
        uncertainty_risk += 12.0
    if score.name in {'Defeat a Skull Kid', 'Defeat 6 different Stalfos', 'Defeat 10 different Stalfos'}:
        uncertainty_risk += 15.0
    uncertainty_risk = min(100.0, uncertainty_risk)
    human_score = 0.44 * topology_risk + 0.18 * intrinsic_risk + 0.14 * breadth_risk + 0.12 * execution_risk + 0.08 * serial_risk + 0.04 * uncertainty_risk
    maximum_component = max(topology_risk, execution_risk, serial_risk)
    human_score += 0.08 * max(0.0, maximum_component - human_score)
    human_score = max(0.0, min(100.0, human_score))
    if cost >= 120:
        factors.append(f'very high world-specific discovery workload ({cost:.1f})')
    elif cost >= 60:
        factors.append(f'high world-specific discovery workload ({cost:.1f})')
    if len(regions) >= 5:
        factors.append(f'objective is spread across {len(regions)} separately discovered regions')
    if checks >= 10:
        factors.append(f'requires at least {checks} qualifying checks')
    if serial_steps:
        factors.append(f'requires {serial_steps} serial prerequisite discoveries before the final objective')
    if percentile >= 0.9:
        factors.append(f'access is harder than about {percentile:.0%} of calibrated random worlds for this goal')
    sample_size = int(goal_calibration.get('reachable_samples', 0))
    confidence = 0.42
    if sample_size >= 64:
        confidence += 0.14
    if score.requirement_kind in {'single', 'count', 'groups'}:
        confidence += 0.08
    if mapping_confidence == 'high':
        confidence += 0.04
    else:
        confidence -= 0.08
    if uncertainty_risk >= 35:
        confidence -= 0.12
    confidence = max(0.1, min(0.72, confidence))
    probability = _completion_probability(human_score)
    return GoalDifficultyEstimate(difficulty_score=round(human_score, 3), difficulty_band=difficulty_band(human_score), completion_probability=round(probability, 5), model_confidence=round(confidence, 3), confidence_label=_confidence_label(confidence), topology_search_risk=round(topology_risk, 3), intrinsic_goal_risk=round(intrinsic_risk, 3), breadth_risk=round(breadth_risk, 3), execution_risk=round(execution_risk, 3), serial_dependency_risk=round(serial_risk, 3), model_uncertainty_risk=round(uncertainty_risk, 3), topology_percentile=round(percentile, 5), random_world_reachability_rate=round(float(reachable_rate), 5), distinct_regions=len(regions), qualifying_checks=checks, serial_steps=serial_steps, factors=factors)

def _quantile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 100.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

def estimate_board_difficulty(goal_names: Sequence[str], goals: Sequence[GoalDifficultyEstimate], two_player_makespan: float | None) -> BoardDifficultyEstimate:
    scores = [goal.difficulty_score for goal in goals]
    probabilities = [goal.completion_probability for goal in goals]
    mean = statistics.fmean(scores) if scores else 100.0
    upper_quartile = _quantile(scores, 0.75)
    upper_decile = _quantile(scores, 0.9)
    bottleneck = max(scores, default=100.0)
    workload_risk = 100.0 if two_player_makespan is None else 100.0 * (1.0 - math.exp(-float(two_player_makespan) / 450.0))
    board_score = 0.1 * mean + 0.3 * upper_quartile + 0.3 * upper_decile + 0.25 * workload_risk + 0.05 * bottleneck
    board_score = max(0.0, min(100.0, board_score))
    probability = _completion_probability(board_score)
    confidence = statistics.fmean((goal.model_confidence for goal in goals)) if goals else 0.1
    hardest = sorted(({'name': name, 'difficulty_score': goal.difficulty_score, 'completion_probability': goal.completion_probability, 'factors': goal.factors[:3]} for name, goal in zip(goal_names, goals)), key=lambda entry: (-entry['difficulty_score'], entry['name']))[:5]
    return BoardDifficultyEstimate(difficulty_score=round(board_score, 3), difficulty_band=difficulty_band(board_score), completion_probability=round(probability, 5), expected_goals_completed=round(sum(probabilities), 3), mean_goal_difficulty=round(mean, 3), upper_quartile_goal_difficulty=round(upper_quartile, 3), bottleneck_goal_difficulty=round(bottleneck, 3), workload_risk=round(workload_risk, 3), model_confidence=round(confidence, 3), confidence_label=_confidence_label(confidence), reference_format=REFERENCE_FORMAT, model_version=MODEL_VERSION, hardest_goals=hardest, caveats=['Completion percentages are model estimates, not observed frequencies.', 'The model assumes experienced players but no entrance-map spoiler.', 'Real playtest results are required to calibrate player skill and the three-hour probability curve.', 'Goal overlap and route-sharing are approximated by the aggregate workload rather than fully routed jointly.'])
