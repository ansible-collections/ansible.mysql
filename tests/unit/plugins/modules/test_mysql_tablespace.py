# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock

from ansible_collections.ansible.mysql.plugins.modules import mysql_tablespace
from ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace import (
    build_alter_queries,
    build_create_query,
    build_drop_query,
    execute_query,
    fail_if_create_only_options_differ,
    fail_if_rename_target_requires_changes,
    get_tablespace_file_block_size,
    main,
    normalize_tablespace_encryption,
    predict_tablespace,
    quote_sql_value,
    resolve_current_tablespace,
    validate_autoextend_size_input,
    validate_file_block_size_input,
    validate_tablespace_autoextend_size,
    validate_tablespace_datafile,
    validate_tablespace_encryption,
    validate_tablespace_rename,
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
            'connect_timeout': 30,
            'check_hostname': None,
            'name': 'app_data',
            'state': 'present',
            'datafile': './app_data.ibd',
            'file_block_size': None,
            'encryption': 'Y',
            'rename_to': None,
            'autoextend_size': 8388608,
        }
        self.check_mode = False

    def fail_json(self, msg=None, **kwargs):
        raise RuntimeError(msg)

    def exit_json(self, **kwargs):
        raise SystemExit(kwargs)


def assert_mysql_connect_not_called(*args, **kwargs):
    raise AssertionError('mysql_connect should not be called')


def make_tablespace(name='app_data', **overrides):
    current = {
        'server_implementation': 'mysql',
        'name': name,
        'datafile': './app_data.ibd',
        'autoextend_size': 8388608,
        'encryption': 'N',
        'page_size': 16384,
        'zip_page_size': 0,
    }
    current.update(overrides)
    return current


@pytest.mark.parametrize(
    'encryption,expected',
    [
        (None, None),
        ('y', 'Y'),
        ('N', 'N'),
    ]
)
def test_normalize_tablespace_encryption_accepts_none_and_uppercases_values(encryption, expected):
    assert normalize_tablespace_encryption(encryption) == expected


def test_normalize_tablespace_encryption_rejects_invalid_values():
    with pytest.raises(ValueError, match="encryption must be either 'Y' or 'N'"):
        normalize_tablespace_encryption('maybe')


@pytest.mark.parametrize(
    'autoextend_size,expected',
    [
        (None, None),
        (4194304, 4194304),
        (8388608, 8388608),
    ]
)
def test_validate_autoextend_size_input_accepts_none_and_valid_multiples(autoextend_size, expected):
    assert validate_autoextend_size_input(autoextend_size) == expected


@pytest.mark.parametrize('autoextend_size', [-4194304, 1])
def test_validate_autoextend_size_input_rejects_invalid_values(autoextend_size):
    with pytest.raises(ValueError, match='autoextend_size must be a non-negative multiple of 4MB'):
        validate_autoextend_size_input(autoextend_size)


@pytest.mark.parametrize(
    'file_block_size,expected',
    [
        (None, None),
        (8192, 8192),
    ]
)
def test_validate_file_block_size_input_accepts_positive_values(file_block_size, expected):
    assert validate_file_block_size_input(file_block_size) == expected


@pytest.mark.parametrize(
    'current,expected',
    [
        ({'page_size': 16384, 'zip_page_size': 0}, 16384),
        ({'page_size': 16384, 'zip_page_size': 8192}, 8192),
        ({'page_size': None, 'zip_page_size': None}, None),
    ]
)
def test_get_tablespace_file_block_size_prefers_zip_page_size(current, expected):
    assert get_tablespace_file_block_size(current) == expected


@pytest.mark.parametrize(
    'validator',
    [
        validate_tablespace_rename,
        validate_tablespace_encryption,
        validate_tablespace_autoextend_size,
    ]
)
def test_version_gated_validators_allow_absent_values(validator):
    assert validator((5, 7, 6), None) is None


def test_validate_tablespace_rename_requires_mysql_8_0_3():
    assert validate_tablespace_rename((8, 0, 3), 'archive_data') == 'archive_data'

    with pytest.raises(ValueError) as exc:
        validate_tablespace_rename((8, 0, 2), 'archive_data')

    assert str(exc.value) == 'rename requires MySQL 8.0.3 or later'


def test_validate_tablespace_encryption_requires_mysql_8_0_13():
    assert validate_tablespace_encryption((8, 0, 13), 'Y') == 'Y'

    with pytest.raises(ValueError) as exc:
        validate_tablespace_encryption((8, 0, 12), 'Y')

    assert str(exc.value) == 'encryption requires MySQL 8.0.13 or later'


