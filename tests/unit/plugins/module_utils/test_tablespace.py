from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

import pytest

try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock

from ansible_collections.ansible.mysql.plugins.module_utils.tablespace import (
    _fetch_normalized_rows,
    _first_defined,
    _format_version,
    _get_mysql_80_tablespaces_query,
    _normalize_mysql_tablespace_row,
    _get_mysql_tablespaces_group_by,
    _to_int_or_none,
    _to_list_or_empty,
    ensure_tablespaces_supported,
    get_mysql_tablespaces,
    get_mysql_tablespace,
    get_server_version_tuple,
)
from ansible_collections.ansible.mysql.tests.unit.plugins.utils import dummy_cursor_class


@pytest.mark.parametrize(
    'server_version,expected',
    [
        ('5.7.6-mysql', (5, 7, 6)),
        ('8.0.38-commercial', (8, 0, 38)),
        ('8.4.9-1.el9', (8, 4, 9)),
    ]
)
def test_get_server_version_tuple(server_version, expected):
    cursor = dummy_cursor_class(server_version, 'dict')
    assert get_server_version_tuple(cursor) == expected


def test_get_server_version_tuple_pads_short_versions():
    cursor = dummy_cursor_class('8.0-community', 'dict')

    assert get_server_version_tuple(cursor) == (8, 0, 0)


def test_ensure_tablespaces_supported_returns_mysql_version_tuple():
    module = MagicMock()
    cursor = dummy_cursor_class('8.0.35-mysql', 'dict')

    assert ensure_tablespaces_supported(module, cursor) == (8, 0, 35)
    module.fail_json.assert_not_called()


def test_ensure_tablespaces_supported_fails_for_unsupported_server(monkeypatch):
    module = MagicMock()
    module.fail_json.side_effect = RuntimeError
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.module_utils.tablespace.get_server_implementation',
        lambda _module, _cursor: 'unsupported',
    )

    with pytest.raises(RuntimeError):
        ensure_tablespaces_supported(module, cursor)

    module.fail_json.assert_called_once_with(
        msg='Tablespace operations are supported only by MySQL.'
    )


def test_ensure_tablespaces_supported_fails_for_old_mysql():
    module = MagicMock()
    module.fail_json.side_effect = RuntimeError
    cursor = dummy_cursor_class('5.7.5-mysql', 'dict')

    with pytest.raises(RuntimeError):
        ensure_tablespaces_supported(module, cursor)

    module.fail_json.assert_called_once_with(
        msg='Tablespace operations require MySQL 5.7.6 or later.'
    )


def test_normalize_tablespace_row_for_mysql_uses_canonical_keys():
    row = {
        'FILE_ID': '17',
        'TABLESPACE_NAME': 'app_data',
        'FILE_TYPE': 'TABLESPACE',
        'ENGINE': 'InnoDB',
        'EXTENT_SIZE': '1048576',
        'AUTOEXTEND_SIZE': '8388608',
        'MAXIMUM_SIZE': None,
        'FILE_NAME': '/var/lib/mysql/app_data.ibd',
        'FS_BLOCK_SIZE': '4096',
        'FILE_SIZE': '16777216',
        'ALLOCATED_SIZE': '8388608',
        'PAGE_SIZE': '16384',
        'ZIP_PAGE_SIZE': '0',
        'SPACE_TYPE': 'General',
        'STATUS': 'NORMAL',
        'EXTRA': 'General tablespace',
        'STATE': 'active',
        'ENCRYPTION': 'N',
        'ATTACHED_TABLES': 'app/order_items,app/orders',
    }

    assert _normalize_mysql_tablespace_row(row) == {
        'server_implementation': 'mysql',
        'name': 'app_data',
        'space_id': 17,
        'engine': 'InnoDB',
        'file_type': 'TABLESPACE',
        'extent_size': 1048576,
        'autoextend_size': 8388608,
        'maximum_size': None,
        'datafile': '/var/lib/mysql/app_data.ibd',
        'filesystem_block_size': 4096,
        'status': 'NORMAL',
        'comment': 'General tablespace',
        'page_size': 16384,
        'file_size': 16777216,
        'allocated_size': 8388608,
        'zip_page_size': 0,
        'space_type': 'General',
        'state': 'active',
        'encryption': 'N',
        'attached_tables': ['app/order_items', 'app/orders'],
    }


