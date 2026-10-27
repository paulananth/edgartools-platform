"""Real PostgreSQL 16 protocol parity and fenced publication from raw inputs."""

import hashlib
import json
import random

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.rules import source_engine


def test_exact_sql_jsonb_bytes_and_hashes_on_numeric_unicode_and_nested_inputs(database):
    rng = random.Random(922016)
    bodies = ['-0', '-0.000', '0e100', '0e-100', '1e131071', '1e-16383',
              '{"x":1,"x":2}', '{"é":1,"bb":2,"𝄞":3,"a":4}',
              json.dumps(['"', '\\', '\b', '\f', '\n', '\t', '\r', '\x01', 'é', '𝄞'], ensure_ascii=False),
              '[' * 512 + '1.2300' + ']' * 512]
    for _ in range(1000):
        number = f"{rng.choice(['', '-'])}{rng.randrange(1, 10**25)}.{rng.randrange(10**12):012}e{rng.randrange(-50, 50):+}"
        bodies.append('{"bbb":[' + number + ',null,true],"a":{"é":"𝄞","x":-0.00}}')
    with database.admin.connect() as conn:
        for body in bodies:
            expected = conn.scalar(text("SELECT CAST(:b AS jsonb)::text"), {"b": body})
            actual = source_engine.postgres_jsonb_text(body)
            assert actual == expected
            assert hashlib.sha256(actual.encode()).hexdigest() == conn.scalar(
                text("SELECT encode(sha256(convert_to(CAST(:b AS jsonb)::text,'UTF8')),'hex')"), {"b": body})


@pytest.mark.parametrize("body", ['"\\u0000"', '"\\ud800"', '[NaN]', '[1,]', '1e131072', '1e-16384',
                                   '0e1073741824', '0e2147483647',
                                   '{"x":"\\u0000","x":1}', '{"x":1e-16384,"x":1}'])
def test_program_and_sql_refuse_invalid_jsonb(database, body):
    with database.admin.begin() as conn, pytest.raises(DBAPIError):
        conn.scalar(text("SELECT CAST(:b AS jsonb)"), {"b": body})
    with pytest.raises(ValueError):
        source_engine.postgres_jsonb_text(body)
