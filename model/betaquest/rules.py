from __future__ import annotations
import ast
import io
import json
import operator
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Protocol
_DATA = Path(__file__).resolve().parent.parent / 'data'
_HELPERS_PATH = _DATA / 'sources' / 'ootr' / 'LogicHelpers.json'

@lru_cache(maxsize=1)
def _base_macros() -> dict[str, tuple[list[str], ast.AST]]:
    raw = _read_logic_file(_HELPERS_PATH)
    macros: dict[str, tuple[list[str], ast.AST]] = {}
    for key, body in raw.items():
        name, _, params = key.partition('(')
        param_names = [p.strip() for p in params.rstrip(')').split(',') if p.strip()] if params else []
        macros[name.strip()] = (param_names, RuleEvaluator._parse(body))
    return macros

def _read_logic_file(path: Path):
    text = ''
    with io.open(path, 'r', encoding='utf-8') as handle:
        for line in handle.readlines():
            text += line.split('#')[0].replace('\n', ' ')
    return json.loads(re.sub(' +', ' ', text))
_SETTING_LIKE = re.compile('^(logic|glitch|shuffle|entrance|mix|free|open|complete|adv|skip|no|disable|start|warp|dungeon|bombchus|plant|useful|selected|triforce)_|^(keysanity|adult_trade_shuffle|damage_multiplier|bridge|gerudo_fortress)$|_(shuffle|shuffled|count|setting)$')
BQ_CHILD_USABLE = frozenset({'Mirror Shield', 'Goron Tunic', 'Zora Tunic'})
BQ_CHILD_SWORD = 'BQ Child Sword'
STRENGTH_UPGRADE = 'Progressive Strength Upgrade'
RBA_STRENGTH_ITEMS = ('RBA Black Gauntlets', 'RBA Green Gauntlets', 'RBA Blue Gauntlets')
RBA_STRENGTH_LEVEL = 3

def _has_item(ctx: 'RuleContext', item: str, count: int=1) -> bool:
    if ctx.has(item, count):
        return True
    if item == STRENGTH_UPGRADE and count <= RBA_STRENGTH_LEVEL:
        return any((ctx.has(gauntlet) for gauntlet in RBA_STRENGTH_ITEMS))
    return False
BOTTLE_ITEMS = ('Bottle', 'Bottle with Milk', 'Rutos Letter', 'Bottle with Red Potion', 'Bottle with Green Potion', 'Bottle with Blue Potion', 'Bottle with Fairy', 'Bottle with Fish', 'Bottle with Blue Fire', 'Bottle with Bugs', 'Bottle with Poe', 'Bottle with Big Poe')
_Compiled = Callable[[Any, dict], Any]
_EMPTY_ENV: dict[str, ast.AST] = {}
_NO_PARAMS: frozenset[str] = frozenset()
_ALWAYS_TRUE: _Compiled = lambda ctx, env: True
_ALWAYS_FALSE: _Compiled = lambda ctx, env: False
_COMPARISONS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}

class RuleContext(Protocol):
    age: str
    region: str

    def has(self, item: str, count: int=1) -> bool:
        ...

    def is_reachable(self, region: str, age: str) -> bool:
        ...

class _AgeRegionContext:
    __slots__ = ('age', 'region', '_base')

    def __init__(self, base: RuleContext, age: str, region: str) -> None:
        self._base = base
        self.age = age
        self.region = region

    def has(self, item: str, count: int=1) -> bool:
        return self._base.has(item, count)

    def is_reachable(self, region: str, age: str) -> bool:
        return self._base.is_reachable(region, age)
