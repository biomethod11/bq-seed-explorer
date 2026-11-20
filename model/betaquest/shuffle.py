from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Callable
from . import filename as _filename
from .rng import MASK32, rand_zero_one, round_to_f32
from .seed import seed_from_filename
MAX_ENTRANCES = 326
RAND_ENTRANCES = 318
SHUFFLE_ENTRANCES = 282
GROTTOS_INDEX = 269
NEW_GROTTO_ENTRANCES = 14
TOTAL_GROTTO_ENTRANCES = 15 + NEW_GROTTO_ENTRANCES
SPOOL_ENTRANCES = RAND_ENTRANCES - SHUFFLE_ENTRANCES + NEW_GROTTO_ENTRANCES
GENERIC_GROTTO = 63
FAIRY_GROTTO = 877
SACRED_ENT = 160
MAGIC_FAIRY_ENT = 789
_DATA_PATH = Path(__file__).resolve().parent.parent / 'data' / 'entrances_raw.json'

def _load_tables() -> dict[str, Any]:
    with _DATA_PATH.open(encoding='utf-8') as handle:
        return json.load(handle)
_RAW = _load_tables()
VAR_ENTRANCES: tuple[int, ...] = tuple(_RAW['VAR_Entrances'])
VAR_GROTTO: tuple[int, ...] = tuple(_RAW['VAR_Grotto'])
VAR_MAGIC_ENTRANCES: tuple[int, ...] = tuple(_RAW['VAR_Magic_Entrances'])
assert len(VAR_ENTRANCES) == MAX_ENTRANCES, 'master entrance table is the wrong length'
assert len(VAR_GROTTO) == NEW_GROTTO_ENTRANCES
assert len(VAR_MAGIC_ENTRANCES) == 6

def sign_extend_16(value: int) -> int:
    return (value & 65535 ^ 32768) - 32768

def sign_extend_32(value: int) -> int:
    return (value & MASK32 ^ 2147483648) - 2147483648

def random_range(state: int, range_: int) -> tuple[int, int]:
    value, new_state = rand_zero_one(state)
    range_f32 = round_to_f32(float(sign_extend_32(range_)))
    product = round_to_f32(value * range_f32)
    truncated = int(product)
    offset = 0
    result = sign_extend_16(truncated + offset & MASK32)
    return (result, new_state)

def copy_entrances(current_entrance_id: int, master: 'list[int] | tuple[int, ...] | None'=None, copy_amount: int | None=None) -> tuple[list[int], int]:
    if master is None:
        master = VAR_ENTRANCES
    if copy_amount is None:
        copy_amount = len(master)
    working: list[int] = []
    lookup_index = -1
    for i in range(copy_amount):
        value = master[i]
        working.append(value)
        if value == current_entrance_id:
            lookup_index = i
    return (working, lookup_index)

def shuffle_entrances(state: int, working_table: list[int], count: int | None=None) -> tuple[list[int], int]:
    if count is None:
        count = SHUFFLE_ENTRANCES
    s1 = count
    while s1 > 0:
        j, state = random_range(state, s1)
        tail = s1 - 1
        working_table[tail], working_table[j] = (working_table[j], working_table[tail])
        s1 -= 1
    return (working_table, state)

def randomize_special_entrances(state: int, master: 'list[int] | tuple[int, ...] | None'=None, count: int | None=None, range_: int | None=None) -> tuple[list[int], int]:
    if master is None:
        master = VAR_ENTRANCES
    if count is None:
        count = SPOOL_ENTRANCES
    if range_ is None:
        range_ = RAND_ENTRANCES
    spool: list[int] = []
    for _ in range(count):
        index, state = random_range(state, range_)
        spool.append(master[index])
    return (spool, state)

def sacred_entrance_slot(state: int) -> tuple[int, int]:
    n, state = random_range(state, TOTAL_GROTTO_ENTRANCES - 2)
    return (GROTTOS_INDEX + n, state)

def apply_sacred_entrance(working_table: list[int], spool_table: list[int], sacred_write_index: int, *, chest_opened: bool) -> tuple[list[int], list[int]]:
    effective_working = list(working_table)
    effective_spool = list(spool_table)
    if chest_opened:
        return (effective_working, effective_spool)
    if not GROTTOS_INDEX <= sacred_write_index <= GROTTOS_INDEX + 26:
        raise ValueError(f'sacred write index outside grotto window: {sacred_write_index}')
    if sacred_write_index < SHUFFLE_ENTRANCES:
        effective_working[sacred_write_index] = SACRED_ENT
    else:
        effective_spool[sacred_write_index - SHUFFLE_ENTRANCES] = SACRED_ENT
    return (effective_working, effective_spool)
