import pytest

from utils import extract_drive_file_id


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://drive.google.com/file/d/abcd1234/view?usp=sharing", "abcd1234"),
        ("https://drive.google.com/open?id=abcd1234&usp=sharing", "abcd1234"),
        ("https://docs.google.com/document/d/abcd1234/edit", "abcd1234"),
        ("abcd1234", "abcd1234"),
    ],
)
def test_extract_drive_file_id(value, expected):
    assert extract_drive_file_id(value) == expected
