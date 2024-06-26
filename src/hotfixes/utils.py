from typing import Any

TABLE_HASH_LEN = 8


class Singleton:
    __instance = None

    def __new__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)

        return cls.__instance


def flatten_matches(matches: tuple[list[Any]] | list[Any], preserve_empty: bool = True) -> list[str]:
    if preserve_empty:
        return [thing for match in matches for thing in match]
    else:
        return [thing for match in matches for thing in match if thing and thing[0].isdigit()]


def dec_to_ascii(number: int) -> str:
    number_hex = hex(number)[2:]
    if len(number_hex) % 2 != 0:
        number_hex = "0" + number_hex

    number_bytes = bytes.fromhex(number_hex)
    out_string = number_bytes.decode("ascii")
    return out_string


def convert_table_hash(tbl_hash: int) -> str:
    converted = hex(tbl_hash)[2:].upper()
    converted_len = len(converted)
    if converted_len != TABLE_HASH_LEN:
        converted = ("0" * (TABLE_HASH_LEN - converted_len)) + converted

    return converted


def bytes_to_hex(data: list[int]) -> str:
    hex_bytes = ""
    for number in data:
        number_hex = hex(number)[2:]
        if len(number_hex) % 2 != 0:
            number_hex = "0" + number_hex
        hex_bytes += number_hex

    return hex_bytes


def bytes_to_int(data: list[int], is_unsigned: bool = True):
    return int.from_bytes(bytes(data), byteorder="little", signed=not is_unsigned)


def bytes_to_float(data: list[int]):
    hex_bytes = bytes_to_hex(data)

    return float.fromhex(hex_bytes)


def bytes_to_str(data: list[int]):
    hex_bytes = bytes_to_hex(data)

    return bytes.fromhex(hex_bytes).decode(encoding="utf8")


def str_to_bytes(input: str) -> list[int]:
    return list(input.encode("utf8"))