def test_validate_tablespace_autoextend_size_requires_mysql_8_0_23():
    assert validate_tablespace_autoextend_size((8, 0, 23), 8388608) == 8388608

    with pytest.raises(ValueError) as exc:
        validate_tablespace_autoextend_size((8, 0, 22), 8388608)

    assert str(exc.value) == 'autoextend_size requires MySQL 8.0.23 or later'


def test_validate_tablespace_datafile_requires_explicit_datafile_before_mysql_8_0_14():
    assert validate_tablespace_datafile((8, 0, 13), './app_data.ibd') == './app_data.ibd'
    assert validate_tablespace_datafile((8, 0, 14), None) is None

    with pytest.raises(ValueError) as exc:
        validate_tablespace_datafile((8, 0, 13), None)

    assert str(exc.value) == 'datafile is required for MySQL versions earlier than 8.0.14'


def test_build_create_query_includes_supported_create_options():
    assert build_create_query(
        'app_data',
        datafile='./app_data.ibd',
        file_block_size=8192,
        encryption='Y',
        autoextend_size=8388608,
    ) == (
        "CREATE TABLESPACE `app_data` ADD DATAFILE './app_data.ibd' "
        "AUTOEXTEND_SIZE = 8388608 FILE_BLOCK_SIZE = 8192 ENCRYPTION = 'Y' ENGINE = InnoDB"
    )


def test_build_alter_queries_split_mutable_changes_into_valid_statements():
    assert build_alter_queries(
        'app_data',
        make_tablespace(),
        rename_to='archive_data',
        encryption='Y',
        autoextend_size=16777216,
    ) == [
        "ALTER TABLESPACE `app_data` RENAME TO `archive_data`",
        "ALTER TABLESPACE `archive_data` AUTOEXTEND_SIZE = 16777216",
        "ALTER TABLESPACE `archive_data` ENCRYPTION = 'Y'",
    ]


def test_build_drop_query_returns_expected_sql():
    assert build_drop_query('app_data') == "DROP TABLESPACE `app_data`"


def test_quote_sql_value_handles_booleans_integers_and_escaping():
    assert quote_sql_value(True) == '1'
    assert quote_sql_value(False) == '0'
    assert quote_sql_value(17) == '17'
    assert quote_sql_value("O'Reilly") == "'O''Reilly'"


def test_execute_query_executes_statement_without_fetching():
    cursor = MagicMock()

    execute_query(cursor, 'DROP TABLESPACE `app_data`')

    cursor.execute.assert_called_once_with('DROP TABLESPACE `app_data`')
    cursor.fetchall.assert_not_called()


def test_predict_tablespace_builds_predicted_state_for_create():
    assert predict_tablespace(
        name='app_data',
        datafile='./app_data.ibd',
        encryption='Y',
        autoextend_size=8388608,
    ) == {
        'server_implementation': 'mysql',
        'name': 'app_data',
        'datafile': './app_data.ibd',
        'encryption': 'Y',
        'autoextend_size': 8388608,
    }


def test_predict_tablespace_overlays_requested_changes_on_existing_state():
    assert predict_tablespace(
        current=make_tablespace(),
        rename_to='archive_data',
        encryption='Y',
        autoextend_size=16777216,
    ) == make_tablespace(
        name='archive_data',
        encryption='Y',
        autoextend_size=16777216,
    )


def test_resolve_current_tablespace_returns_current_when_no_rename_is_requested(monkeypatch):
    current = make_tablespace()
    lookups = []

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        lookups.append(name)
        return current

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)

    resolved, rename_already_applied = resolve_current_tablespace(
        MagicMock(),
        MagicMock(),
        (8, 0, 36),
        'app_data',
    )

    assert resolved == current
    assert rename_already_applied is False
    assert lookups == ['app_data']


def test_resolve_current_tablespace_fails_when_rename_target_already_exists(monkeypatch):
    module = MagicMock()
    module.fail_json.side_effect = RuntimeError('fail_json called')
    current = make_tablespace()
    renamed = make_tablespace(name='archive_data')

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        if name == 'app_data':
            return current
        if name == 'archive_data':
            return renamed
        raise AssertionError('Unexpected tablespace lookup: %s' % name)

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)

    with pytest.raises(RuntimeError, match='fail_json called'):
        resolve_current_tablespace(
            module,
            MagicMock(),
            (8, 0, 36),
            'app_data',
            rename_to='archive_data',
        )

    module.fail_json.assert_called_once_with(
        msg='Cannot rename tablespace app_data to archive_data because archive_data already exists.'
    )


