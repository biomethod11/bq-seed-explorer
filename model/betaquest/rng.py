from __future__ import annotations
import struct
MASK32 = 4294967295
RAND_MULTIPLIER = 1664525
RAND_INCREMENT = 1013904223
INITIAL_SRAND_INT = 1

def rand_next(state: int) -> int:
    return (state & MASK32) * RAND_MULTIPLIER + RAND_INCREMENT & MASK32

def bits_to_f32(bits: int) -> float:
    return struct.unpack('>f', struct.pack('>I', bits & MASK32))[0]

def f32_to_bits(value: float) -> int:
    return struct.unpack('>I', struct.pack('>f', value))[0]

def round_to_f32(value: float) -> float:
    return struct.unpack('>f', struct.pack('>f', value))[0]

def rand_zero_one(state: int) -> tuple[float, int]:
    new_state = rand_next(state)
    bits = new_state & 8388607 | 1065353216
    return (bits_to_f32(bits) - 1.0, new_state)
