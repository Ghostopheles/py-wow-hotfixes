from hotfixes.structures import Region, RecordState
from hotfixes.bytelist import ByteList


class DBCacheHeader:
    magic: int
    version: int
    build_id: int
    verification_hash: list[int]


class DBCacheEntry:
    magic: int
    region_id: Region
    push_id: int
    unique_id: int
    table_hash: int
    record_id: int
    data_size: int
    status: RecordState
    padding: list[int]
    data: ByteList


class DBCacheFile:
    header: DBCacheHeader
    entries: list[DBCacheEntry]


class DB2Header:
    magic: int
    version: int
    schemaString: str
    record_count: int
    field_count: int
    record_size: int
    string_table_size: int
    table_hash: int
    layout_hash: int
