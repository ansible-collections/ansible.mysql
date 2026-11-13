# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.ansible.mysql.plugins.module_utils.user import (
    handle_grant_on_col,
    has_grant_on_col,
    normalize_col_grants,
    sort_column_order,
    privileges_unpack,
)


@pytest.mark.parametrize(
    'input_list,grant,output_tuple',
    [
        (['INSERT', 'DELETE'], 'INSERT', (None, None)),
        (['SELECT', 'UPDATE'], 'SELECT', (None, None)),
        (['INSERT', 'UPDATE', 'INSERT', 'DELETE'], 'DELETE', (None, None)),
        (['just', 'a', 'random', 'text'], 'blabla', (None, None)),
        (['SELECT (A, B, C)'], 'SELECT', (0, 0)),
        (['UPDATE', 'SELECT (A, B, C)'], 'SELECT', (1, 1)),
        (['UPDATE', 'REFERENCES (A, B, C)'], 'REFERENCES', (1, 1)),
        (['SELECT', 'UPDATE (A, B, C)'], 'UPDATE', (1, 1)),
        (['INSERT', 'SELECT (A', 'B)'], 'SELECT', (1, 2)),
        (['SELECT (A', 'B)', 'UPDATE'], 'SELECT', (0, 1)),
        (['INSERT', 'SELECT (A', 'B)', 'UPDATE'], 'SELECT', (1, 2)),
        (['INSERT (A, B)', 'SELECT (A', 'B)', 'UPDATE'], 'INSERT', (0, 0)),
        (['INSERT (A', 'B)', 'SELECT (A', 'B)', 'UPDATE'], 'INSERT', (0, 1)),
        (['INSERT (A', 'B)', 'SELECT (A', 'B)', 'UPDATE'], 'SELECT', (2, 3)),
        (['INSERT (A', 'B)', 'SELECT (A', 'C', 'B)', 'UPDATE'], 'SELECT', (2, 4)),
    ]
)
def test_has_grant_on_col(input_list, grant, output_tuple):
    """Tests has_grant_on_col function."""
    assert has_grant_on_col(input_list, grant) == output_tuple


@pytest.mark.parametrize(
    'input_,output',
    [
        ('SELECT (A)', 'SELECT (A)'),
        ('SELECT (`A`)', 'SELECT (A)'),
        ('UPDATE (B, A)', 'UPDATE (A, B)'),
        ('INSERT (`A`, `B`)', 'INSERT (A, B)'),
        ('REFERENCES (B, A)', 'REFERENCES (A, B)'),
        ('SELECT (`B`, `A`)', 'SELECT (A, B)'),
        ('SELECT (`B`, `A`, C)', 'SELECT (A, B, C)'),
    ]
)
def test_sort_column_order(input_, output):
    """Tests sort_column_order function."""
    assert sort_column_order(input_) == output


@pytest.mark.parametrize(
    'privileges,start,end,output',
    [
        (['UPDATE', 'SELECT (C, B, A)'], 1, 1, ['UPDATE', 'SELECT (A, B, C)']),
        (['INSERT', 'SELECT (A', 'B)'], 1, 2, ['INSERT', 'SELECT (A, B)']),
        (
            ['SELECT (`A`', 'B)', 'UPDATE', 'REFERENCES (B, A)'], 0, 1,
            ['SELECT (A, B)', 'UPDATE', 'REFERENCES (B, A)']),
        (
            ['INSERT', 'REFERENCES (`B`', 'A', 'C)', 'UPDATE (A', 'B)'], 1, 3,
            ['INSERT', 'REFERENCES (A, B, C)', 'UPDATE (A', 'B)']),
    ]
)
def test_handle_grant_on_col(privileges, start, end, output):
    """Tests handle_grant_on_col function."""
    assert handle_grant_on_col(privileges, start, end) == output


@pytest.mark.parametrize(
    'input_,expected',
    [
        (['SELECT'], ['SELECT']),
        (['SELECT (A, B)'], ['SELECT (A, B)']),
        (['SELECT (B, A)'], ['SELECT (A, B)']),
        (['UPDATE', 'SELECT (C, B, A)'], ['UPDATE', 'SELECT (A, B, C)']),
        (['INSERT', 'SELECT (A', 'B)'], ['INSERT', 'SELECT (A, B)']),
        (
            ['SELECT (`A`', 'B)', 'UPDATE', 'REFERENCES (B, A)'],
            ['SELECT (A, B)', 'UPDATE', 'REFERENCES (A, B)']),
        (
            ['INSERT', 'REFERENCES (`B`', 'A', 'C)', 'UPDATE (B', 'A)', 'DELETE'],
            ['INSERT', 'REFERENCES (A, B, C)', 'UPDATE (A, B)', 'DELETE']),
    ]
)
def test_normalize_col_grants(input_, expected):
    """Tests normalize_col_grants function."""
    assert normalize_col_grants(input_) == expected


@pytest.mark.parametrize(
    'priv,expected,mode,column_case_sensitive,ensure_usage',
    [
        ('mydb.*:SELECT', {'"mydb".*': ['SELECT']}, 'ANSI', False, False),
        ('mydb.*:SELECT', {'`mydb`.*': ['SELECT']}, 'NOTANSI', False, False),
        ('mydb.*:SELECT', {'"mydb".*': ['SELECT'], '*.*': ['USAGE']}, 'ANSI', False, True),
        ('mydb.*:SELECT', {'`mydb`.*': ['SELECT'], '*.*': ['USAGE']}, 'NOTANSI', False, True),
        ('mydb.*:SELECT (a)', {'`mydb`.*': ['SELECT (A)']}, 'NOTANSI', False, False),
        ('mydb.*:UPDATE (b, a)', {'`mydb`.*': ['UPDATE (a, b)']}, 'NOTANSI', True, False),
        ('mydb.*:SELECT (b, a, c)', {'`mydb`.*': ['SELECT (A, B, C)']}, 'NOTANSI', False, False),
        ('mydb.*:SELECT (b, a, c)', {'`mydb`.*': ['SELECT (a, b, c)']}, 'NOTANSI', True, False),
    ]
)
def test_privileges_unpack(priv, mode, column_case_sensitive, ensure_usage, expected):
    """Tests privileges_unpack function."""
    assert privileges_unpack(priv, mode, column_case_sensitive, ensure_usage) == expected


@pytest.mark.parametrize(
    'priv,expected',
    [
        # column-level after table-level must not leak onto the table
        ('db.tbl:INSERT/db.other:UPDATE(`col`)',
         {'`db`.`tbl`': ['INSERT'], '`db`.`other`': ['UPDATE(`col`)'], '*.*': ['USAGE']}),
        # leak onto *.* (the severe case)
        ('*.*:PROCESS,REPLICATION CLIENT/db.t:SELECT(`a`)',
         {'*.*': ['PROCESS', 'REPLICATION CLIENT'], '`db`.`t`': ['SELECT(`a`)']}),
        # multiple column grants after one table grant
        ('db.a:SELECT/db.b:UPDATE(`x`)/db.c:INSERT(`y`)',
         {'`db`.`a`': ['SELECT'], '`db`.`b`': ['UPDATE(`x`)'],
          '`db`.`c`': ['INSERT(`y`)'], '*.*': ['USAGE']}),
    ]
)
def test_privileges_unpack_column_grant_does_not_leak(priv, expected):
    """Column-level grants must not add privileges to earlier table-level entries."""
    assert privileges_unpack(priv, 'NONE', True) == expected
