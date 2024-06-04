import os
import re
import json
import httpx
import zipfile

from enum import StrEnum
from typing import Optional
from dataclasses import dataclass

from hotfixes import CACHE_PATH
from hotfixes.structures import STRUCT_DB2_HEADER
from hotfixes.utils import Singleton, flatten_matches, convert_table_hash

DB2_EXPORT_PATH = "T:/Data/dbcs/"

DBD_PATH = os.path.join(CACHE_PATH, "WoWDBDefs-master")
DBD_URL = "https://github.com/wowdev/WoWDBDefs/archive/refs/heads/master.zip"

# shoutout to my main man ChatGPT-4o for writing these regex patterns (except the column one)

LAYOUT_HEADER_PATTERN = r"^LAYOUT\s+(.+)(?:,\s*(.+))*"
LAYOUT_BUILD_PATTERN = (
    r"BUILD\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)?)(?:,\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)?))*"
)

LAYOUT_COLUMN_PATTERN = r"(?>\$(.+)\$)?(.+)<(.+)>(?>\[(.+)\])?"
LAYOUT_COLUMN_RE = re.compile(LAYOUT_COLUMN_PATTERN)


class ColumnDataType(StrEnum):
    Integer = "int"
    String = "string"
    Float = "float"
    Locstring = "locstring"
    U8 = "u8"


@dataclass
class Foreign:
    table: str
    column: str


@dataclass
class Column:
    type: ColumnDataType
    name: str
    confirmed_name: bool
    foreign: Optional[Foreign]
    comment: Optional[str]


@dataclass
class Build:
    major: int
    minor: int
    patch: int
    build: int

    def to_string(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}.{self.build}"

    @classmethod
    def from_version_str(cls, version: str):
        if "-" in version:
            return BuildRange.from_version_str(version)

        return cls(*[int(number) for number in version.split(".", 4)])

    def is_equal(self, other):
        if other is None:
            return False
        return self.major == other.major and self.minor == other.minor and self.patch == other.patch and self.build == other.build

    def __lt__(self, other):
        return self.major < other.major or self.minor < other.minor or self.patch < other.patch or self.build < other.build

    def __gt__(self, other):
        return self.major > other.major or self.minor > other.minor or self.patch > other.patch or self.build > other.build


@dataclass
class BuildRange:
    lower: Build
    upper: Build

    @classmethod
    def from_version_str(cls, version: str):
        if "-" not in version:
            return Build.from_version_str(version)

        version_split = version.split("-")
        return cls(
            Build.from_version_str(version_split[0]),
            Build.from_version_str(version_split[1]),
        )


@dataclass
class DefinitionEntry:
    column: str
    int_width: int
    is_unsigned: bool
    array_size: int
    annotation: str
    comment: str


@dataclass
class Definitions:
    builds: list[Build | BuildRange]
    layouts: list[str]
    comments: list[str]
    entries: list[DefinitionEntry]

    def supports_version(self, version: Build) -> bool:
        for build in self.builds:
            if isinstance(build, Build):
                if build.is_equal(version):
                    return True
            elif isinstance(build, BuildRange):
                if version > build.lower and version < build.upper:
                    return True

        return False


@dataclass
class DBD:
    columns: list[Column]
    definitions: list[Definitions]

    def get_definitions_for_build(self, build: Build) -> list[DefinitionEntry]:
        entries = []
        for definition in self.definitions:
            if definition.supports_version(build):
                entries.extend(definition.entries)

        return entries

    def get_definitions_for_layout(self, layout_hash: str) -> list[DefinitionEntry]:
        entries = []
        for definition in self.definitions:
            if layout_hash in definition.layouts:
                entries.extend(definition.entries)

        return entries

    def get_column_from_def_entry(self, def_entry: DefinitionEntry):
        for column in self.columns:
            if column.name == def_entry.column:
                return column


