from typing import Literal, Optional, get_args, TypeAlias, Union

from collections.abc import Iterable

HOTFIXES_DEFAULT_STR_ENCODING = "ascii"
HOTFIXES_DEFAULT_ENDIANNESS = "little"


ByteOrder: TypeAlias = Literal["little", "big"]


class ByteList(Iterable[int]):
    """A list of little-endian `uint8` values."""

    __data: list[int]
    __encoding: str
    __byteorder: ByteOrder

    def __init__(self, *args, **kwargs) -> None:
        self.__index = 0

        self.__data = kwargs["data"] if "data" in kwargs else [*args]
        self.__encoding = kwargs["encoding"] if "encoding" in kwargs else HOTFIXES_DEFAULT_STR_ENCODING
        byteorder = kwargs["byteorder"] if "byteorder" in kwargs else HOTFIXES_DEFAULT_ENDIANNESS

        if byteorder not in get_args(ByteOrder):
            byteorder = HOTFIXES_DEFAULT_ENDIANNESS

        self.__byteorder = byteorder

    def __iter__(self):
        self.__index = 0
        return self

    def __next__(self):
        if self.__index < len(self.__data):
            result = self.__data[self.__index]
            self.__index += 1
            return result
        else:
            raise StopIteration

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ByteList) and not isinstance(other, Iterable):
            return NotImplemented

        return self.__data == other

    def __repr__(self) -> str:
        return str(self.__data)

    def __getitem__(self, index: Union[int, slice]):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self.__data))
            return [self.__data[i] for i in range(start, stop, step)]
        elif isinstance(index, int):
            return self.__data[index]

    def __len__(self):
        return len(self.__data)

    # in methods

    @classmethod
    def from_str(cls, input: str, encoding: str = HOTFIXES_DEFAULT_STR_ENCODING, **kwargs):
        return cls(*list(input.encode(encoding)), encoding=encoding, **kwargs)

    @classmethod
    def from_list(cls, input: list[int], **kwargs):
        return cls(*input, **kwargs)

    # out methods

    def to_hex(self) -> str:
        hex_bytes = ""
        for number in self:
            number_hex = hex(number)[2:]
            if len(number_hex) % 2 != 0:
                number_hex = "0" + number_hex
            hex_bytes += number_hex

        return hex_bytes

    def to_int(self, unsigned: bool = True) -> int:
        return int.from_bytes(bytes.fromhex(self.to_hex()), byteorder=self.__byteorder, signed=not unsigned)

    def to_float(self) -> float:
        return float.fromhex(self.to_hex())

    def to_str(self, encoding: Optional[str] = None) -> str:
        if encoding is None:
            encoding = self.__encoding

        return bytes.fromhex(self.to_hex()).decode(encoding=encoding)