def test_normalize_tablespace_row_sets_missing_mysql_80_fields_to_none():
    row = {
        'FILE_ID': '17',
        'TABLESPACE_NAME': 'app_data',
        'FILE_TYPE': 'TABLESPACE',
        'ENGINE': 'InnoDB',
        'EXTENT_SIZE': '1048576',
        'AUTOEXTEND_SIZE': '8388608',
        'MAXIMUM_SIZE': None,
        'FILE_NAME': '/var/lib/mysql/app_data.ibd',
        'FS_BLOCK_SIZE': '4096',
        'FILE_SIZE': '16777216',
        'ALLOCATED_SIZE': '8388608',
        'PAGE_SIZE': '16384',
        'ZIP_PAGE_SIZE': '0',
        'SPACE_TYPE': 'General',
        'STATUS': 'NORMAL',
        'EXTRA': 'General tablespace',
        'ATTACHED_TABLES': 'app/orders',
    }

    normalized = _normalize_mysql_tablespace_row(row)

    assert normalized['encryption'] is None
    assert normalized['state'] is None


def test_get_mysql_tablespace_returns_one_normalized_mysql_row():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            'FILE_ID': '17',
            'TABLESPACE_NAME': 'app_data',
            'FILE_TYPE': 'TABLESPACE',
            'ENGINE': 'InnoDB',
            'EXTENT_SIZE': '1048576',
            'AUTOEXTEND_SIZE': '8388608',
            'MAXIMUM_SIZE': None,
            'FILE_NAME': './app_data.ibd',
            'FS_BLOCK_SIZE': '4096',
            'FILE_SIZE': '16777216',
            'ALLOCATED_SIZE': '8388608',
            'PAGE_SIZE': '16384',
            'ZIP_PAGE_SIZE': '0',
            'SPACE_TYPE': 'General',
            'STATUS': 'NORMAL',
            'EXTRA': 'General tablespace',
            'STATE': 'active',
            'ENCRYPTION': 'N',
            'ATTACHED_TABLES': 'app/orders',
        }
    ]

    assert get_mysql_tablespace(cursor, (8, 0, 36), 'app_data') == {
        'server_implementation': 'mysql',
        'name': 'app_data',
        'space_id': 17,
        'engine': 'InnoDB',
        'file_type': 'TABLESPACE',
        'extent_size': 1048576,
        'autoextend_size': 8388608,
        'maximum_size': None,
        'datafile': './app_data.ibd',
        'filesystem_block_size': 4096,
        'status': 'NORMAL',
        'comment': 'General tablespace',
        'page_size': 16384,
        'file_size': 16777216,
        'allocated_size': 8388608,
        'zip_page_size': 0,
        'space_type': 'General',
        'state': 'active',
        'encryption': 'N',
        'attached_tables': ['app/orders'],
    }

    executed_query, params = cursor.execute.call_args[0]
    assert 'INFORMATION_SCHEMA.INNODB_TABLESPACES AS ts' in executed_query
    assert params == ('app_data',)


def test_get_mysql_tablespaces_uses_mysql_57_metadata_without_name_filter():
    cursor = MagicMock()
    cursor.fetchall.return_value = []

    assert get_mysql_tablespaces(cursor, (5, 7, 42)) == []

    (executed_query,) = cursor.execute.call_args[0]
    assert 'INFORMATION_SCHEMA.INNODB_SYS_TABLESPACES AS ts' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_DATAFILES AS df' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_TABLES AS t' in executed_query
    assert 'AND f.TABLESPACE_NAME = %s' not in executed_query


@pytest.mark.parametrize(
    'server_version,expected_fragment,unexpected_fragments',
    [
        (
            (8, 0, 12),
            'ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, NULL AS ENCRYPTION, NULL AS STATE, ',
            ['ts.ENCRYPTION, NULL AS STATE', 'ts.ENCRYPTION, ts.STATE'],
        ),
        (
            (8, 0, 13),
            'ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, ts.ENCRYPTION, NULL AS STATE, ',
            ['NULL AS ENCRYPTION', 'ts.ENCRYPTION, ts.STATE'],
        ),
        (
            (8, 0, 14),
            'ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, ts.ENCRYPTION, ts.STATE, ',
            ['NULL AS ENCRYPTION', 'NULL AS STATE'],
        ),
    ]
)
def test_get_mysql_80_tablespaces_query_uses_version_specific_columns(
    server_version,
    expected_fragment,
    unexpected_fragments,
):
    query = _get_mysql_80_tablespaces_query(server_version)

    assert expected_fragment in query
    for fragment in unexpected_fragments:
        assert fragment not in query


