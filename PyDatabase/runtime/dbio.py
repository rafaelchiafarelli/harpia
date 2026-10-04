"""Bulk import/export of a whole table as JSON or XML (port of the C++
``harpia::dbio`` in ``Database/templates/dbio.h.tmpl``).

A generated ``harpia_generated/dbio/<name>_<hash>_dbio.py`` binds these to
one message's DAO. The formats are the C++ ones, byte for byte for the same
rows:

- JSON: newline-delimited, one :func:`harpia_runtime.json.to_json` document
  per row, each followed by ``\\n``; blank lines are skipped on import.
- XML: ``<<name>_list>`` wrapping one :func:`harpia_runtime.xml.to_xml`
  element per row; on import every child element of the root is one row
  (read with ``from_xml_element``, whatever its tag, like C++).

Rows are exported in ``Dao.list()`` order (primary key).

Different from C++ on purpose (C++ returns ``false`` and keeps the rows it
had already created): the whole input is parsed first, so malformed input
raises :class:`ValueError` and writes nothing, and the rows are then
created in one transaction, so a database error (for example a duplicate
key) raises and rolls every row back.
"""
import xml.etree.ElementTree as ET
from typing import Any

from google.protobuf.message import Message

from harpia_runtime.db.dao import Dao
from harpia_runtime.json import from_json, to_json
from harpia_runtime.xml import from_xml_element, to_xml


def _create_all(dao: Dao[Any], rows: list[Message]) -> int:
    with dao._tx() as cur:
        for msg in rows:
            dao._create(cur, msg)
    return len(rows)


def export_json(dao: Dao[Any]) -> str:
    """Every row of ``dao``'s table as newline-delimited JSON."""
    return "".join(to_json(row) + "\n" for row in dao.list())


def import_json(dao: Dao[Any], text: str) -> int:
    """Create one row per non-empty line of newline-delimited JSON.

    Returns:
        The number of rows created.

    Raises:
        ValueError: A line is not a valid message (nothing is written).
    """
    rows: list[Message] = []
    for number, line in enumerate(text.split("\n"), 1):
        if not line:
            continue
        msg = dao.MESSAGE()
        if not from_json(line, msg):
            name = dao.MESSAGE.DESCRIPTOR.name
            raise ValueError(f"line {number}: not a valid {name} JSON document")
        rows.append(msg)
    return _create_all(dao, rows)


def export_xml(dao: Dao[Any], wrapper: str) -> str:
    """Every row of ``dao``'s table as ``<wrapper>...</wrapper>``."""
    return "<{0}>{1}</{0}>".format(wrapper, "".join(to_xml(row) for row in dao.list()))


def import_xml(dao: Dao[Any], text: str) -> int:
    """Create one row per child element of the document's root element.

    Returns:
        The number of rows created.

    Raises:
        ValueError: The document does not parse (nothing is written).
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"not a valid XML document: {e}") from e
    rows: list[Message] = []
    for element in root:
        msg = dao.MESSAGE()
        from_xml_element(element, msg)
        rows.append(msg)
    return _create_all(dao, rows)