DEFAULT_SETTINGS: dict[str, Any] = {'age': 'child', 'starting_age': 'child', 'open_door_of_time': 'stones_sot', 'glitch_door_of_time_skip': False, 'glitch_oi': False, 'glitch_qpa': False, 'glitch_dc_mouth_sword_climb': False, 'glitch_equip_swap': False, 'glitch_megaflip': False, 'glitch_superslide': False, 'glitch_gtg_vine_clip': False, 'glitch_bomb_hover': False, 'glitch_zero_hp_arrival': False, 'glitch_minimum_item_routes': False, 'glitch_dc_switch_trick': False, 'glitch_forest_ledge_precise': False, 'glitch_light_trial_rock_skip': False, 'glitch_suns_song_boss_door': False, 'glitch_llr_tower_clip': False, 'glitch_lh_tree_isg_hookshot': False, 'glitch_jabu_adult_clip': False, 'glitch_gc_dmc_child': False, 'glitch_zd_tunnel_hookshot': False, 'glitch_zd_tunnel_adult': False, 'glitch_damage_flag_corruption': False, 'glitch_child_golden_scale': False, 'glitch_rft_js_clip_child': False, 'glitch_dmc_fairy_child': False, 'glitch_dmc_fairy_adult': False, 'glitch_hba_without_bow': False, 'logic_trail_gs_lower': False, 'logic_trail_gs_upper': False, 'glitch_child_water_temple': False, 'glitch_kak_gallery_void': False, 'glitch_kak_gallery_clip': False, 'glitch_kak_door_clip_child': False, 'glitch_gtg_door_clip_child': False, 'glitch_gv_tent_child_clip': False, 'glitch_gv_octorok_megasidehop_child': False, 'glitch_llr_tower_oob_death': False, 'glitch_spirit_qpa_weirdshot': False, 'logic_wasteland_crossing': False, 'glitch_vine_clip': False, 'bq_water_no_zora_tunic': False, 'open_kakariko': 'open', 'open_forest': 'open', 'gerudo_fortress': 'normal', 'bridge': 'vanilla', 'lacs_condition': 'vanilla', 'damage_multiplier': 'normal', 'shuffle_scrubs': 'off', 'shuffle_individual_ocarina_notes': False, 'skip_child_zelda': False, 'skip_reward_from_rauru': 'not_free', 'free_bombchu_drops': False, 'blue_fire_arrows': False, 'bq_bombchus_without_bag': True, 'logic_grottos_without_agony': True, 'logic_lens_shadow': True, 'logic_lens_shadow_platform': True, 'logic_lens_gtg': True, 'logic_lens_wasteland': True, 'logic_lens_bongo': True, 'logic_lens_botw': True, 'logic_lens_castle': True, 'logic_lens_spirit': True, 'logic_reverse_wasteland': True, 'logic_lab_wall_gs': True, 'shuffle_dungeon_entrances': True, 'logic_water_morpha': True, 'logic_shadow_bongo': True, 'dungeon_shortcuts': (), 'skipped_trials': {'Forest': False, 'Fire': False, 'Water': False, 'Shadow': False, 'Spirit': False, 'Light': False}, 'complete_mask_quest': False, 'plant_beans': False, 'selected_adult_trade_item': 'Claim Check', 'chicken_count': 7, 'big_poe_count': 10}