_NO_LOOKUP = object()

def build_tables(state: int) -> dict[str, Any]:
    working, _ = copy_entrances(current_entrance_id=_NO_LOOKUP)
    working, state_after_shuffle = shuffle_entrances(state, working)
    spool, state_after_spool = randomize_special_entrances(state_after_shuffle)
    sacred_index, state_after_sacred = sacred_entrance_slot(state_after_spool)
    return {'working_table': working, 'shuffled_table': working[:SHUFFLE_ENTRANCES], 'spool_table': spool, 'state_after_shuffle': state_after_shuffle, 'state_after_spool': state_after_spool, 'state_after_sacred': state_after_sacred, 'sacred_write_index': sacred_index}

def _dispatch(current_entrance_id: int, lookup_index: int, working_table: list[int], spool_table: list[int]) -> dict[str, Any]:
    if lookup_index < 0:
        return {'lookup_index': lookup_index, 'case': 'bad_entrance', 'result_entrance_id': -1}
    if lookup_index >= RAND_ENTRANCES:
        return {'lookup_index': lookup_index, 'case': 'static', 'corrected_index': lookup_index, 'result_entrance_id': VAR_ENTRANCES[lookup_index]}
    if lookup_index < SHUFFLE_ENTRANCES:
        corrected = lookup_index
        case = 'shuffled'
        result = working_table[corrected]
    else:
        corrected = lookup_index + NEW_GROTTO_ENTRANCES
        case = 'spool'
        spool_slot = corrected - SHUFFLE_ENTRANCES
        assert spool_slot == lookup_index - SHUFFLE_ENTRANCES + NEW_GROTTO_ENTRANCES
        result = spool_table[spool_slot]
    return {'lookup_index': lookup_index, 'case': case, 'corrected_index': corrected, 'result_entrance_id': result}

def resolve_entrance(current_entrance_id: int, state: int, *, sacred_chest_opened: bool=False) -> dict[str, Any]:
    _, lookup_index = copy_entrances(current_entrance_id)
    tables = build_tables(state)
    working, spool = apply_sacred_entrance(tables['working_table'], tables['spool_table'], tables['sacred_write_index'], chest_opened=sacred_chest_opened)
    return _annotate(_dispatch(current_entrance_id, lookup_index, working, spool), current_entrance_id, tables['sacred_write_index'])

def _annotate(result: dict[str, Any], current_entrance_id: int, sacred_write_index: int) -> dict[str, Any]:
    result['input_entrance_id'] = current_entrance_id
    result['grotto_case'] = current_entrance_id in (GENERIC_GROTTO, FAIRY_GROTTO)
    result['sacred_conflict'] = result.get('case') == 'shuffled' and result.get('corrected_index') == sacred_write_index
    result['sacred_write_index'] = sacred_write_index
    result['magic_reroute_candidate'] = result.get('result_entrance_id') in VAR_MAGIC_ENTRANCES[:5]
    result['result_is_grotto_placeholder'] = result.get('result_entrance_id') in (GENERIC_GROTTO, FAIRY_GROTTO)
    return result

def predict_entrance_table(name: str, *, prior_state: int | None=None, sacred_chest_opened: bool=False) -> dict[str, Any]:
    word1, word2 = _filename.name_to_words(name)
    seed = seed_from_filename(word1, word2, prior_state=prior_state)
    tables = build_tables(seed)
    sacred_index = tables['sacred_write_index']
    working, spool = apply_sacred_entrance(tables['working_table'], tables['spool_table'], sacred_index, chest_opened=sacred_chest_opened)
    index_of = {value: i for i, value in enumerate(VAR_ENTRANCES)}

    def find_lookup_index(entrance_id: int) -> int:
        return index_of.get(entrance_id, -1)

    def resolve(entrance_id: int) -> dict[str, Any]:
        return _annotate(_dispatch(entrance_id, find_lookup_index(entrance_id), working, spool), entrance_id, sacred_index)
    out: dict[str, Any] = {'name': name, 'word1': word1, 'word2': word2, 'seed': seed, 'resolve': resolve, 'find_lookup_index': find_lookup_index, 'sacred_chest_opened': sacred_chest_opened, 'effective_working_table': working, 'effective_shuffled_table': working[:SHUFFLE_ENTRANCES], 'effective_spool_table': spool}
    out.update(tables)
    return out
ResolveFn = Callable[[int], dict]
