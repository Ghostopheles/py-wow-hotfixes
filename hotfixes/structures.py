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
    "magic" / Int32ul,
    "version" / Int32ul,
    "build_id" / Int32ul,
    "verification_hash" / Array(32, Int8ul),
)

STRUCT_DBCACHE_ENTRY = Struct(
    "magic" / Int32ul,
    "region_id" / Int32sl,
    "push_id" / Int32sl,
    "unique_id" / Int32ul,
    "table_hash" / Int32ul,
    "record_id" / Int32ul,
    "data_size" / Int32ul,
    "status" / STRUCT_RECORD_STATE,
    "padding" / Array(3, Int8ul),
    "data" / Array(this.data_size, Int8ul),
)

STRUCT_DBCACHE_FILE = Struct(
    "header" / STRUCT_DBCACHE_HEADER, "entries" / GreedyRange(STRUCT_DBCACHE_ENTRY)
)

STRUCT_DB2_HEADER = Struct(
    "magic" / Int32ul,
    "version" / Int32ul,
    "schemaString" / PaddedString(128, "ascii"),
    "record_count" / Int32ul,
    "field_count" / Int32ul,
    "record_size" / Int32ul,
    "string_table_size" / Int32ul,
    "table_hash" / Int32ul,
    "layout_hash" / Int32ul,
)