@dataclass
class RuleEvaluator:
    items: set[str]
    events: set[str]
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))

    def __post_init__(self) -> None:
        self._by_escaped: dict[str, str] = {}
        for name in list(self.items) + list(self.events):
            self._by_escaped.setdefault(self._escape(name), name)
        self.macros: dict[str, tuple[list[str], ast.AST]] = dict(_base_macros())
        if 'has_fire_source' in self.macros:
            params, body = self.macros['has_fire_source']
            qpa_clause = self._parse('glitch_qpa and (Sticks or Kokiri_Sword or BQ_Child_Sword)')
            self.macros['has_fire_source'] = (params, ast.BoolOp(op=ast.Or(), values=[body, qpa_clause]))
        if self.settings.get('bq_bombchus_without_bag'):
            found = 'Bombchus or Bombchus_5 or Bombchus_10 or Bombchus_20'
            for name, body in (('found_bombchus', found), ('has_bombchus', found), ('has_explosives', f'Bombs or {found}'), ('has_both_explosives', f'Bombs and ({found})')):
                self.macros[name] = ([], self._parse(body))
        self.macros['bq_bomb_hover'] = ([], self._parse('glitch_bomb_hover and can_shield and can_jumpslash and Bombs'))
        self.macros['bq_bombchu_hover'] = ([], self._parse('glitch_bomb_hover and can_shield and can_jumpslash and has_bombchus'))
        self.macros['bq_five_hearts'] = ([], self._parse('(Heart_Container, 2) or (Heart_Container and (Piece_of_Heart, 4)) or (Piece_of_Heart, 8)'))
        self.macros['bq_six_hearts'] = ([], self._parse('(Heart_Container, 3) or ((Heart_Container, 2) and (Piece_of_Heart, 4)) or (Heart_Container and (Piece_of_Heart, 8)) or (Piece_of_Heart, 12)'))
        self.macros['bq_weird_shot'] = ([], self._parse('can_use(Hookshot) and Bombs and can_shield'))
        self.macros['bq_fourteen_hearts'] = ([], self._parse(' or '.join((' and '.join((part for part in (f'(Heart_Container, {c})' if c else '', f'(Piece_of_Heart, {4 * (11 - c)})' if c < 11 else '') if part)) for c in range(12)))))
        self.macros['bq_volvagia_heat'] = ([], self._parse('can_use(Goron_Tunic) or (has_bombchus and bq_six_hearts) or bq_fourteen_hearts or (Fairy and (can_equip_swap_child or can_equip_swap_adult))'))
        self.macros['bq_damage_flag_corruption'] = ([], self._parse('glitch_damage_flag_corruption and (Bugs or Fish or Fairy or Blue_Fire) and (can_use(Slingshot) or can_use(Bow) or (Magic_Meter and (is_adult or Kokiri_Sword or BQ_Child_Sword)))'))
        for name, body in (('bq_vine_clip_gtg', 'glitch_vine_clip and is_child and can_shield and has_bombchus'), ('bq_vine_clip_botw', 'glitch_vine_clip and is_child and can_shield'), ('bq_superslide', 'glitch_superslide and is_adult and Bombs and can_shield and can_use(Hover_Boots)')):
            self.macros[name] = ([], self._parse(body))
        self._cache: dict[str, ast.AST] = {}
        self._compiled: dict[tuple[ast.AST, frozenset[str]], _Compiled] = {}
        self._comparables: dict[tuple[ast.AST, frozenset[str]], _Compiled] = {}
        self.unknown_identifiers: set[str] = set()
        self.assumed_settings: set[str] = set()
        self._fast: dict[str, Callable[[Any], bool]] = {}
        self._seen: dict[str, int] = {}

    @staticmethod
    def _escape(name: str) -> str:
        return re.sub('[^A-Za-z0-9_]', '', name.replace(' ', '_'))

    @staticmethod
    def _parse(rule: str) -> ast.AST:
        return ast.parse(str(rule).strip(), mode='eval').body

    def parse(self, rule: str) -> ast.AST:
        key = str(rule)
        node = self._cache.get(key)
        if node is None:
            node = self._parse(key)
            self._cache[key] = node
        return node

    def evaluate(self, rule: str, ctx: RuleContext) -> bool:
        fast = self._fast.get(rule)
        if fast is not None:
            return fast(ctx)
        return self._evaluate_early(rule, ctx)

    def evaluate_by_closures(self, rule: str, ctx: RuleContext) -> bool:
        return bool(self.compile(self.parse(rule), _NO_PARAMS)(ctx, _EMPTY_ENV))

    def _evaluate_early(self, rule: str, ctx: RuleContext) -> bool:
        seen = self._seen.get(rule, 0) + 1
        if seen < FAST_AFTER:
            self._seen[rule] = seen
            return self.evaluate_by_closures(rule, ctx)
        fast = self._fast_function(rule)
        self._fast[rule] = fast
        return fast(ctx)

    def _fast_function(self, rule: str) -> Callable[[Any], bool]:
        node = self.parse(rule)
        writer = _RuleWriter(self)
        try:
            expr = writer.node(node, {}, 0)
        except (_TooBig, RecursionError):
            expr = None
        if expr is not None and expr.const:
            return _ANSWER_TRUE if expr.value else _ANSWER_FALSE
        if expr is not None:
            body = expr.src if expr.kind == 'bool' else f'True if {expr.src} else False'
            try:
                code = _compile_rule_source(f'def _rule(ctx):\n    return {body}\n')
            except (SyntaxError, RecursionError, MemoryError, ValueError):
                code = None
            if code is not None:
                exec(code, writer.ns)
                return writer.ns['_rule']
        compiled = self.compile(node, _NO_PARAMS)
        return lambda ctx: bool(compiled(ctx, _EMPTY_ENV))

    def compile(self, node: ast.AST, params: frozenset[str]) -> _Compiled:
        key = (node, params)
        compiled = self._compiled.get(key)
        if compiled is not None:
            return compiled
        cell: list[_Compiled] = []
        self._compiled[key] = lambda ctx, env: cell[0](ctx, env)
        built = self._build(node, params)
        cell.append(built)
        self._compiled[key] = built
        return built

    @staticmethod
    def _raiser(message: str) -> _Compiled:

        def fail(ctx, env):
            raise ValueError(message)
        return fail

    def _build(self, node: ast.AST, params: frozenset[str]) -> _Compiled:
        if isinstance(node, ast.BoolOp):
            parts = [self.compile(v, params) for v in node.values]
            if isinstance(node.op, ast.And):

                def eval_and(ctx, env):
                    for part in parts:
                        if not part(ctx, env):
                            return False
                    return True
                return eval_and

            def eval_or(ctx, env):
                for part in parts:
                    if part(ctx, env):
                        return True
                return False
            return eval_or
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = self.compile(node.operand, params)
            return lambda ctx, env: not operand(ctx, env)
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, str):
                if value in self.items or value in self.events:
                    if value == STRENGTH_UPGRADE:
                        return lambda ctx, env: _has_item(ctx, value)
                    return lambda ctx, env: ctx.has(value)
                return self._static_name(value)
            return lambda ctx, env: value
        if isinstance(node, ast.Tuple):
            return self._build_tuple(node, params)
        if isinstance(node, ast.Compare):
            return self._build_compare(node, params)
        if isinstance(node, ast.Name):
            return self._build_name(node, params)
        if isinstance(node, ast.Call):
            return self._build_call(node, params)
        if isinstance(node, ast.Subscript):
            container_of = self._build_comparable(node.value, params)
            key_of = self._build_comparable(node.slice, params)
            value_node = node.value

            def eval_subscript(ctx, env):
                container = container_of(ctx, env)
                key = key_of(ctx, env)
                try:
                    return container[key]
                except (KeyError, IndexError, TypeError):
                    self.unknown_identifiers.add(f'{self._as_name(value_node, env)}[{key}]')
                    return False
            return eval_subscript
        return self._raiser(f'unsupported rule node: {ast.dump(node)[:120]}')

    def _build_tuple(self, node: ast.Tuple, params: frozenset[str]) -> _Compiled:
        item_node, count_node = (node.elts[0], node.elts[1])
        count_of = self.compile(count_node, params)
        if not (isinstance(item_node, ast.Name) and item_node.id in params):
            try:
                item = self._as_name(item_node, _EMPTY_ENV)
            except ValueError as exc:
                return self._raiser(str(exc))
            resolved = self._by_escaped.get(item, self._item_name(item))
            if resolved == STRENGTH_UPGRADE:
                return lambda ctx, env: _has_item(ctx, resolved, int(count_of(ctx, env)))
            return lambda ctx, env: ctx.has(resolved, int(count_of(ctx, env)))

        def eval_tuple(ctx, env):
            item = self._as_name(item_node, env)
            resolved = self._by_escaped.get(item, self._item_name(item))
            return _has_item(ctx, resolved, int(count_of(ctx, env)))
        return eval_tuple

    def _build_compare(self, node: ast.Compare, params: frozenset[str]) -> _Compiled:
        left_of = self._build_comparable(node.left, params)
        steps: list[tuple[Any, bool, Any]] = []
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                if isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                    element_of = [self._build_comparable(e, params) for e in comp.elts]
                    steps.append((None, isinstance(op, ast.In), element_of))
                else:
                    steps.append((None, isinstance(op, ast.In), self._build_comparable(comp, params)))
                continue
            apply = _COMPARISONS.get(type(op))
            if apply is None:
                return self._raiser(f'unsupported comparison: {ast.dump(op)}')
            steps.append((apply, False, self._build_comparable(comp, params)))
        if len(steps) == 1 and steps[0][0] is not None:
            apply, _, right_of = steps[0]
            return lambda ctx, env: apply(left_of(ctx, env), right_of(ctx, env))

        def eval_compare(ctx, env):
            left = left_of(ctx, env)
            result = True
            for apply, is_in, right_of in steps:
                if apply is None:
                    if isinstance(right_of, list):
                        options = [element(ctx, env) for element in right_of]
                    else:
                        options = right_of(ctx, env)
                    hit = left in options
                    result = result and (hit if is_in else not hit)
                    left = options
                    continue
                right = right_of(ctx, env)
                result = result and apply(left, right)
                left = right
            return result
        return eval_compare

    def _build_comparable(self, node: ast.AST, params: frozenset[str]) -> _Compiled:
        key = (node, params)
        built = self._comparables.get(key)
        if built is None:
            built = self._comparables[key] = self._build_comparable_uncached(node, params)
        return built

    def _build_comparable_uncached(self, node: ast.AST, params: frozenset[str]) -> _Compiled:
        if isinstance(node, ast.Constant):
            value = node.value
            return lambda ctx, env: value
        if isinstance(node, ast.Name):
            name = node.id
            static = self._static_comparable_name(name)
            if name not in params:
                return static

            def eval_bound_comparable(ctx, env):
                bound = env.get(name)
                if bound is not None:
                    return self._build_comparable(bound, params)(ctx, env)
                return static(ctx, env)
            return eval_bound_comparable
        return self.compile(node, params)

    def _static_comparable_name(self, name: str) -> _Compiled:
        if name == 'age':
            return lambda ctx, env: ctx.age
        if name in self.settings:
            return lambda ctx, env: self.settings[name]

        def eval_assumed(ctx, env):
            self.assumed_settings.add(name)
            return name
        return eval_assumed

    @staticmethod
    def _as_name(node: ast.AST, env: dict[str, ast.AST]) -> str:
        if isinstance(node, ast.Name):
            if node.id in env:
                return RuleEvaluator._as_name(env[node.id], env)
            return node.id
        if isinstance(node, ast.Constant):
            return str(node.value)
        raise ValueError(f'expected a name, got {ast.dump(node)[:80]}')

    @staticmethod
    def _item_name(token: str) -> str:
        return token.replace('_', ' ')

    @staticmethod
    def _region_name(token: str) -> str:
        return token.replace('_', ' ') if '_' in token else token

    def _build_name(self, node: ast.Name, params: frozenset[str]) -> _Compiled:
        name = node.id
        static = self._static_name(name)
        if name not in params:
            return static

        def eval_bound_name(ctx, env):
            bound = env.get(name)
            if bound is not None:
                return self.compile(bound, params)(ctx, env)
            return static(ctx, env)
        return eval_bound_name

    def _static_name(self, name: str) -> _Compiled:
        if name == 'age':
            return lambda ctx, env: ctx.age
        if name in self.macros:
            macro_params, body = self.macros[name]
            if macro_params:
                return self._raiser(f'macro {name} used without arguments')
            expand = self.compile(body, _NO_PARAMS)
            if name in ('can_child_attack', 'can_child_damage'):

                def eval_child_combat(ctx, env):
                    if ctx.age == 'child' and ctx.has(BQ_CHILD_SWORD):
                        return True
                    return expand(ctx, _EMPTY_ENV)
                return eval_child_combat
            return lambda ctx, env: expand(ctx, _EMPTY_ENV)
        if name in self.settings:
            return lambda ctx, env: self.settings[name]
        if name == 'has_bottle':
            return lambda ctx, env: any((ctx.has(b) for b in BOTTLE_ITEMS))
        if name.startswith('Ocarina_') and name.endswith('_Button'):
            return _ALWAYS_TRUE
        if name == 'at_dampe_time':
            return _ALWAYS_TRUE
        if name == 'had_night_start':
            return _ALWAYS_FALSE
        if name == 'Chicken':
            return _ALWAYS_TRUE
        if name in ('at_night', 'at_day'):
            return _ALWAYS_TRUE
        resolved = self._by_escaped.get(name)
        if resolved is None:
            spaced = self._item_name(name)
            if spaced in self.items or spaced in self.events:
                resolved = spaced
        if resolved is not None:
            held = resolved
            if held == STRENGTH_UPGRADE:
                return lambda ctx, env: _has_item(ctx, held)
            return lambda ctx, env: ctx.has(held)
        if _SETTING_LIKE.match(name):

            def eval_assumed(ctx, env):
                self.assumed_settings.add(name)
                return False
            return eval_assumed

        def eval_unknown(ctx, env):
            self.unknown_identifiers.add(name)
            return False
        return eval_unknown

    def _build_call(self, node: ast.Call, params: frozenset[str]) -> _Compiled:
        func = node.func
        if not isinstance(func, ast.Name):
            return self._raiser(f'unsupported call target: {ast.dump(func)[:80]}')
        name = func.id
        if name == 'here':
            inner = self.compile(node.args[0], params)

            def eval_here(ctx, env):
                for age in (ctx.age, 'adult' if ctx.age == 'child' else 'child'):
                    if age == ctx.age or ctx.is_reachable(ctx.region, age):
                        if inner(_AgeRegionContext(ctx, age, ctx.region), env):
                            return True
                return False
            return eval_here
        if name == 'at':
            region_node = node.args[0]
            inner = self.compile(node.args[1], params)
            fixed_region = None
            if not (isinstance(region_node, ast.Name) and region_node.id in params):
                try:
                    fixed_region = self._region_name(self._as_name(region_node, _EMPTY_ENV))
                except ValueError:
                    fixed_region = None

            def eval_at(ctx, env):
                region = fixed_region
                if region is None:
                    region = self._region_name(self._as_name(region_node, env))
                for age in (ctx.age, 'adult' if ctx.age == 'child' else 'child'):
                    if ctx.is_reachable(region, age):
                        if inner(_AgeRegionContext(ctx, age, region), env):
                            return True
                return False
            return eval_at
        if name == 'has_all_notes_for_song':
            return _ALWAYS_TRUE
        child_usable: str | None = None
        arg_rebindable = False
        if name == 'can_use' and node.args:
            arg = node.args[0]
            arg_rebindable = isinstance(arg, ast.Name) and arg.id in params
            if not arg_rebindable:
                try:
                    requested = self._as_name(arg, _EMPTY_ENV)
                except ValueError:
                    requested = None
                if requested is not None:
                    resolved = self._by_escaped.get(requested, self._item_name(requested))
                    if resolved in BQ_CHILD_USABLE:
                        child_usable = resolved
        if child_usable is not None:
            return lambda ctx, env: ctx.has(child_usable)
        expansion = self._build_macro_call(node, name, params)
        if not arg_rebindable:
            return expansion
        arg = node.args[0]

        def eval_can_use(ctx, env):
            try:
                requested = self._as_name(arg, env)
            except ValueError:
                requested = None
            if requested is not None:
                resolved = self._by_escaped.get(requested, self._item_name(requested))
                if resolved in BQ_CHILD_USABLE:
                    return ctx.has(resolved)
            return expansion(ctx, env)
        return eval_can_use

    def _build_macro_call(self, node: ast.Call, name: str, params: frozenset[str]) -> _Compiled:
        if name not in self.macros:

            def eval_unknown_call(ctx, env):
                self.unknown_identifiers.add(f'{name}()')
                return False
            return eval_unknown_call
        macro_params, body = self.macros[name]
        args = list(node.args)
        if len(macro_params) != len(args):
            return self._raiser(f'macro {name} expects {len(macro_params)} args, got {len(args)}')
        expand = self.compile(body, frozenset(macro_params))
        if not params:
            fixed = dict(zip(macro_params, args))
            return lambda ctx, env: expand(ctx, fixed)
        pairs = list(zip(macro_params, args))

        def eval_macro(ctx, env):
            bound = {p: env.get(a.id, a) if isinstance(a, ast.Name) else a for p, a in pairs}
            return expand(ctx, bound)
        return eval_macro
