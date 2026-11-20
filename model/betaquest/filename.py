from __future__ import annotations
NAME_LENGTH = 8
PAD_BYTE = 223

def _build_tables() -> tuple[dict[str, int], dict[int, str]]:
    byte_to_char: dict[int, str] = {}
    for i in range(26):
        byte_to_char[i + 171] = chr(ord('A') + i)
    for i in range(26):
        byte_to_char[i + 197] = chr(ord('a') + i)
    for i in range(10):
        byte_to_char[i] = chr(ord('0') + i)
    byte_to_char[234] = '.'
    byte_to_char[228] = '-'
    byte_to_char[223] = ' '
    char_to_byte = {char: value for value, char in byte_to_char.items()}
    return (char_to_byte, byte_to_char)
CHAR_TO_BYTE, BYTE_TO_CHAR = _build_tables()

class IllegalCharacterError(ValueError):
    pass

class NameTooLongError(ValueError):
    pass

def encode_name(name: str) -> bytes:
    if len(name) > NAME_LENGTH:
        raise NameTooLongError(f'Name too long, max {NAME_LENGTH} chars: {name!r}')
    buf = bytearray([PAD_BYTE] * NAME_LENGTH)
    for i, char in enumerate(name):
        try:
            buf[i] = CHAR_TO_BYTE[char]
        except KeyError:
            raise IllegalCharacterError(f'Illegal char {char!r} in name {name!r}') from None
    return bytes(buf)

def name_to_words(name: str) -> tuple[int, int]:
    return bytes_to_words(encode_name(name))

def bytes_to_words(raw: bytes) -> tuple[int, int]:
    if len(raw) != NAME_LENGTH:
        raise ValueError(f'expected {NAME_LENGTH} bytes, got {len(raw)}')
    word1 = int.from_bytes(raw[0:4], 'big')
    word2 = int.from_bytes(raw[4:8], 'big')
    return (word1, word2)

def words_to_bytes(word1: int, word2: int) -> bytes:
    return (word1 & 4294967295).to_bytes(4, 'big') + (word2 & 4294967295).to_bytes(4, 'big')

def name_from_words(word1: int, word2: int) -> str:
    out = []
    for byte in words_to_bytes(word1, word2):
        char = BYTE_TO_CHAR.get(byte)
        out.append(char if char is not None else f'\\{byte:02x}')
    return ''.join(out).rstrip()
