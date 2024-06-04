from enum import IntEnum
from construct import (
    Struct,
    Int32ul,
    Int32sl,
    Int8ul,
    Array,
    Enum,
    Byte,
    GreedyRange,
    this,
    PaddedString,
)


class RecordState(IntEnum):
    Valid = 1  # has data, overwrites source record if it exists
    Delete = 2  # no data, deletes source record
    Invalid = 3  # no data, invalidates current entry reverting to either the local source record or a server-side record
    NotPublic = 4  # no data


STRUCT_RECORD_STATE = Enum(Byte, RecordState)

STRUCT_DBCACHE_HEADER = Struct(
    "magic" / Int32ul,  # type: ignore
    "version" / Int32ul,  # type: ignore
    "build_id" / Int32ul,  # type: ignore
    "verification_hash" / Array(32, Int8ul),
)

STRUCT_DBCACHE_ENTRY = Struct(
    "magic" / Int32ul,  # type: ignore
    "region_id" / Int32sl,  # type: ignore
    "push_id" / Int32sl,  # type: ignore
    "unique_id" / Int32ul,  # type: ignore
    "table_hash" / Int32ul,  # type: ignore
    "record_id" / Int32ul,  # type: ignore
    "data_size" / Int32ul,  # type: ignore
    "status" / STRUCT_RECORD_STATE,
    "padding" / Array(3, Int8ul),
    "data" / Array(this.data_size, Int8ul),
)

STRUCT_DBCACHE_FILE = Struct(
    "header" / STRUCT_DBCACHE_HEADER,
    "entries" / GreedyRange(STRUCT_DBCACHE_ENTRY),
)

STRUCT_DB2_HEADER = Struct(
    "magic" / Int32ul,  # type: ignore
    "version" / Int32ul,  # type: ignore
    "schemaString" / PaddedString(128, "ascii"),
    "record_count" / Int32ul,  # type: ignore
    "field_count" / Int32ul,  # type: ignore
    "record_size" / Int32ul,  # type: ignore
    "string_table_size" / Int32ul,  # type: ignore
    "table_hash" / Int32ul,  # type: ignore
    "layout_hash" / Int32ul,  # type: ignore
)