def test_fail_if_rename_target_requires_changes_fails_when_file_block_size_metadata_is_missing():
    module = MagicMock()
    module.fail_json.side_effect = RuntimeError('fail_json called')

    with pytest.raises(RuntimeError, match='fail_json called'):
        fail_if_rename_target_requires_changes(
            module,
            make_tablespace(name='archive_data', page_size=None, zip_page_size=None),
            'archive_data',
            file_block_size=8192,
        )

    assert 'file_block_size' in module.fail_json.call_args[1]['msg']


def test_fail_if_rename_target_requires_changes_accepts_matching_end_state():
    fail_if_rename_target_requires_changes(
        MagicMock(),
        make_tablespace(name='archive_data', autoextend_size=8388608, encryption='N'),
        'archive_data',
        encryption='N',
        autoextend_size=8388608,
    )


def test_fail_if_create_only_options_differ_fails_when_file_block_size_metadata_is_missing():
    module = MagicMock()
    module.fail_json.side_effect = RuntimeError('fail_json called')

    with pytest.raises(RuntimeError, match='fail_json called'):
        fail_if_create_only_options_differ(
            module,
            make_tablespace(page_size=None, zip_page_size=None),
            file_block_size=8192,
        )

    assert 'Cannot compare create-only file_block_size' in module.fail_json.call_args[1]['msg']


def test_fail_if_create_only_options_differ_accepts_matching_state():
    fail_if_create_only_options_differ(
        MagicMock(),
        make_tablespace(),
        datafile='./app_data.ibd',
        file_block_size=16384,
    )


def test_build_alter_queries_return_empty_list_when_requested_state_matches_current():
    assert build_alter_queries(
        'app_data',
        make_tablespace(),
        rename_to='app_data',
        encryption='N',
        autoextend_size=8388608,
    ) == []


def test_main_creates_tablespace_in_check_mode_with_predicted_result(monkeypatch):
    module = DummyModule()
    module.check_mode = True
    cursor = MagicMock()
    connection = MagicMock()
    connect_kwargs = {}

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )

    def fake_mysql_connect(*args, **kwargs):
        connect_kwargs.update(kwargs)
        return cursor, connection

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        fake_mysql_connect,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'get_mysql_tablespace',
        lambda _cursor, _server_version, _name, module=None: None,
    )

    with pytest.raises(SystemExit) as exc:
        main()

    result = exc.value.args[0]
    assert result == {
        'changed': True,
        'queries': [
            "CREATE TABLESPACE `app_data` ADD DATAFILE './app_data.ibd' "
            "AUTOEXTEND_SIZE = 8388608 ENCRYPTION = 'Y' ENGINE = InnoDB"
        ],
        'tablespace': {
            'server_implementation': 'mysql',
            'name': 'app_data',
            'datafile': './app_data.ibd',
            'autoextend_size': 8388608,
            'encryption': 'Y',
        },
    }
    assert connect_kwargs['cursor_class'] == 'DictCursor'
    assert connect_kwargs['autocommit'] is True


def test_main_fails_when_rename_to_is_used_with_absent_state(monkeypatch):
    module = DummyModule()
    module.params['state'] = 'absent'
    module.params['rename_to'] = 'archive_data'

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'mysql_connect',
        assert_mysql_connect_not_called,
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'rename_to cannot be used with state=absent'


def test_main_fails_when_mysql_driver_is_missing(monkeypatch):
    module = DummyModule()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        None,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver_fail_msg',
        'mysql driver missing',
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'mysql driver missing'


def test_main_fails_when_database_connection_fails(monkeypatch):
    module = DummyModule()

    def raise_connection_error(*args, **kwargs):
        raise RuntimeError('network timeout')

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        raise_connection_error,
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'unable to connect to database: network timeout'


def test_main_fails_fast_for_unsupported_server(monkeypatch):
    module = DummyModule()
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.module_utils.tablespace.get_server_implementation',
        lambda _module, _cursor: 'unsupported',
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'Tablespace operations are supported only by MySQL.'


def test_main_drops_tablespace_in_check_mode(monkeypatch):
    module = DummyModule()
    module.check_mode = True
    module.params['state'] = 'absent'
    module.params['datafile'] = None
    module.params['encryption'] = None
    module.params['autoextend_size'] = None
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'get_mysql_tablespace',
        lambda _cursor, _server_version, _name, module=None: make_tablespace(),
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {
        'changed': True,
        'queries': ["DROP TABLESPACE `app_data`"],
    }