class DBDefs:
    def __init__(self):
        self.update_definitions()

    def should_update_definitions(self) -> bool:
        if not os.path.exists(DBD_PATH):
            return True

        return False

    def update_definitions(self):
        if not self.should_update_definitions():
            return

        if not os.path.exists(DBD_PATH):
            os.makedirs(DBD_PATH, exist_ok=True)

        response = httpx.get(DBD_URL, follow_redirects=True)
        response.raise_for_status()

        with open("dbd.zip", "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

        file = zipfile.ZipFile("dbd.zip", "r")
        file.extractall(CACHE_PATH)
        file.close()

        os.remove("dbd.zip")

    def parse_column_line(self, column: str):
        elements = column.split(" ")

        type = None
        column_fk = None
        comment = None

        has_fk = "<" in elements[0]
        if has_fk:
            type_split = elements[0].split("<")
            type = type_split[0]
            fk = type_split[1].split("::")
            foreign_table = fk[0]
            foreign_column = fk[1].replace(">", "")
            column_fk = Foreign(foreign_table, foreign_column)
        else:
            type = elements[0]

        column_name = elements[1]
        guessed_name = column_name.endswith("?")
        if guessed_name:
            column_name = column_name.removesuffix("?")

        if len(elements) > 2:
            if elements[3].startswith("//"):
                comment = " ".join(*elements[3:])

        parsed_column = Column(
            type=ColumnDataType(type),
            name=column_name,
            confirmed_name=not guessed_name,
            foreign=column_fk or None,
            comment=comment or None,
        )

        return parsed_column

    def parse_columns(self, *args):
        columns = []
        for line in args:
            column = self.parse_column_line(line)
            columns.append(column)

        return columns

    def parse_layout(self, section: list[str]):
        matches = re.findall(LAYOUT_HEADER_PATTERN, section[0])
        layout_hashes = flatten_matches(matches, False)

        # get all supported builds
        i = 0
        supported_builds = []
        for line in section[1:]:
            i += 1
            build_matches = re.findall(LAYOUT_BUILD_PATTERN, line)
            if not build_matches:
                break

            supported_builds.extend(flatten_matches(build_matches, False))

        builds = [Build.from_version_str(version) for version in supported_builds]

        # read columns now
        columns = []
        for line in section[i:]:
            column_matches = re.findall(LAYOUT_COLUMN_PATTERN, line)
            if not column_matches:
                break

            columns_flattened = flatten_matches(column_matches)
            annotations = columns_flattened[0]
            column_name = columns_flattened[1]
            int_width = columns_flattened[2]
            is_unsigned = False
            if int_width.startswith("u"):
                int_width = int_width.replace("u", "")
                is_unsigned = True

            array_size = columns_flattened[3] or 0

            entry = DefinitionEntry(
                column_name,
                int(int_width),
                is_unsigned,
                int(array_size),
                annotations,
                "uwu",
            )
            columns.append(entry)

        return Definitions(builds, layout_hashes, ["uwu"], columns)

    def parse_dbd(self, dbd: str) -> DBD:
        definitions = []

        dbd_split = dbd.split("\n\n")
        for section in dbd_split:
            section_split = section.split("\n")
            if section_split[0] == "COLUMNS":
                columns = self.parse_columns(*section_split[1:])
            elif section_split[0].startswith("LAYOUT"):
                definitions.append(self.parse_layout(section_split))

        return DBD(columns, definitions)

    def get_definitions_for_table(self, tbl_name: str):
        path = os.path.join(DBD_PATH, "definitions", f"{tbl_name}.dbd")
        with open(path) as f:
            definitions = f.read()

        return definitions

    def get_definitions_for_table_by_hash(self, tbl_hash: str):
        tbl_name = Manifest().get_table_name_from_hash(tbl_hash)
        return self.get_definitions_for_table(tbl_name)

    def get_parsed_definitions_by_hash(self, tbl_hash: str) -> DBD:
        defs = self.get_definitions_for_table_by_hash(tbl_hash)
        return self.parse_dbd(defs)

    def get_layout_for_table(self, tbl_name: str, build: Build):
        db2_path = os.path.join(
            DB2_EXPORT_PATH,
            build.to_string(),
            "dbfilesclient",
            f"{tbl_name.lower()}.db2",
        )

        if not os.path.exists(db2_path):
            print(f"Exported DB2 not found > DB2: {tbl_name} Build: {build.to_string()}")

        with open(db2_path, "rb") as f:
            db2_header = STRUCT_DB2_HEADER.parse(f.read())

        return convert_table_hash(db2_header.layout_hash)


UNK_TBL = "Unknown"


class Manifest(Singleton):
    __name_lookup: dict[str, str]

    def __init__(self):
        self.__name_lookup = {}
        self.load_manifest()

    def load_manifest(self):
        manifest = None
        manifest_path = os.path.join(DBD_PATH, "manifest.json")

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        if manifest is None:
            raise Exception("bruh")  # TODO: some kind of proper error handling here

        for tbl in manifest:
            self.__name_lookup[tbl["tableHash"]] = tbl["tableName"]

    def get_table_name_from_hash(self, tbl_hash: str) -> str:
        tbl_hash = tbl_hash.upper()

        if tbl_hash in self.__name_lookup:
            return self.__name_lookup[tbl_hash]
        else:
            return UNK_TBL  # probably also send an alert somewhere idk
