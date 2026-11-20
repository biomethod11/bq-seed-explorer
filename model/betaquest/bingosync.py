from __future__ import annotations
import atexit
import json
import shutil
import statistics
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from .board import GOAL_DISCOVERY_CHAINS, GOAL_FINAL_DISCOVERY_LABELS, BoardScore, load_goal_definitions, rescore_after_sky_chest, score_board
from .discovery import compute_for_filename, reaches_beyond, seed_world_for_filename
from .difficulty import BoardDifficultyEstimate, GoalDifficultyEstimate, estimate_board_difficulty, estimate_goal_difficulty
from .shuffle import predict_entrance_table
from .world import World
_ROOT = Path(__file__).resolve().parent.parent
_RUNNER = _ROOT / 'data' / 'sources' / 'run_bingosync_betaquest.js'
_SERVER_RUNNER = _ROOT / 'data' / 'sources' / 'run_bingosync_betaquest_server.js'
_GENERATOR = _ROOT / 'data' / 'sources' / 'ocarina_of_time_beta_quest_generator.js'
_GENERATOR_BASE = _ROOT / 'data' / 'sources' / 'generators' / 'generator_bases' / 'srl_generator_v5_blackout.js'
DISCOVERY_CHAINS = {goal: [step['label'] for step in steps] + [GOAL_FINAL_DISCOVERY_LABELS.get(goal, f'complete the final check: {goal}')] for goal, steps in GOAL_DISCOVERY_CHAINS.items()}

def canonical_seed(seed: int | str) -> int:
    if isinstance(seed, str):
        if not seed.isascii() or not seed.isdecimal():
            raise ValueError('seed must contain decimal digits only')
        seed = int(seed)
    if isinstance(seed, bool) or not isinstance(seed, int) or (not 1 <= seed <= 999999):
        raise ValueError('seed must be an integer from 1 through 999999')
    return seed

def filename_for_seed(seed: int | str) -> str:
    return str(canonical_seed(seed))

class _ServerUnavailable(Exception):
    pass

