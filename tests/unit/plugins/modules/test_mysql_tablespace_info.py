# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock

from ansible_collections.ansible.mysql.plugins.modules import mysql_tablespace_info
from ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info import (
    format_tablespace_info,
    get_tablespaces_info,
    main,
)


class DummyModule(object):
    def __init__(self):
        self.params = {
            'login_user': 'root',
            'login_password': 'secret',
            'config_file': '~/.my.cnf',
            'client_cert': None,
            'client_key': None,
            'ca_cert': None,
            'check_hostname': None,
            'connect_timeout': 30,
            'name': None,
        }
        self.check_mode = False

    def fail_json(self, msg=None, **kwargs):
        raise RuntimeError(msg)

    def exit_json(self, **kwargs):
        raise SystemExit(kwargs)


def test_get_tablespaces_info_uses_mysql_8_metadata_family(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            'FILE_ID': '17',
            'TABLESPACE_NAME': 'app_data',
            'FILE_NAME': './app_data.ibd',
            'FILE_TYPE': 'TABLESPACE',
            'ENGINE': 'InnoDB',
            'EXTENT_SIZE': '1048576',
            'AUTOEXTEND_SIZE': '8388608',
            'MAXIMUM_SIZE': '67108864',
            'STATUS': 'NORMAL',
            'EXTRA': 'General tablespace',
            'FS_BLOCK_SIZE': '4096',
            'FILE_SIZE': '16777216',
            'ALLOCATED_SIZE': '8388608',
            'PAGE_SIZE': '16384',
            'ZIP_PAGE_SIZE': '0',
            'SPACE_TYPE': 'General',
            'ENCRYPTION': 'N',
            'STATE': 'active',
            'ATTACHED_TABLES': 'app/order_items,app/orders',
        }
    ]
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.get_server_version_tuple',
        lambda _cursor: (8, 0, 36),
    )

    assert get_tablespaces_info(cursor) == {
        'tablespaces': [
            {
                'name': 'app_data',
                'space_id': 17,
                'extent_size': 1048576,
                'autoextend_size': 8388608,
                'maximum_size': 67108864,
                'datafile': './app_data.ibd',
                'filesystem_block_size': 4096,
                'status': 'NORMAL',
                'page_size': 16384,
                'file_size': 16777216,
                'allocated_size': 8388608,
                'zip_page_size': 0,
                'state': 'active',
                'encryption': 'N',
                'attached_tables': ['app/order_items', 'app/orders'],
            }
        ]
    }

    executed_query = cursor.execute.call_args[0][0]
    assert 'INFORMATION_SCHEMA.INNODB_TABLESPACES AS ts' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_DATAFILES AS df' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_TABLES AS t' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_TABLESPACES' not in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_DATAFILES' not in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_TABLES' not in executed_query
    assert "f.FILE_TYPE = 'TABLESPACE'" in executed_query
    assert "ts.SPACE_TYPE = 'General'" in executed_query
    assert 'GROUP_CONCAT' in executed_query
    assert 'ORDER BY f.TABLESPACE_NAME' in executed_query


def test_get_tablespaces_info_uses_mysql_57_metadata_family(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            'FILE_ID': '11',
            'TABLESPACE_NAME': 'archive_data',
            'FILE_NAME': './archive_data.ibd',
            'FILE_TYPE': 'TABLESPACE',
            'ENGINE': 'InnoDB',
            'EXTENT_SIZE': '1048576',
            'AUTOEXTEND_SIZE': '8388608',
            'MAXIMUM_SIZE': None,
            'STATUS': 'NORMAL',
            'EXTRA': 'General tablespace',
            'FS_BLOCK_SIZE': '4096',
            'FILE_SIZE': '16777216',
            'ALLOCATED_SIZE': '8388608',
            'PAGE_SIZE': '16384',
            'ZIP_PAGE_SIZE': '0',
            'SPACE_TYPE': 'General',
            'ENCRYPTION': None,
            'STATE': None,
            'ATTACHED_TABLES': 'archive/orders',
        }
    ]
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.get_server_version_tuple',
        lambda _cursor: (5, 7, 42),
    )

    assert get_tablespaces_info(cursor) == {
        'tablespaces': [
            {
                'name': 'archive_data',
                'space_id': 11,
                'extent_size': 1048576,
                'autoextend_size': 8388608,
                'datafile': './archive_data.ibd',
                'filesystem_block_size': 4096,
                'status': 'NORMAL',
                'page_size': 16384,
                'file_size': 16777216,
                'allocated_size': 8388608,
                'zip_page_size': 0,
                'attached_tables': ['archive/orders'],
            }
        ]
    }

    executed_query = cursor.execute.call_args[0][0]
    assert 'INFORMATION_SCHEMA.INNODB_SYS_TABLESPACES AS ts' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_DATAFILES AS df' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_SYS_TABLES AS t' in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_TABLESPACES' not in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_DATAFILES' not in executed_query
    assert 'INFORMATION_SCHEMA.INNODB_TABLES AS t' not in executed_query
    assert "f.FILE_TYPE = 'TABLESPACE'" in executed_query
    assert 'ts.FS_BLOCK_SIZE' in executed_query
    assert 'ts.FILE_SIZE' in executed_query
    assert 'ts.ALLOCATED_SIZE' in executed_query


