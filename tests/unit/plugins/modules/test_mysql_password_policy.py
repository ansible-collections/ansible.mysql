# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from contextlib import contextmanager
import json
import sys

import pytest

try:
    from unittest.mock import MagicMock
except ImportError:
    from mock import MagicMock  # pyright: ignore[reportMissingImports]

from ansible.module_utils import basic
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_bytes
try:
    from ansible.module_utils.testing import patch_module_args  # pyright: ignore[reportMissingImports]
except ImportError:
    patch_module_args = None

from ansible_collections.ansible.mysql.plugins.modules import mysql_password_policy
from ansible_collections.ansible.mysql.plugins.modules.mysql_password_policy import (
    MySQLPasswordPolicy,
    get_variable,
    normalize_bool_setting_value,
    normalize_int_value,
    normalize_policy_value,
    set_variable,
)


class AnsibleExitJson(Exception):
    pass


class AnsibleFailJson(Exception):
    pass


def exit_json(*args, **kwargs):
    raise AnsibleExitJson(kwargs)


def fail_json(*args, **kwargs):
    kwargs['failed'] = True
    raise AnsibleFailJson(kwargs)


@contextmanager
def set_module_args(args):
    module_args = dict(args)

    original_argv = sys.argv[:]
    sys.argv = ['ansible_unittest']

    try:
        if patch_module_args is not None:
            with patch_module_args(module_args):
                yield
            return

        original_args = getattr(basic, '_ANSIBLE_ARGS', None)
        original_profile = getattr(basic, '_ANSIBLE_PROFILE', None)
        had_profile = hasattr(basic, '_ANSIBLE_PROFILE')

        basic._ANSIBLE_ARGS = to_bytes(json.dumps({'ANSIBLE_MODULE_ARGS': module_args}))
        basic._ANSIBLE_PROFILE = 'legacy'

        try:
            yield
        finally:
            basic._ANSIBLE_ARGS = original_args
            if had_profile:
                basic._ANSIBLE_PROFILE = original_profile
            else:
                delattr(basic, '_ANSIBLE_PROFILE')
    finally:
        sys.argv = original_argv


class FakeCursor(object):
    def __init__(self, variables):
        self.variables = variables.copy()
        self.executed = []
        self._rows = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

        if query == "SHOW GLOBAL VARIABLES WHERE Variable_name = %s":
            variable_name = params[0]
            if variable_name in self.variables:
                self._rows = [(variable_name, self.variables[variable_name])]
            else:
                self._rows = []
            return

        if query.startswith("SET GLOBAL ") or query.startswith("SET PERSIST "):
            variable_name = query.split('`')[1]
            self.variables[variable_name] = params[0]
            self._rows = []
            return

        raise AssertionError('Unexpected query: %s' % query)

    def fetchall(self):
        return list(self._rows)


class ModuleStub(object):
    def fail_json(self, **kwargs):
        raise RuntimeError(kwargs['msg'])


@pytest.mark.parametrize(
    'value,expected',
    [
        ('12', 12),
        (12, 12),
    ],
)
def test_normalize_int_value_returns_expected_int(value, expected):
    assert normalize_int_value(value) == expected


@pytest.mark.parametrize(
    'value,expected',
    [
        ('ON', 'ON'),
        ('off', 'OFF'),
        (1, 'ON'),
        (False, 'OFF'),
    ],
)
def test_normalize_bool_setting_value_normalizes_supported_inputs(value, expected):
    assert normalize_bool_setting_value(value) == expected


@pytest.mark.parametrize(
    'value,expected',
    [
        ('medium', 'medium'),
        ('MEDIUM', 'medium'),
        ('1', 'medium'),
        ('2', 'strong'),
    ],
)
def test_normalize_policy_value_normalizes_numeric_and_string_inputs(value, expected):
    assert normalize_policy_value(value) == expected


def test_get_variable_returns_matching_value():
    cursor = FakeCursor({
        'password_history': '3',
    })

    assert get_variable(cursor, 'password_history') == '3'


def test_get_variable_returns_none_when_variable_is_missing():
    assert get_variable(FakeCursor({}), 'password_history') is None


def test_set_variable_executes_global_query():
    cursor = FakeCursor({})

    set_variable(cursor, 'password_history', 4, 'global')

    assert cursor.executed[-1] == ("SET GLOBAL `password_history` = %s", (4,))
    assert cursor.variables['password_history'] == 4