class _NodeBoardServer:

    def __init__(self, node: str) -> None:
        self._process = subprocess.Popen([node, str(_SERVER_RUNNER)], cwd=_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self._lock = threading.Lock()

    def request(self, seed_number: int) -> list[dict]:
        with self._lock:
            try:
                self._process.stdin.write(f'{seed_number}\n')
                self._process.stdin.flush()
                line = self._process.stdout.readline()
            except (BrokenPipeError, ValueError, OSError) as exc:
                raise _ServerUnavailable(str(exc)) from exc
        if not line:
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
            stderr = self._process.stderr.read() if self._process.stderr else ''
            raise _ServerUnavailable(stderr.strip() or 'board server exited unexpectedly')
        payload = json.loads(line)
        if isinstance(payload, dict) and 'error' in payload:
            raise RuntimeError(payload['error'])
        return payload

    def close(self) -> None:
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.wait(timeout=2.0)
        except Exception:
            self._process.kill()
_server_lock = threading.Lock()
_server: _NodeBoardServer | None = None

def _board_server(node: str) -> _NodeBoardServer:
    server = _server
    if server is not None and server._process.poll() is None:
        return server
    return _restart_board_server(node)

def _restart_board_server(node: str) -> _NodeBoardServer:
    global _server
    with _server_lock:
        if _server is not None:
            _server.close()
        _server = _NodeBoardServer(node)
        return _server

def _shutdown_board_server() -> None:
    global _server
    with _server_lock:
        if _server is not None:
            _server.close()
            _server = None
atexit.register(_shutdown_board_server)

def _validate_board(board: list[dict]) -> None:
    if len(board) != 25 or any((not goal.get('name') for goal in board)):
        raise RuntimeError('BingoSync generator returned an invalid board')

def native_board(seed: int | str, node: str | None=None) -> list[dict]:
    seed_number = canonical_seed(seed)
    if node is not None:
        completed = subprocess.run([node, str(_RUNNER), str(seed_number)], cwd=_ROOT, check=True, capture_output=True, text=True)
        board = json.loads(completed.stdout)
        _validate_board(board)
        return board
    resolved_node = shutil.which('node')
    if resolved_node is None:
        raise RuntimeError('Node.js is required to reproduce BingoSync boards exactly')
    try:
        board = _board_server(resolved_node).request(seed_number)
    except _ServerUnavailable:
        board = _restart_board_server(resolved_node).request(seed_number)
    _validate_board(board)
    return board

@dataclass
class MatchedSeedAnalysis:
    seed: int
    filename: str
    native_board: list[dict]
    score: BoardScore
    start_region: str | None
    reached_regions: int
    reached_locations: int
    goal_difficulty: list[GoalDifficultyEstimate]
    board_difficulty: BoardDifficultyEstimate

    def to_dict(self) -> dict:
        scored = []
        for native, goal_score, human_estimate in zip(self.native_board, self.score.goals, self.goal_difficulty):
            goal_analysis = asdict(goal_score)
            goal_analysis['human_difficulty'] = human_estimate.to_dict()
            entry = {**native, 'analysis': goal_analysis}
            chain = DISCOVERY_CHAINS.get(goal_score.name)
            if chain:
                entry['discovery_chain'] = chain
                entry['chain_heavy'] = True
            scored.append(entry)
        unmapped = [g for g in self.score.goals if g.requirement_kind == 'unmapped']
        unreachable_mapped = [g for g in self.score.goals if g.requirement_kind != 'unmapped' and (not g.satisfiable)]
        reachable_costs = [g.cost for g in self.score.goals if g.cost is not None]
        chain_heavy = [g.name for g in self.score.goals if g.name in DISCOVERY_CHAINS]
        workload = self.score.workload_split()
        band_label = self.board_difficulty.difficulty_band.replace('_', ' ').title()
        if unmapped:
            verdict = f'{band_label} estimate; mapping coverage incomplete'
        elif unreachable_mapped:
            verdict = f'{band_label} estimate; {len(unreachable_mapped)} goals not proven reachable'
        else:
            verdict = f'{band_label}; all goals reachable in logic model'
        warnings = ['Reachable means a valid route exists; it does not mean a human player is likely to find or execute it quickly.', 'Completion percentages are provisional model estimates for an experienced two-player, spoiler-free, three-hour blackout.', 'Known dungeon-logic gaps can produce conservative false negatives.']
        if unmapped:
            warnings.insert(0, 'Difficulty confidence is low while native-board goals remain unmapped.')
        if chain_heavy:
            warnings.append('Chain-heavy goals require several separately shuffled loading-zone discoveries.')
        return {'schema_version': 2, 'seed': self.seed, 'beta_quest_filename': self.filename, 'board_source': 'native BingoSync Ocarina of Time Beta Quest generator', 'topology': {'child_start_region': self.start_region, 'reached_regions': self.reached_regions, 'reached_locations': self.reached_locations}, 'difficulty_verdict': verdict, 'difficulty_evidence': {'reachable_board_goals': len(reachable_costs), 'unreached_board_goals': len(unreachable_mapped), 'median_reachable_goal_cost': statistics.median(reachable_costs) if reachable_costs else None, 'maximum_reachable_goal_cost': max(reachable_costs, default=None), 'two_player_relative_makespan': workload.makespan, 'chain_heavy_goals': chain_heavy, 'human_difficulty_score': self.board_difficulty.difficulty_score, 'estimated_completion_probability': self.board_difficulty.completion_probability, 'expected_goals_completed': self.board_difficulty.expected_goals_completed, 'mean_goal_difficulty': self.board_difficulty.mean_goal_difficulty, 'upper_quartile_goal_difficulty': self.board_difficulty.upper_quartile_goal_difficulty, 'bottleneck_goal_difficulty': self.board_difficulty.bottleneck_goal_difficulty}, 'difficulty_model': self.board_difficulty.to_dict(), 'model_coverage': {'scored': 25 - len(unmapped), 'unmapped': len(unmapped), 'unreachable_mapped': len(unreachable_mapped)}, 'warnings': warnings, 'goals': scored}

def analyze_seed(seed: int | str, world: World | None=None, settings: dict[str, Any] | None=None, seed_world=None, chest_seed_world=None, board: list[dict] | None=None) -> MatchedSeedAnalysis:
    seed_number = canonical_seed(seed)
    filename = filename_for_seed(seed_number)
    board = board if board is not None else native_board(seed_number)
    world = world or World.load()
    seed_world = seed_world or seed_world_for_filename(filename, world)
    discovery = compute_for_filename(filename, world=world, settings=settings, seed_world=seed_world)
    names = [goal['name'] for goal in board]
    score = score_board(filename, names, world=world, discovery=discovery)
    opened_world: list = []

    def open_world():
        if not opened_world:
            opened = chest_seed_world() if callable(chest_seed_world) else chest_seed_world
            opened_world.append(opened or seed_world_for_filename(filename, world, sacred_chest_opened=True))
        return opened_world[0]

    def chest_open_discovery():
        return compute_for_filename(filename, world=world, settings=settings, seed_world=open_world())
    score, after_chest = rescore_after_sky_chest(score, names, discovery, chest_open_discovery, reaches_more=lambda searched: reaches_beyond(open_world(), seed_world, searched))
    definitions = {goal['name']: goal for goal in load_goal_definitions()}
    goal_difficulty = [estimate_goal_difficulty(native, definitions[native['name']], goal_score, after_chest if goal_score.after_sky_chest else discovery) for native, goal_score in zip(board, score.goals)]
    board_difficulty = estimate_board_difficulty([goal['name'] for goal in board], goal_difficulty, score.workload_split().makespan)
    table = predict_entrance_table(filename)
    child_spawn = table['resolve'](world.spawn_indices['child'])['result_entrance_id']
    return MatchedSeedAnalysis(seed_number, filename, board, score, start_region=world.dest_region_of_index(child_spawn), reached_regions=len({region for searched in (discovery, after_chest) if searched is not None for region, _age in searched.region_cost if not world.is_state_copy(region)}), reached_locations=len(set(discovery.location_cost) | set(after_chest.location_cost if after_chest else ())), goal_difficulty=goal_difficulty, board_difficulty=board_difficulty)

def write_analysis(analysis: MatchedSeedAnalysis, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis.to_dict(), indent=2) + '\n', encoding='utf-8')
    return path