def test_get_tablespaces_info_filters_mysql_by_name(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.get_server_version_tuple',
        lambda _cursor: (8, 0, 36),
    )

    assert get_tablespaces_info(cursor, name='app_data') == {'tablespaces': []}

    executed_query, params = cursor.execute.call_args[0]
    assert 'f.TABLESPACE_NAME = %s' in executed_query
    assert params == ('app_data',)


def test_get_tablespaces_info_filters_mysql_by_explicit_empty_name(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.get_server_version_tuple',
        lambda _cursor: (8, 0, 36),
    )

    assert get_tablespaces_info(cursor, name='') == {'tablespaces': []}

    executed_query, params = cursor.execute.call_args[0]
    assert 'f.TABLESPACE_NAME = %s' in executed_query
    assert params == ('',)


def test_get_tablespaces_info_uses_provided_mysql_version(monkeypatch):
    cursor = MagicMock()

    def fail_get_server_version(_cursor):
        raise AssertionError('server version should not be re-read')

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.get_server_version_tuple',
        fail_get_server_version,
    )

    def fake_get_mysql_tablespaces(actual_cursor, server_version, name=None, module=None):
        assert actual_cursor is cursor
        assert server_version == (8, 0, 36)
        assert name == 'app_data'
        assert module is None
        return [{
            'name': 'app_data',
            'space_id': 17,
            'datafile': './app_data.ibd',
            'page_size': 16384,
            'attached_tables': [],
        }]

    monkeypatch.setattr(mysql_tablespace_info, 'get_mysql_tablespaces', fake_get_mysql_tablespaces)

    assert get_tablespaces_info(
        cursor,
        name='app_data',
        server_version=(8, 0, 36),
    ) == {'tablespaces': [{
        'name': 'app_data',
        'space_id': 17,
        'datafile': './app_data.ibd',
        'page_size': 16384,
        'attached_tables': [],
    }]}


def test_format_tablespace_info_keeps_only_informative_fields():
    assert format_tablespace_info({
        'server_implementation': 'mysql',
        'name': 'app_data',
        'space_id': 17,
        'engine': 'InnoDB',
        'file_type': 'TABLESPACE',
        'datafile': './app_data.ibd',
        'page_size': 16384,
        'file_size': 16777216,
        'allocated_size': 8388608,
        'attached_tables': ['app/orders'],
        'status': None,
        'comment': 'General tablespace',
        'space_type': 'General',
    }) == {
        'name': 'app_data',
        'space_id': 17,
        'datafile': './app_data.ibd',
        'page_size': 16384,
        'file_size': 16777216,
        'allocated_size': 8388608,
        'attached_tables': ['app/orders'],
    }


def test_main_returns_changed_false_and_passes_name_filter(monkeypatch):
    module = DummyModule()
    module.params['name'] = 'app_data'
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )

    def fake_ensure_tablespaces_supported(actual_module, actual_cursor):
        assert actual_module is module
        assert actual_cursor is cursor
        return (8, 0, 36)

    monkeypatch.setattr(mysql_tablespace_info, 'ensure_tablespaces_supported', fake_ensure_tablespaces_supported, raising=False)

    def fake_get_tablespaces_info(actual_cursor, name=None, server_version=None, module=None):
        assert actual_cursor is cursor
        assert name == 'app_data'
        assert server_version == (8, 0, 36)
        assert module is not None
        return {'tablespaces': [{'name': 'app_data'}]}

    monkeypatch.setattr(mysql_tablespace_info, 'get_tablespaces_info', fake_get_tablespaces_info)

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result == {
        'changed': False,
        'tablespaces': [{'name': 'app_data'}],
    }


def test_main_fails_fast_for_non_mysql(monkeypatch):
    module = DummyModule()
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )

    def fail_ensure_tablespaces_supported(actual_module, actual_cursor):
        assert actual_module is module
        assert actual_cursor is cursor
        raise RuntimeError('Tablespace operations are supported only by MySQL.')

    monkeypatch.setattr(mysql_tablespace_info, 'ensure_tablespaces_supported', fail_ensure_tablespaces_supported, raising=False)

    def unexpected_get_tablespaces_info(*args, **kwargs):
        raise AssertionError('get_tablespaces_info should not be called')

    monkeypatch.setattr(mysql_tablespace_info, 'get_tablespaces_info', unexpected_get_tablespaces_info)

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'Tablespace operations are supported only by MySQL.'


def test_main_fails_fast_for_unsupported_old_mysql(monkeypatch):
    module = DummyModule()
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )

    def fail_ensure_tablespaces_supported(actual_module, actual_cursor):
        assert actual_module is module
        assert actual_cursor is cursor
        raise RuntimeError('Tablespace operations require MySQL 5.7.6 or later.')

    monkeypatch.setattr(mysql_tablespace_info, 'ensure_tablespaces_supported', fail_ensure_tablespaces_supported, raising=False)

    def unexpected_get_tablespaces_info(*args, **kwargs):
        raise AssertionError('get_tablespaces_info should not be called')

    monkeypatch.setattr(mysql_tablespace_info, 'get_tablespaces_info', unexpected_get_tablespaces_info)

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'Tablespace operations require MySQL 5.7.6 or later.'


def test_main_fails_cleanly_when_tablespace_query_fails(monkeypatch):
    module = DummyModule()
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError('metadata denied')

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace_info.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )

    monkeypatch.setattr(
        mysql_tablespace_info,
        'ensure_tablespaces_supported',
        lambda actual_module, actual_cursor: (8, 0, 36),
        raising=False,
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert "Cannot execute SQL '" in str(exc.value)
    assert 'metadata denied' in str(exc.value)
