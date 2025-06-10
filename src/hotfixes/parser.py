import os
import httpx
import concurrent.futures

from enum import StrEnum
from dataclasses import dataclass
from typing import Optional, Any

from pycasclib.core import CascHandler, LocaleFlags

from hotfixes.dbdefs import DBDefs, Manifest, Build, ColumnDataType
from hotfixes.structures import RecordState
from hotfixes.t_structs import DBCacheFile, DBCacheEntry
from hotfixes.bytelist import ByteList
from hotfixes.utils import (
    convert_table_hash,
    bytes_to_int,
    dec_to_ascii,
    bytes_to_str,
    bytes_to_float,
    bytes_to_hex,
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

    def __init__(
        self,
        game_path: str,
        flavor: Flavor,
        dbcache_schema: Any,
        http_client: Optional[httpx.Client] = None,
        dbdefs_path: Optional[str] = None,
        max_threads: Optional[int] = None,
    ):
        self.game_path = game_path
        self.flavor = flavor

        self.casc = CascHandler(game_path, LocaleFlags.CASC_LOCALE_ENUS, product=BRANCH_NAMES[self.flavor])  # type: ignore

        self.dbdefs = DBDefs(http_client, dbdefs_path, self.casc)
        self.manifest = Manifest(http_client, dbdefs_path)

        self.dbcache_path = os.path.join(
            game_path, flavor, "Cache", "ADB", "enUS", "DBCache.bin"
        )
        self.buildinfo_path = os.path.join(game_path, ".build.info")

        self.struct_dbcache_file = dbcache_schema.STRUCT_DBCACHE_FILE

        self.cache_game_versions()

        self.max_threads = max_threads or os.cpu_count()

    def __del__(self):
        self.casc.close()

    def read_dbcache(self) -> DBCacheFile:
        with open(self.dbcache_path, "rb") as f:
            dbcache = self.struct_dbcache_file.parse(f.read())

        return dbcache  # type: ignore

    def convert_chunk(self, data: list[int], type: ColumnDataType, is_unsigned: bool):
        match type:
            case (
                ColumnDataType.Integer
                | ColumnDataType.U8
                | ColumnDataType.U16
                | ColumnDataType.U32
            ):
                return bytes_to_int(data, is_unsigned)
            case ColumnDataType.Float:
                return bytes_to_float(data)
            case ColumnDataType.String | ColumnDataType.Locstring:
                return bytes_to_str(data)
            case _:
                raise Exception("no data type?")

    def convert_to_hex_repr(self, hex_data: int) -> str:
        data = bytes_to_hex([hex_data])
        return f"0x{data}"

    def parse_hotfix_data(
        self, table_hash: str, table_name: str, hotfix_data: ByteList
    ) -> Optional[dict[str, Any]]:
        if len(hotfix_data) == 0:
            print("NO HOTFIX DATA " + table_name)
            return None

        defs = self.dbdefs.get_parsed_definitions_by_hash(table_hash)
        tbl_layout_hash = self.dbdefs.get_layout_for_table(table_name)
        if not tbl_layout_hash:
            print("NO TABLE LAYOUT FOR " + table_name)
            return None

        def_entries = defs.get_definitions_for_layout(tbl_layout_hash)

        data = list(hotfix_data)
        parsed_data = {}
        for def_entry in def_entries:
            chunk_name = def_entry.column
            if "noninline" in def_entry.annotation:
                continue

            chunk_width = int(def_entry.int_width / 8)

            column = defs.get_column_from_def_entry(def_entry)
            if column is None:
                continue

            chunk_type = column.type
            if (
                chunk_type == ColumnDataType.String
                or chunk_type == ColumnDataType.Locstring
            ):
                try:
                    null_index = data.index(0)
                    chunk_width = null_index + 1  # add one to hold the null character
                except ValueError:
                    pass

            if def_entry.array_size == 0:
                chunk_data = data[:chunk_width]
                chunk = self.convert_chunk(
                    chunk_data, chunk_type, def_entry.is_unsigned
                )
                data = data[chunk_width:]
            else:
                chunk = []
                for _ in range(def_entry.array_size):
                    chunk_data = data[:chunk_width]
                    value = self.convert_chunk(
                        chunk_data, chunk_type, def_entry.is_unsigned
                    )
                    chunk.append(value)  # type: ignore
                    data = data[chunk_width:]

            if isinstance(chunk, str):
                chunk = chunk[:-1]

            parsed_data[chunk_name] = chunk

        return parsed_data

    def get_hotfixes(
        self, filter: Optional[str] = None, show_cached_entries: Optional[bool] = False
    ) -> HotfixCollection:
        dbcache = self.read_dbcache()
        header_magic = dec_to_ascii(dbcache.header.magic)
        dbcache_version = dbcache.header.version
        build_id = dbcache.header.build_id

        all_hotfixes = []

        def handle_hotfix(entry: DBCacheEntry):
            if entry.push_id == -1 and not show_cached_entries:
                return

            tbl_hash = convert_table_hash(entry.table_hash)
            tbl_name = self.manifest.get_table_name_from_hash(tbl_hash)

            if filter and tbl_name != filter:
                return

            hotfix_data = self.parse_hotfix_data(tbl_hash, tbl_name, entry.data)
            if entry.status == RecordState.Valid:
                print(hotfix_data)

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

        results = []
        for entry in dbcache.entries:
            results.append(handle_hotfix(entry))

        # max_threads = self.max_threads
        # with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        #    futures = [
        #        executor.submit(handle_hotfix, entry) for entry in dbcache.entries
        #    ]

        # results = concurrent.futures.wait(futures)
        for result in results:
            if isinstance(result, Exception):
                print(str(result))

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
            self.__game_versions[entry["Product"]] = Build.from_version_str(
                entry["Version"]
            )

        current_branch = BRANCH_NAMES[self.flavor]
        self.current_version = self.__game_versions[current_branch]