def write_board_pdf(analysis: MatchedSeedAnalysis, path: Path, *, tier_label: str | None=None, settings_display: str | None=None) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import Paragraph, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError('PDF output requires reportlab: python -m pip install reportlab') from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = landscape(letter)
    canvas = Canvas(str(path), pagesize=(width, height), pageCompression=1)
    canvas.setTitle(f'Beta Quest Matched Seed {analysis.seed}')
    canvas.setAuthor('Beta Quest Matched-Seed Analyzer')
    canvas.setSubject('Native BingoSync Beta Quest board with relative difficulty analysis')
    navy = colors.HexColor('#18253A')
    gold = colors.HexColor('#D6A94A')
    paper = colors.HexColor('#F8F4E8')
    warning = colors.HexColor('#F6D8D4')
    red = colors.HexColor('#8C2F2A')
    canvas.setFillColor(navy)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(paper)
    canvas.setFont('Helvetica-Bold', 17)
    canvas.drawCentredString(width / 2, height - 0.36 * inch, 'BETA QUEST NATIVE BINGOSYNC BOARD')
    canvas.setFillColor(gold)
    canvas.setFont('Helvetica-Bold', 12)
    canvas.drawCentredString(width / 2, height - 0.62 * inch, f"MATCHED SEED: {analysis.seed}     VERDICT: {analysis.to_dict()['difficulty_verdict'].upper()}")
    style = ParagraphStyle('goal', fontName='Helvetica-Bold', fontSize=7.8, leading=9.2, alignment=TA_CENTER, textColor=navy)
    data = []
    backgrounds = []
    for row in range(5):
        cells = []
        for col, (native, score, human) in enumerate(zip(analysis.native_board[row * 5:(row + 1) * 5], analysis.score.goals[row * 5:(row + 1) * 5], analysis.goal_difficulty[row * 5:(row + 1) * 5])):
            if score.satisfiable:
                status = f'Difficulty {human.difficulty_score:.0f}/100 - {human.completion_probability:.0%} uncalibrated estimate'
                status_color = '#765B20'
                backgrounds.append(((col, row), paper))
            else:
                status = 'NOT PROVEN REACHABLE'
                status_color = '#8C2F2A'
                backgrounds.append(((col, row), warning))
            cells.append(Paragraph(f"{score.name}<br/><font size='6.7' color='{status_color}'>BingoSync tier {native['difficulty']} - {status}</font>", style))
        data.append(cells)
    margin = 0.34 * inch
    table_top = height - 0.84 * inch
    provenance_lines = []
    if tier_label:
        provenance_lines.append(f'ANALYSIS TIER: {tier_label.upper()}')
    if settings_display:
        provenance_lines.append(settings_display)
    if provenance_lines:
        provenance_style = ParagraphStyle('provenance', fontName='Helvetica', fontSize=6.7, leading=8, alignment=TA_CENTER, textColor=gold)
        provenance = Paragraph('<br/>'.join(provenance_lines), provenance_style)
        _, provenance_height = provenance.wrap(width - 2 * margin, height)
        provenance_y = table_top - provenance_height
        provenance.drawOn(canvas, margin, provenance_y)
        table_top = provenance_y - 0.04 * inch
    table_bottom = 0.52 * inch
    table = Table(data, colWidths=[(width - 2 * margin) / 5] * 5, rowHeights=[(table_top - table_bottom) / 5] * 5)
    commands = [('BOX', (0, 0), (-1, -1), 2, gold), ('INNERGRID', (0, 0), (-1, -1), 1, gold), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]
    commands.extend((('BACKGROUND', cell, cell, color) for cell, color in backgrounds))
    table.setStyle(TableStyle(commands))
    table.wrapOn(canvas, width - 2 * margin, table_top - table_bottom)
    table.drawOn(canvas, margin, table_bottom)
    canvas.setFillColor(paper)
    canvas.setFont('Helvetica', 6.7)
    canvas.drawCentredString(width / 2, 0.2 * inch, 'Pale red = not proven reachable by the conservative model - relative costs are not minutes; completion estimates are uncalibrated')
    canvas.save()
    return path