def test_get_mysql_tablespaces_filters_by_explicit_empty_name():
    cursor = MagicMock()
    cursor.fetchall.return_value = []

    assert get_mysql_tablespaces(cursor, (8, 0, 36), name='') == []

    executed_query, params = cursor.execute.call_args[0]
    assert 'AND f.TABLESPACE_NAME = %s' in executed_query
    assert params == ('',)


def test_get_mysql_tablespace_returns_none_when_missing():
    cursor = MagicMock()
    cursor.fetchall.return_value = []

    assert get_mysql_tablespace(cursor, (8, 0, 36), 'missing_tablespace') is None


def test_fetch_normalized_rows_re_raises_without_module():
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError('metadata denied')

    with pytest.raises(RuntimeError, match='metadata denied'):
        _fetch_normalized_rows(cursor, 'SELECT 1', None)


def test_fetch_normalized_rows_calls_fail_json_when_module_is_provided():
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError('metadata denied')
    module = MagicMock()
    module.fail_json.side_effect = RuntimeError('fail_json called')

    with pytest.raises(RuntimeError, match='fail_json called'):
        _fetch_normalized_rows(cursor, 'SELECT 1', None, module=module)

    module.fail_json.assert_called_once()
    assert module.fail_json.call_args[1]['msg'] == "Cannot execute SQL 'SELECT 1': metadata denied"


@pytest.mark.parametrize(
    'server_version,expected_fragment,unexpected_fragment',
    [
        ((5, 7, 42), 'ts.SPACE_TYPE ORDER BY f.TABLESPACE_NAME', 'ts.ENCRYPTION'),
        ((8, 0, 12), 'ts.SPACE_TYPE ORDER BY f.TABLESPACE_NAME', 'ts.ENCRYPTION'),
        ((8, 0, 13), 'ts.SPACE_TYPE, ts.ENCRYPTION ORDER BY f.TABLESPACE_NAME', 'ts.STATE'),
        ((8, 0, 14), 'ts.ENCRYPTION, ts.STATE ORDER BY f.TABLESPACE_NAME', 'INNODB_SYS_TABLESPACES'),
    ]
)
def test_get_mysql_tablespaces_group_by_uses_version_specific_columns(
    server_version,
    expected_fragment,
    unexpected_fragment,
):
    query = _get_mysql_tablespaces_group_by(server_version)

    assert expected_fragment in query
    assert unexpected_fragment not in query


@pytest.mark.parametrize(
    'row,keys,expected',
    [
        ({'PATH': None, 'FILENAME': './app_data.ibd'}, ('PATH', 'FILENAME'), './app_data.ibd'),
        ({'PATH': None, 'FILENAME': None}, ('PATH', 'FILENAME'), None),
    ]
)
def test_first_defined_returns_first_non_none_value(row, keys, expected):
    assert _first_defined(row, *keys) == expected


@pytest.mark.parametrize(
    'value,expected',
    [
        (None, None),
        ('17', 17),
        (17, 17),
    ]
)
def test_to_int_or_none_handles_none_and_numeric_values(value, expected):
    assert _to_int_or_none(value) == expected


@pytest.mark.parametrize(
    'value,expected',
    [
        (None, []),
        (['app/orders', 'app/order_items'], ['app/orders', 'app/order_items']),
        (('app/orders', 'app/order_items'), ['app/orders', 'app/order_items']),
        ('app/orders, app/order_items , ,app/audit', ['app/orders', 'app/order_items', 'app/audit']),
    ]
)
def test_to_list_or_empty_normalizes_sequences_and_csv_strings(value, expected):
    assert _to_list_or_empty(value) == expected


def test_format_version_joins_version_parts():
    assert _format_version((8, 0, 23)) == '8.0.23'
