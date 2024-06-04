import os

from enum import IntEnum, StrEnum

from typing import Optional

from hotfixes.dbdefs import DBDefs, Manifest, Build, ColumnDataType
from hotfixes.structures import STRUCT_DBCACHE_FILE, RecordState
from hotfixes.utils import (
    convert_table_hash,
    bytes_to_int,
    dec_to_ascii,
    bytes_to_str,
    bytes_to_float,
)

DATA_INT_SIZE = 8


class Region(IntEnum):
    US = 1
    KR = 2
    EU = 3
    TW = 4
    CN = 5
    TR1 = 50
    TR2 = 60


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


class HotfixParser:
    current_version: Build

    def __init__(self, game_path: str, flavor: Flavor):
        self.dbdefs = DBDefs()
        self.manifest = Manifest()

        self.game_path = game_path
        self.flavor = flavor

        self.dbcache_path = os.path.join(game_path, flavor, "Cache", "ADB", "enUS", "DBCache.bin")
        self.buildinfo_path = os.path.join(game_path, ".build.info")

        self.cache_game_versions()

    def read_dbcache(self):
        with open(self.dbcache_path, "rb") as f:
            dbcache = STRUCT_DBCACHE_FILE.parse(f.read())

        return dbcache

    def format_hotfix_data(self, entry, filter: Optional[str]) -> Optional[str]:
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
                def_entries = defs.get_definitions_for_layout(tbl_layout_hash)

            hotfix_data = list(entry.data)
            parsed_data = {}
            for def_entry in def_entries:
                if "noninline,id" in def_entry.annotation:
                    continue

                chunk_name = def_entry.column
                chunk_width = int(def_entry.int_width / 8)  # each number in the hotfix data is 8 bytes

                column = defs.get_column_from_def_entry(def_entry)
                chunk_type = column.type

                chunk_data = hotfix_data[:chunk_width]
                match chunk_type:
                    case ColumnDataType.Integer:
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

    def print_hotfixes(self, filter: Optional[str]):
        dbcache = self.read_dbcache()

        header_magic = dec_to_ascii(dbcache.header.magic)
        print(f"DBCache Version: {dbcache.header.version} | Build: {dbcache.header.build_id}")
        print(f"Header Magic: {header_magic}")
        for entry in dbcache.entries:
            if entry.push_id != -1:  # ignore those pesky cached entries
                formatted_hotfix = self.format_hotfix_data(entry, filter)
                if formatted_hotfix is not None:
                    print(formatted_hotfix)

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
