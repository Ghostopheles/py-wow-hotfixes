import os
import httpx

from enum import StrEnum
from dataclasses import dataclass
from typing import Optional, Any

from hotfixes.dbdefs import DBDefs, Manifest, Build, ColumnDataType
from hotfixes.structures import RecordState, Region
from hotfixes.t_structs import DBCacheFile, DBCacheEntry
from hotfixes.bytelist import ByteList
from hotfixes.utils import (
    convert_table_hash,
    bytes_to_int,
    dec_to_ascii,
    bytes_to_str,
    bytes_to_float,
)


class Flavor(StrEnum):
    Live = "_retail_"
    Beta = "_beta_"
    PTR = "_ptr_"
    XPTR = "_xptr_"


BRANCH_NAMES = {
    Flavor.Live: "wow",
    Flavor.Beta: "wow_beta",
    Flavor.PTR: "wowt",
    Flavor.XPTR: "wowxptr",
}


@dataclass
class Hotfix:
    PushID: int
    UniqueID: int
    TableHash: str
    TableName: str
    Status: RecordState
    RecordID: int
    Data: Optional[dict[str, Any]]


@dataclass
class HotfixCollection:
    DBCacheVersion: int
    HeaderMagic: str
    Hotfixes: list[Hotfix]
    BuildId: int