def test_set_variable_executes_persist_query():
    cursor = FakeCursor({})

    set_variable(cursor, 'password_history', 4, 'persist')

    assert cursor.executed[-1] == ("SET PERSIST `password_history` = %s", (4,))
    assert cursor.variables['password_history'] == 4


def test_configure_returns_unchanged_when_mysql_settings_already_match():
    cursor = FakeCursor({
        'validate_password.length': '12',
        'validate_password.mixed_case_count': '2',
        'validate_password.number_count': '2',
        'validate_password.special_char_count': '1',
        'default_password_lifetime': '90',
    })

    policy = MySQLPasswordPolicy(ModuleStub(), cursor, 'mysql')

    result = policy.configure({
        'length': 12,
        'mixed_case_count': 2,
        'number_count': 2,
        'special_char_count': 1,
        'password_lifetime': 90,
    })

    assert result['changed'] is False
    assert result['queries'] == []
    assert result['settings'] == {
        'length': 12,
        'mixed_case_count': 2,
        'number_count': 2,
        'special_char_count': 1,
        'password_lifetime': 90,
    }


def test_configure_in_check_mode_predicts_mysql_persist_queries_without_writes():
    cursor = FakeCursor({
        'validate_password.length': '8',
        'password_history': '3',
    })

    policy = MySQLPasswordPolicy(ModuleStub(), cursor, 'mysql')

    result = policy.configure({
        'length': 12,
        'password_history': 5,
    }, mode='persist', check_mode=True)

    assert result['changed'] is True
    assert result['queries'] == [
        "SET PERSIST `validate_password`.`length` = 12",
        "SET PERSIST `password_history` = 5",
    ]
    assert cursor.variables['validate_password.length'] == '8'
    assert cursor.variables['password_history'] == '3'
    assert not any(query.startswith('SET PERSIST ') for query, _params in cursor.executed)


def test_configure_uses_mariadb_simple_password_check_mapping():
    cursor = FakeCursor({
        'simple_password_check_minimal_length': '12',
        'simple_password_check_letters_same_case': '2',
        'simple_password_check_digits': '2',
        'simple_password_check_other_characters': '1',
    })

    policy = MySQLPasswordPolicy(ModuleStub(), cursor, 'mariadb')

    result = policy.configure({
        'length': 12,
        'mixed_case_count': 2,
        'number_count': 2,
        'special_char_count': 1,
    })

    assert result['changed'] is False
    assert result['settings'] == {
        'length': 12,
        'mixed_case_count': 2,
        'number_count': 2,
        'special_char_count': 1,
    }


def test_configure_fails_when_mariadb_receives_mysql_only_option():
    policy = MySQLPasswordPolicy(ModuleStub(), FakeCursor({}), 'mariadb')

    with pytest.raises(RuntimeError) as exc_info:
        policy.configure({'policy': 'medium'})

    assert str(exc_info.value) == 'Parameter "policy" is supported only on MySQL.'


def test_validate_supported_settings_allows_mysql_specific_options():
    policy = MySQLPasswordPolicy(ModuleStub(), FakeCursor({}), 'mysql')

    policy.validate_supported_settings({'policy': 'medium'}, mode='persist')


def test_configure_fails_when_requested_validation_facility_is_missing():
    policy = MySQLPasswordPolicy(ModuleStub(), FakeCursor({}), 'mysql')

    with pytest.raises(RuntimeError) as exc_info:
        policy.configure({'length': 12})

    assert str(exc_info.value) == 'Password policy setting "length" is not available on this server.'


def test_configure_allows_mysql_global_settings_without_validate_password_component():
    cursor = FakeCursor({
        'password_history': '3',
    })

    policy = MySQLPasswordPolicy(ModuleStub(), cursor, 'mysql')

    result = policy.configure({
        'password_history': 5,
    })

    assert result['changed'] is True
    assert result['queries'] == [
        "SET GLOBAL `password_history` = 5",
    ]
    assert cursor.variables['password_history'] == 5


def test_configure_fails_when_mariadb_requests_persist_mode():
    cursor = FakeCursor({
        'simple_password_check_minimal_length': '8',
    })

    policy = MySQLPasswordPolicy(ModuleStub(), cursor, 'mariadb')

    with pytest.raises(RuntimeError) as exc_info:
        policy.configure({'length': 12}, mode='persist')

    assert str(exc_info.value) == 'mode=persist is supported only on MySQL.'