FAST_AFTER = 3
FAST_MAX_NODES = 4000

def _answer_true(ctx: Any) -> bool:
    return True

def _answer_false(ctx: Any) -> bool:
    return False
_ANSWER_TRUE = _answer_true
_ANSWER_FALSE = _answer_false
_SYMBOLS = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}

@lru_cache(maxsize=16384)
def _compile_rule_source(source: str):
    return compile(source, '<rule>', 'exec')

class _TooBig(Exception):
    pass

@dataclass
class _Expr:
    src: str
    kind: str
    const: bool = False
    known: bool = False
    value: Any = None
    effect: str | None = None

class _RuleWriter:

    def __init__(self, ev: 'RuleEvaluator') -> None:
        self.ev = ev
        self.ns: dict[str, Any] = {'_has_item': _has_item, '_A': ev.assumed_settings.add, '_U': ev.unknown_identifiers.add}
        self.size = 0

    def ref(self, obj: Any) -> str:
        name = f'_k{len(self.ns)}'
        self.ns[name] = obj
        return name

    def const(self, value: Any) -> _Expr:
        src = repr(value) if value is None or type(value) in (bool, int, str) else self.ref(value)
        kind = 'bool' if isinstance(value, bool) else 'exact'
        return _Expr(src, kind, const=True, known=True, value=value)

    def has(self, item: str) -> _Expr:
        if item == STRENGTH_UPGRADE:
            return _Expr(f'_has_item(ctx, {item!r})', 'bool')
        return _Expr(f'ctx.has({item!r})', 'exact')

    def recorded(self, which: str, name: str, value: Any) -> _Expr:
        target = self.ev.assumed_settings if which == '_A' else self.ev.unknown_identifiers
        if name in target:
            return self.const(value)
        call = f'{which}({name!r})'
        kind = 'bool' if isinstance(value, bool) else 'exact'
        return _Expr(f'({call} or {value!r})', kind, known=True, value=value, effect=call)

    @staticmethod
    def as_value(expr: _Expr) -> str:
        return f'bool({expr.src})' if expr.kind == 'loose' else expr.src

    def fallback(self, node: ast.AST, env: dict) -> _Expr:
        closure = self.ev.compile(node, frozenset(env))
        return _Expr(f'{self.ref(closure)}(ctx, {self.ref(env)})', 'exact')

    def tick(self) -> None:
        self.size += 1
        if self.size > FAST_MAX_NODES:
            raise _TooBig()

    def node(self, node: ast.AST, env: dict, depth: int) -> _Expr:
        self.tick()
        if isinstance(node, ast.BoolOp):
            return self.boolop(node, env, depth)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self.node(node.operand, env, depth + 1)
            if inner.const:
                return self.const(not inner.value)
            if inner.known:
                return _Expr(f'(not {inner.src})', 'bool', known=True, value=not inner.value)
            return _Expr(f'(not {inner.src})', 'bool')
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, str):
                if value in self.ev.items or value in self.ev.events:
                    return self.has(value)
                return self.static_name(value, node, depth)
            return self.const(value)
        if isinstance(node, ast.Tuple):
            return self.tuple(node, env, depth)
        if isinstance(node, ast.Compare):
            return self.compare(node, env, depth)
        if isinstance(node, ast.Name):
            if node.id in env:
                return self.node(env[node.id], env, depth + 1)
            return self.static_name(node.id, node, depth)
        if isinstance(node, ast.Call):
            return self.call(node, env, depth)
        return self.fallback(node, env)

    def boolop(self, node: ast.BoolOp, env: dict, depth: int) -> _Expr:
        is_and = isinstance(node.op, ast.And)
        parts: list[_Expr] = []
        absorbed = False
        for value in node.values:
            part = self.node(value, env, depth + 1)
            if part.const:
                if bool(part.value) == is_and:
                    continue
                parts.append(self.const(not is_and))
                absorbed = True
                break
            parts.append(part)
            if part.known and bool(part.value) != is_and:
                absorbed = True
                break
        if not parts:
            return self.const(is_and)
        if len(parts) == 1 and parts[0].const:
            return parts[0]
        if absorbed:
            known, value = (True, not is_and)
        else:
            known = all((part.known for part in parts))
            value = is_and if known else None
        if len(parts) == 1:
            kind = 'bool' if parts[0].kind == 'bool' else 'loose'
            return _Expr(parts[0].src, kind, known=known, value=value)
        joiner = ' and ' if is_and else ' or '
        kind = 'bool' if all((part.kind == 'bool' for part in parts)) else 'loose'
        return _Expr('(' + joiner.join((part.src for part in parts)) + ')', kind, known=known, value=value)

    def tuple(self, node: ast.Tuple, env: dict, depth: int) -> _Expr:
        if len(node.elts) < 2:
            return self.fallback(node, env)
        item_node, count_node = (node.elts[0], node.elts[1])
        count = self.node(count_node, env, depth + 1)
        if count.const:
            try:
                count_src = repr(int(count.value))
            except (TypeError, ValueError, OverflowError):
                return self.fallback(node, env)
        else:
            count_src = f'int({self.as_value(count)})'
        bound = isinstance(item_node, ast.Name) and item_node.id in env
        try:
            item = RuleEvaluator._as_name(item_node, env if bound else _EMPTY_ENV)
        except ValueError:
            return self.fallback(node, env)
        resolved = self.ev._by_escaped.get(item, self.ev._item_name(item))
        if resolved == STRENGTH_UPGRADE:
            return _Expr(f'_has_item(ctx, {resolved!r}, {count_src})', 'bool')
        if bound:
            return _Expr(f'(True if ctx.has({resolved!r}, {count_src}) else False)', 'bool')
        return _Expr(f'ctx.has({resolved!r}, {count_src})', 'exact')

    def compare(self, node: ast.Compare, env: dict, depth: int) -> _Expr:
        if len(node.ops) != 1 or type(node.ops[0]) not in _SYMBOLS:
            return self.fallback(node, env)
        apply = _COMPARISONS[type(node.ops[0])]
        left = self.comparable(node.left, env, depth + 1)
        right = self.comparable(node.comparators[0], env, depth + 1)
        if left.known and right.known:
            try:
                result = apply(left.value, right.value)
            except Exception:
                return self.fallback(node, env)
            effects = [side.effect for side in (left, right) if side.effect]
            if not effects:
                return self.const(result)
            if type(result) not in (bool, int, str):
                return self.fallback(node, env)
            effect = ' or '.join(effects)
            kind = 'bool' if isinstance(result, bool) else 'exact'
            return _Expr(f'({effect} or {result!r})', kind, known=True, value=result, effect=effect)
        symbol = _SYMBOLS[type(node.ops[0])]
        return _Expr(f'({self.as_value(left)} {symbol} {self.as_value(right)})', 'exact')

    def comparable(self, node: ast.AST, env: dict, depth: int) -> _Expr:
        self.tick()
        if isinstance(node, ast.Constant):
            return self.const(node.value)
        if isinstance(node, ast.Name):
            name = node.id
            if name in env:
                return self.comparable(env[name], env, depth + 1)
            if name == 'age':
                return _Expr('ctx.age', 'exact')
            if name in self.ev.settings:
                return self.const(self.ev.settings[name])
            return self.recorded('_A', name, name)
        inner = self.node(node, env, depth + 1)
        if inner.kind != 'loose':
            return inner
        return _Expr(f'bool({inner.src})', 'bool', known=inner.known, value=bool(inner.value) if inner.known else None)

    def static_name(self, name: str, node: ast.AST, depth: int) -> _Expr:
        ev = self.ev
        if name == 'age':
            return _Expr('ctx.age', 'exact')
        if name in ev.macros:
            macro_params, body = ev.macros[name]
            if macro_params:
                return self.fallback(node, {})
            inner = self.node(body, {}, depth + 1)
            if name in ('can_child_attack', 'can_child_damage'):
                return _Expr(f"(True if (ctx.age == 'child' and ctx.has({BQ_CHILD_SWORD!r})) else {inner.src})", inner.kind)
            return inner
        if name in ev.settings:
            return self.const(ev.settings[name])
        if name == 'has_bottle':
            return _Expr('(' + ' or '.join((f'ctx.has({b!r})' for b in BOTTLE_ITEMS)) + ')', 'loose')
        if name.startswith('Ocarina_') and name.endswith('_Button'):
            return self.const(True)
        if name in ('at_dampe_time', 'Chicken', 'at_night', 'at_day'):
            return self.const(True)
        if name == 'had_night_start':
            return self.const(False)
        resolved = ev._by_escaped.get(name)
        if resolved is None:
            spaced = ev._item_name(name)
            if spaced in ev.items or spaced in ev.events:
                resolved = spaced
        if resolved is not None:
            return self.has(resolved)
        if _SETTING_LIKE.match(name):
            return self.recorded('_A', name, False)
        return self.recorded('_U', name, False)

    def call(self, node: ast.Call, env: dict, depth: int) -> _Expr:
        ev = self.ev
        func = node.func
        if not isinstance(func, ast.Name) or func.id in ('here', 'at'):
            return self.fallback(node, env)
        name = func.id
        if name == 'has_all_notes_for_song':
            return self.const(True)
        if name == 'can_use' and node.args:
            arg = node.args[0]
            bound = isinstance(arg, ast.Name) and arg.id in env
            try:
                requested = RuleEvaluator._as_name(arg, env if bound else _EMPTY_ENV)
            except ValueError:
                requested = None
            if requested is not None:
                resolved = ev._by_escaped.get(requested, ev._item_name(requested))
                if resolved in BQ_CHILD_USABLE:
                    return _Expr(f'ctx.has({resolved!r})', 'exact')
        if name not in ev.macros:
            return self.recorded('_U', f'{name}()', False)
        macro_params, body = ev.macros[name]
        if len(macro_params) != len(node.args):
            return self.fallback(node, env)
        inner_env = {param: env.get(arg.id, arg) if isinstance(arg, ast.Name) else arg for param, arg in zip(macro_params, node.args)}
        return self.node(body, inner_env, depth + 1)
