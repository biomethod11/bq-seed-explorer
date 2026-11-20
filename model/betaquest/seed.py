from __future__ import annotations
from . import filename as _filename
from .rng import MASK32, rand_next
VAR_RNG_ONLY = (3166220772, 3117600989)

class RngOnlyModeError(RuntimeError):
    pass

def is_rng_only(word1: int, word2: int) -> bool:
    return (word1 & MASK32, word2 & MASK32) == VAR_RNG_ONLY

def seed_from_filename(word1: int, word2: int, *, prior_state: int | None=None) -> int:
    word1 &= MASK32
    word2 &= MASK32
    if is_rng_only(word1, word2):
        if prior_state is None:
            raise RngOnlyModeError("filename 'RNG-Only' (VAR_RNG_ONLY) skips seeding; the resulting shuffle depends on live console RNG state, not the filename")
        return prior_state & MASK32
    state = rand_next(word1 >> 9)
    mixed = word1 << 14 & MASK32 | word2 >> 18
    state = state + mixed & MASK32
    state = rand_next(state)
    return word2 + state & MASK32

def seed_from_name(name: str, *, prior_state: int | None=None) -> int:
    word1, word2 = _filename.name_to_words(name)
    return seed_from_filename(word1, word2, prior_state=prior_state)
