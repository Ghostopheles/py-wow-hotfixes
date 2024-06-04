import pytest

from hotfixes.bytelist import ByteList


@pytest.mark.parametrize("input,expected", [("KeyboardTurner", [75, 101, 121, 98, 111, 97, 114, 100, 84, 117, 114, 110, 101, 114])])
def test_bytelist_from_str(input: str, expected: list[int]):
    assert ByteList.from_str(input) == expected


@pytest.mark.parametrize("input,expected", [([75, 101, 121, 98, 111, 97, 114, 100, 84, 117, 114, 110, 101, 114], "KeyboardTurner")])
def test_bytelist_to_str(input: list[int], expected: str):
    assert ByteList.from_list(input).to_str() == expected