def test_main_returns_unchanged_when_absent_tablespace_is_missing(monkeypatch):
    module = DummyModule()
    module.params['state'] = 'absent'
    module.params['datafile'] = None
    module.params['encryption'] = None
    module.params['autoextend_size'] = None
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'get_mysql_tablespace',
        lambda _cursor, _server_version, _name, module=None: None,
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {'changed': False}


def test_main_alters_tablespace_in_check_mode(monkeypatch):
    module = DummyModule()
    module.check_mode = True
    module.params['datafile'] = None
    module.params['file_block_size'] = None
    module.params['rename_to'] = 'archive_data'
    module.params['encryption'] = 'Y'
    module.params['autoextend_size'] = 16777216
    current = make_tablespace()
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        if name == 'app_data':
            return current
        if name == 'archive_data':
            return None
        raise AssertionError('Unexpected tablespace lookup: %s' % name)

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {
        'changed': True,
        'queries': [
            "ALTER TABLESPACE `app_data` RENAME TO `archive_data`",
            "ALTER TABLESPACE `archive_data` AUTOEXTEND_SIZE = 16777216",
            "ALTER TABLESPACE `archive_data` ENCRYPTION = 'Y'",
        ],
        'tablespace': make_tablespace(
            name='archive_data',
            autoextend_size=16777216,
            encryption='Y',
        ),
    }


def test_main_returns_predicted_tablespace_when_post_create_lookup_is_empty(monkeypatch):
    module = DummyModule()
    cursor = MagicMock()
    lookups = []

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        lookups.append(name)
        return None

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {
        'changed': True,
        'queries': [
            "CREATE TABLESPACE `app_data` ADD DATAFILE './app_data.ibd' "
            "AUTOEXTEND_SIZE = 8388608 ENCRYPTION = 'Y' ENGINE = InnoDB"
        ],
        'tablespace': {
            'server_implementation': 'mysql',
            'name': 'app_data',
            'datafile': './app_data.ibd',
            'autoextend_size': 8388608,
            'encryption': 'Y',
        },
    }
    assert lookups == ['app_data', 'app_data']