def test_read_setting_returns_mapped_mysql_variable_name_and_value():
    policy = MySQLPasswordPolicy(
        ModuleStub(),
        FakeCursor({'validate_password.policy': 'MEDIUM'}),
        'mysql',
    )

    variable_name, value = policy.read_setting('policy')

    assert variable_name == 'validate_password.policy'
    assert value == 'MEDIUM'


def test_normalize_value_handles_supported_setting_types():
    policy = MySQLPasswordPolicy(ModuleStub(), FakeCursor({}), 'mysql')

    assert policy.normalize_value('policy', '1') == 'medium'
    assert policy.normalize_value('check_user_name', 'off') == 'OFF'
    assert policy.normalize_value('length', '12') == 12


def test_query_value_formats_policy_and_bool_for_sql():
    policy = MySQLPasswordPolicy(ModuleStub(), FakeCursor({}), 'mysql')

    assert policy.query_value('policy', 'medium') == 'MEDIUM'
    assert policy.query_value('check_user_name', False) == 'OFF'


def test_format_set_query_formats_expected_statement():
    assert MySQLPasswordPolicy.format_set_query('password_history', 5, 'persist') == (
        "SET PERSIST `password_history` = 5"
    )


def test_format_set_query_quotes_dotted_variable_fragments():
    assert MySQLPasswordPolicy.format_set_query('validate_password.length', 12, 'global') == (
        "SET GLOBAL `validate_password`.`length` = 12"
    )


def test_configure_treats_policy_values_case_insensitively():
    cursor = FakeCursor({
        'validate_password.policy': 'MEDIUM',
    })

    policy = MySQLPasswordPolicy(ModuleStub(), cursor, 'mysql')

    result = policy.configure({
        'policy': 'medium',
    })

    assert result['changed'] is False
    assert result['queries'] == []


def test_main_rejects_persist_mode_for_old_mysql(monkeypatch):
    with set_module_args(
        {
            'login_unix_socket': '/run/mysqld/mysqld.sock',
            'length': 12,
            'mode': 'persist',
        }
    ):
        monkeypatch.setattr(AnsibleModule, 'exit_json', exit_json)
        monkeypatch.setattr(AnsibleModule, 'fail_json', fail_json)
        monkeypatch.setattr(mysql_password_policy, 'mysql_driver', object())
        monkeypatch.setattr(mysql_password_policy, 'mysql_connect', lambda *args, **kwargs: (MagicMock(), MagicMock()))
        monkeypatch.setattr(mysql_password_policy, 'get_server_implementation', lambda cursor: 'mysql')
        monkeypatch.setattr(mysql_password_policy, 'get_server_version', lambda cursor: '5.7.44')

        with pytest.raises(AnsibleFailJson) as exc:
            mysql_password_policy.main()

    assert exc.value.args[0]['msg'] == 'mode=persist requires MySQL 8.0 or later.'


def test_main_returns_configure_result(monkeypatch):
    with set_module_args(
        {
            'login_unix_socket': '/run/mysqld/mysqld.sock',
            'length': 12,
        }
    ):
        monkeypatch.setattr(AnsibleModule, 'exit_json', exit_json)
        monkeypatch.setattr(AnsibleModule, 'fail_json', fail_json)
        monkeypatch.setattr(mysql_password_policy, 'mysql_driver', object())
        monkeypatch.setattr(mysql_password_policy, 'mysql_connect', lambda *args, **kwargs: (MagicMock(), MagicMock()))
        monkeypatch.setattr(mysql_password_policy, 'get_server_implementation', lambda cursor: 'mariadb')

        def fake_configure(self, desired_settings, mode='global', check_mode=False):
            assert desired_settings['length'] == 12
            assert mode == 'global'
            assert check_mode is False
            return {
                'changed': False,
                'queries': [],
                'settings': {'length': 12},
            }

        monkeypatch.setattr(mysql_password_policy.MySQLPasswordPolicy, 'configure', fake_configure)

        with pytest.raises(AnsibleExitJson) as exc:
            mysql_password_policy.main()

    assert exc.value.args[0] == {
        'changed': False,
        'queries': [],
        'settings': {'length': 12},
    }