class HotfixParser:
    current_version: Build

    def __init__(self, game_path: str, flavor: Flavor, dbcache_schema: Any, http_client: Optional[httpx.Client] = None, dbdefs_path: Optional[str] = None):
        self.dbdefs = DBDefs(http_client, dbdefs_path)
        self.manifest = Manifest(http_client, dbdefs_path)

        self.game_path = game_path
        self.flavor = flavor

        self.dbcache_path = os.path.join(game_path, flavor, "Cache", "ADB", "enUS", "DBCache.bin")
        self.buildinfo_path = os.path.join(game_path, ".build.info")

        self.struct_dbcache_file = dbcache_schema.STRUCT_DBCACHE_FILE

        self.cache_game_versions()

    def read_dbcache(self) -> DBCacheFile:
        with open(self.dbcache_path, "rb") as f:
            dbcache = self.struct_dbcache_file.parse(f.read())

        return dbcache  # type: ignore

    def format_hotfix_data(self, entry: DBCacheEntry, filter: Optional[str]) -> Optional[str]:
        tbl_hash = convert_table_hash(entry.table_hash)
        tbl_name = self.manifest.get_table_name_from_hash(tbl_hash)

        if filter and tbl_name.lower() != filter.lower():
            return None

        formatted = f"""
PushID: {entry.push_id}
    Region: {Region(entry.region_id).name}
    Unique ID: {entry.unique_id}
    Table Hash: {tbl_hash}
    Table Name: {tbl_name}
    Status: {entry.status}"""

        if entry.status == RecordState.Valid.name:
            defs = self.dbdefs.get_parsed_definitions_by_hash(tbl_hash)
            def_entries = defs.get_definitions_for_build(self.current_version)

            if len(def_entries) == 0:
                tbl_layout_hash = self.dbdefs.get_layout_for_table(tbl_name, self.current_version)
                if not tbl_layout_hash:
                    return None

                def_entries = defs.get_definitions_for_layout(tbl_layout_hash)

            hotfix_data = list(entry.data)
            parsed_data = {}
            for def_entry in def_entries:
                if "noninline,id" in def_entry.annotation:
                    continue

                chunk_name = def_entry.column
                chunk_width = int(def_entry.int_width / 8)  # each number in the hotfix data is 8 bytes

                column = defs.get_column_from_def_entry(def_entry)
                if column is None:
                    continue

                chunk_type = column.type
                chunk_data = hotfix_data[:chunk_width]
                match chunk_type:
                    case ColumnDataType.Integer | ColumnDataType.U8 | ColumnDataType.U16:
                        chunk = bytes_to_int(chunk_data, def_entry.is_unsigned)
                    case ColumnDataType.Float:
                        chunk = bytes_to_float(chunk_data)
                    case ColumnDataType.String | ColumnDataType.Locstring:
                        chunk = bytes_to_str(chunk_data)
                    case _:
                        raise Exception("no data type?")

                parsed_data[chunk_name] = chunk

                hotfix_data = hotfix_data[chunk_width:]

            formatted += f"\n\tRecord ID: {entry.record_id}"

            for name, value in parsed_data.items():
                formatted += f"\n\t\t{name}: {value}"

        return formatted

    def print_hotfixes(self, filter: Optional[str] = None):
        dbcache = self.read_dbcache()

        header_magic = dec_to_ascii(dbcache.header.magic)
        print(f"DBCache Version: {dbcache.header.version} | Build: {dbcache.header.build_id}")
        print(f"Header Magic: {header_magic}")
        for entry in dbcache.entries:
            if entry.push_id != -1:  # ignore those pesky cached entries
                formatted_hotfix = self.format_hotfix_data(entry, filter)
                if formatted_hotfix is not None:
                    print(formatted_hotfix)

    def parse_hotfix_data(self, table_hash: str, table_name: str, hotfix_data: ByteList) -> Optional[dict[str, Any]]:
        defs = self.dbdefs.get_parsed_definitions_by_hash(table_hash)
        def_entries = defs.get_definitions_for_build(self.current_version)

        if len(def_entries) == 0:
            tbl_layout_hash = self.dbdefs.get_layout_for_table(table_name, self.current_version)
            if not tbl_layout_hash:
                return None

            def_entries = defs.get_definitions_for_layout(tbl_layout_hash)

        data = list(hotfix_data)
        parsed_data = {}
        for def_entry in def_entries:
            if "noninline,id" in def_entry.annotation:
                continue

            chunk_name = def_entry.column
            chunk_width = int(def_entry.int_width / 8)  # each number in the hotfix data is 8 bytes

            column = defs.get_column_from_def_entry(def_entry)
            if column is None:
                continue

            chunk_type = column.type
            chunk_data = data[:chunk_width]
            match chunk_type:
                case ColumnDataType.Integer | ColumnDataType.U8 | ColumnDataType.U16:
                    chunk = bytes_to_int(chunk_data, def_entry.is_unsigned)
                case ColumnDataType.Float:
                    chunk = bytes_to_float(chunk_data)
                case ColumnDataType.String | ColumnDataType.Locstring:
                    chunk = bytes_to_str(chunk_data)
                case _:
                    raise Exception("no data type?")

            parsed_data[chunk_name] = chunk

            data = data[chunk_width:]

        return parsed_data

    def get_hotfixes(self, filter: Optional[str] = None, show_cached_entries: Optional[bool] = False) -> HotfixCollection:
        dbcache = self.read_dbcache()
        header_magic = dec_to_ascii(dbcache.header.magic)
        dbcache_version = dbcache.header.version
        build_id = dbcache.header.build_id

        all_hotfixes = []
        for entry in dbcache.entries:
            if entry.push_id == -1 and not show_cached_entries:
                continue

            tbl_hash = convert_table_hash(entry.table_hash)
            tbl_name = self.manifest.get_table_name_from_hash(tbl_hash)

            if filter and tbl_name != filter:
                continue

            hotfix_data = self.parse_hotfix_data(tbl_hash, tbl_name, entry.data)

            hotfix = Hotfix(
                entry.push_id,
                entry.unique_id,
                tbl_hash,
                tbl_name,
                RecordState[entry.status],  # type: ignore
                entry.record_id,
                hotfix_data,
            )
            all_hotfixes.append(hotfix)

        return HotfixCollection(dbcache_version, header_magic, all_hotfixes, build_id)

    def read_build_info(self):
        with open(self.buildinfo_path, "r") as f:
            data = f.read()

        data_split = data.split("\n")
        index: list[str] = []
        output = []

        for line in data_split:
            line_split = line.split("|")

            if len(line_split) > 1:
                if not index:
                    for index_key in line_split:
                        key = index_key.split("!")
                        index.append(key[0].replace(" ", ""))
                else:
                    line_entry = {}
                    for i, entry in enumerate(line_split):
                        k = index[i]
                        line_entry[k] = entry
                    output.append(line_entry)

        return output

    def cache_game_versions(self):
        self.__game_versions = {}

        buildinfo = self.read_build_info()
        for entry in buildinfo:
            self.__game_versions[entry["Product"]] = Build.from_version_str(entry["Version"])

        current_branch = BRANCH_NAMES[self.flavor]
        self.current_version = self.__game_versions[current_branch]