def test_main_returns_predicted_tablespace_when_post_alter_lookup_is_empty(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = None
    module.params['file_block_size'] = None
    module.params['rename_to'] = 'archive_data'
    module.params['encryption'] = 'Y'
    module.params['autoextend_size'] = 16777216
    current = make_tablespace()
    cursor = MagicMock()
    executed_queries = []
    archive_data_lookups = []

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        if name == 'app_data':
            return current
        if name == 'archive_data':
            archive_data_lookups.append(name)
            return None
        raise AssertionError('Unexpected tablespace lookup: %s' % name)

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)
    monkeypatch.setattr(
        mysql_tablespace,
        'execute_query',
        lambda _cursor, query: executed_queries.append(query),
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {
        'changed': True,
        'queries': [
            "ALTER TABLESPACE `app_data` RENAME TO `archive_data`",
            "ALTER TABLESPACE `archive_data` AUTOEXTEND_SIZE = 16777216",
            "ALTER TABLESPACE `archive_data` ENCRYPTION = 'Y'",
        ],
        'tablespace': make_tablespace(
            name='archive_data',
            autoextend_size=16777216,
            encryption='Y',
        ),
    }
    assert executed_queries == [
        "ALTER TABLESPACE `app_data` RENAME TO `archive_data`",
        "ALTER TABLESPACE `archive_data` AUTOEXTEND_SIZE = 16777216",
        "ALTER TABLESPACE `archive_data` ENCRYPTION = 'Y'",
    ]
    assert archive_data_lookups == ['archive_data', 'archive_data']


def test_main_treats_rename_to_as_already_applied(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = None
    module.params['file_block_size'] = None
    module.params['rename_to'] = 'archive_data'
    module.params['encryption'] = 'N'
    module.params['autoextend_size'] = 8388608
    renamed = make_tablespace(name='archive_data')
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        if name == 'app_data':
            return None
        if name == 'archive_data':
            return renamed
        raise AssertionError('Unexpected tablespace lookup: %s' % name)

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {
        'changed': False,
        'tablespace': renamed,
    }


def test_main_converges_when_rename_target_only_needs_mutable_changes(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = './app_data.ibd'
    module.params['file_block_size'] = 16384
    module.params['rename_to'] = 'archive_data'
    module.params['encryption'] = 'Y'
    module.params['autoextend_size'] = 16777216
    renamed = make_tablespace(name='archive_data', encryption='N')
    converged = make_tablespace(name='archive_data', encryption='Y', autoextend_size=16777216)
    cursor = MagicMock()
    executed_queries = []

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        if name == 'app_data':
            return None
        if name == 'archive_data':
            if executed_queries:
                return converged
            return renamed
        raise AssertionError('Unexpected tablespace lookup: %s' % name)

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)
    monkeypatch.setattr(
        mysql_tablespace,
        'execute_query',
        lambda _cursor, query: executed_queries.append(query),
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.args[0] == {
        'changed': True,
        'queries': [
            "ALTER TABLESPACE `archive_data` AUTOEXTEND_SIZE = 16777216",
            "ALTER TABLESPACE `archive_data` ENCRYPTION = 'Y'",
        ],
        'tablespace': converged,
    }
    assert executed_queries == [
        "ALTER TABLESPACE `archive_data` AUTOEXTEND_SIZE = 16777216",
        "ALTER TABLESPACE `archive_data` ENCRYPTION = 'Y'",
    ]


def test_main_fails_when_existing_rename_target_has_create_only_mismatch(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = './different.ibd'
    module.params['file_block_size'] = None
    module.params['rename_to'] = 'archive_data'
    module.params['encryption'] = 'N'
    module.params['autoextend_size'] = 8388608
    renamed = make_tablespace(name='archive_data', datafile='./app_data.ibd')
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )

    def fake_get_mysql_tablespace(_cursor, _server_version, name, module=None):
        if name == 'app_data':
            return None
        if name == 'archive_data':
            return renamed
        raise AssertionError('Unexpected tablespace lookup: %s' % name)

    monkeypatch.setattr(mysql_tablespace, 'get_mysql_tablespace', fake_get_mysql_tablespace)

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == (
        'rename_to target archive_data already exists but does not match the requested end state '
        '(datafile). Refusing to treat the rename as already applied.'
    )


def test_main_fails_when_rename_to_is_requested_without_existing_tablespace(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = None
    module.params['rename_to'] = 'archive_data'
    module.params['encryption'] = None
    module.params['autoextend_size'] = None
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'get_mysql_tablespace',
        lambda _cursor, _server_version, _name, module=None: None,
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == (
        'rename_to is alter-only and requires an existing tablespace named app_data, '
        'or a tablespace already renamed to archive_data.'
    )


def test_main_fails_for_autoextend_size_not_multiple_of_4mb(monkeypatch):
    module = DummyModule()
    module.params['autoextend_size'] = 1

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'mysql_connect',
        assert_mysql_connect_not_called,
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'autoextend_size must be a non-negative multiple of 4MB (4194304 bytes)'


def test_main_fails_when_existing_datafile_differs(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = './different.ibd'
    module.params['file_block_size'] = None
    module.params['encryption'] = None
    module.params['autoextend_size'] = None
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'get_mysql_tablespace',
        lambda _cursor, _server_version, _name, module=None: make_tablespace(),
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == (
        'datafile is create-only and cannot be changed for existing tablespace app_data '
        '(current: ./app_data.ibd, requested: ./different.ibd).'
    )


def test_main_fails_for_non_positive_file_block_size(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = None
    module.params['file_block_size'] = 0
    module.params['encryption'] = None
    module.params['autoextend_size'] = None

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'mysql_connect',
        assert_mysql_connect_not_called,
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == 'file_block_size must be a positive integer'


def test_main_fails_when_existing_file_block_size_differs(monkeypatch):
    module = DummyModule()
    module.params['datafile'] = None
    module.params['file_block_size'] = 8192
    module.params['encryption'] = None
    module.params['autoextend_size'] = None
    cursor = MagicMock()

    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.AnsibleModule',
        lambda **kwargs: module,
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_driver',
        object(),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.mysql_connect',
        lambda *args, **kwargs: (cursor, MagicMock()),
    )
    monkeypatch.setattr(
        'ansible_collections.ansible.mysql.plugins.modules.mysql_tablespace.ensure_tablespaces_supported',
        lambda _module, _cursor: (8, 0, 36),
    )
    monkeypatch.setattr(
        mysql_tablespace,
        'get_mysql_tablespace',
        lambda _cursor, _server_version, _name, module=None: make_tablespace(),
    )

    with pytest.raises(RuntimeError) as exc:
        main()

    assert str(exc.value) == (
        'file_block_size is create-only and cannot be changed for existing tablespace app_data '
        '(current best-effort value: 16384, requested: 8192).'
    )
