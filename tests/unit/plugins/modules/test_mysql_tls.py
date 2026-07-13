# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import pytest

from ansible_collections.ansible.mysql.plugins.modules import mysql_tls as mysql_tls_module
from ansible_collections.ansible.mysql.plugins.modules.mysql_tls import MySQLTLS


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeCursor:
    """Minimal cursor double that tracks executed queries and fakes SHOW VARIABLES."""

    TLS_VARS = frozenset(('ssl_cert', 'ssl_key', 'ssl_ca',
                          'require_secure_transport', 'tls_version'))

    def __init__(self, variables=None, server_version='8.0.34', write_error=None, reload_error=None):
        self.variables = dict(variables or {})
        self.server_version = server_version
        self.write_error = write_error
        self.reload_error = reload_error
        self.executed = []
        self._rows = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

        upper = query.strip().upper()

        if upper.startswith("SELECT VERSION()"):
            self._rows = [(self.server_version,)]
            return

        if upper.startswith("SHOW") and "VARIABLE_NAME" in upper.upper():
            var_name = params[0]
            if var_name in self.variables:
                self._rows = [(var_name, self.variables[var_name])]
            else:
                self._rows = []
            return

        if upper.startswith("SET GLOBAL ") or upper.startswith("SET PERSIST "):
            if self.write_error is not None:
                raise self.write_error
            # Extract variable name between backticks
            var_name = query.split('`')[1]
            self.variables[var_name] = params[0]
            self._rows = []
            return

        if upper == "ALTER INSTANCE RELOAD TLS":
            if self.reload_error is not None:
                raise self.reload_error
            self._rows = []
            return

        raise AssertionError("Unexpected query: %s (params=%s)" % (query, params))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class ModuleStub:
    def fail_json(self, **kwargs):
        raise RuntimeError(kwargs.get('msg', 'fail_json called'))


class DummyDriverError(Exception):
    pass


def _make_mysql_cursor(overrides=None, server_version='8.0.34', write_error=None, reload_error=None):
    """Return a FakeCursor with reasonable MySQL TLS defaults."""
    defaults = {
        'ssl_cert': '',
        'ssl_key': '',
        'ssl_ca': '',
        'require_secure_transport': 'OFF',
        'tls_version': 'TLSv1.2,TLSv1.3',
    }
    if overrides:
        defaults.update(overrides)
    return FakeCursor(
        defaults,
        server_version=server_version,
        write_error=write_error,
        reload_error=reload_error,
    )


# ---------------------------------------------------------------------------
# MySQL - basic configure behaviour
# ---------------------------------------------------------------------------

def test_configure_returns_unchanged_when_settings_already_match():
    cursor = _make_mysql_cursor({
        'ssl_cert': '/etc/mysql/ssl/server-cert.pem',
        'require_secure_transport': 'ON',
    })

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')

    result = tls.configure({
        'server_cert': '/etc/mysql/ssl/server-cert.pem',
        'require_secure_transport': True,
    })

    assert result['changed'] is False
    assert result['queries'] == []


def test_configure_changes_require_secure_transport():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure({'require_secure_transport': True})

    assert result['changed'] is True
    assert any('require_secure_transport' in q for q in result['queries'])
    assert cursor.variables['require_secure_transport'] == 'ON'


def test_configure_changes_cert_paths():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure({
        'server_cert': '/etc/mysql/ssl/server-cert.pem',
        'server_key': '/etc/mysql/ssl/server-key.pem',
        'server_ca': '/etc/mysql/ssl/ca-cert.pem',
    })

    assert result['changed'] is True
    assert cursor.variables['ssl_cert'] == '/etc/mysql/ssl/server-cert.pem'
    assert cursor.variables['ssl_key'] == '/etc/mysql/ssl/server-key.pem'
    assert cursor.variables['ssl_ca'] == '/etc/mysql/ssl/ca-cert.pem'


def test_configure_changes_tls_version():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure({'tls_version': 'TLSv1.3'})

    assert result['changed'] is True
    assert any(
        q.startswith('SET GLOBAL ') and '`tls_version`' in q and 'TLSv1.3' in q
        for q in result['queries']
    )
    assert cursor.variables['tls_version'] == 'TLSv1.3'


def test_configure_returns_effective_settings():
    cursor = _make_mysql_cursor({
        'ssl_cert': '/etc/mysql/ssl/server-cert.pem',
        'require_secure_transport': 'ON',
        'tls_version': 'TLSv1.3',
    })

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure({})

    assert 'settings' in result
    assert result['settings']['server_cert'] == '/etc/mysql/ssl/server-cert.pem'
    assert result['settings']['require_secure_transport'] == 'ON'
    assert result['settings']['tls_version'] == 'TLSv1.3'
    assert 'ssl_cert' not in result['settings']


def test_configure_fails_when_tls_setting_is_not_available():
    cursor = _make_mysql_cursor({'tls_version': None})

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')

    with pytest.raises(RuntimeError) as exc_info:
        tls.configure({})

    assert 'TLS setting "tls_version" is not available on this server.' == str(exc_info.value)


# ---------------------------------------------------------------------------
# MySQL - version guard
# ---------------------------------------------------------------------------

def test_mysql_fails_for_tls_context_change_before_8_0_16():
    cursor = _make_mysql_cursor(server_version='8.0.15')

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='8.0.15')

    with pytest.raises(RuntimeError) as exc_info:
        tls.configure({'server_cert': '/etc/mysql/ssl/server-cert.pem'})

    assert '8.0.16' in str(exc_info.value)
    assert 'server_cert' in str(exc_info.value)


def test_mysql_fails_for_reload_before_8_0_16():
    cursor = _make_mysql_cursor(server_version='8.0.15')

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='8.0.15')

    with pytest.raises(RuntimeError) as exc_info:
        tls.configure({'require_secure_transport': True}, reload=True)

    assert '8.0.16' in str(exc_info.value)
    assert 'reload' in str(exc_info.value).lower()


def test_mysql_allows_require_secure_transport_before_8_0_16():
    cursor = _make_mysql_cursor(server_version='5.7.35')

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='5.7.35')
    result = tls.configure({'require_secure_transport': True})

    assert result['changed'] is True
    assert cursor.variables['require_secure_transport'] == 'ON'


# ---------------------------------------------------------------------------
# MySQL - check mode
# ---------------------------------------------------------------------------

def test_configure_in_check_mode_predicts_changes_without_writes():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure(
        {'require_secure_transport': True},
        check_mode=True,
    )

    assert result['changed'] is True
    assert any('require_secure_transport' in q for q in result['queries'])
    # The variable must NOT have been written
    assert cursor.variables['require_secure_transport'] == 'OFF'
    assert not any(
        q.strip().upper().startswith('SET ') for q, _p in cursor.executed
    )


# ---------------------------------------------------------------------------
# MySQL - reload
# ---------------------------------------------------------------------------

def test_configure_with_reload_executes_alter_instance_reload_tls():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure(
        {'require_secure_transport': True},
        reload=True,
    )

    assert result['changed'] is True
    assert 'ALTER INSTANCE RELOAD TLS' in result['queries']
    assert any(
        q == 'ALTER INSTANCE RELOAD TLS' for q, _p in cursor.executed
    )


def test_configure_with_reload_in_check_mode_includes_reload_query():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure(
        {'require_secure_transport': True},
        reload=True,
        check_mode=True,
    )

    assert result['changed'] is True
    assert 'ALTER INSTANCE RELOAD TLS' in result['queries']
    assert not any(
        q == 'ALTER INSTANCE RELOAD TLS' for q, _p in cursor.executed
    )


def test_configure_tls_context_change_does_not_reload_by_default():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure({
        'server_cert': '/etc/mysql/ssl/server-cert.pem',
    })

    assert result['changed'] is True
    assert any('`ssl_cert`' in q for q in result['queries'])
    assert 'ALTER INSTANCE RELOAD TLS' not in result['queries']
    assert not any(
        q == 'ALTER INSTANCE RELOAD TLS' for q, _p in cursor.executed
    )


def test_configure_does_not_swallow_non_driver_write_errors():
    cursor = _make_mysql_cursor(write_error=TypeError('bad write parameters'))

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='8.0.34')

    with pytest.raises(TypeError) as exc_info:
        tls.configure({'require_secure_transport': True})

    assert 'bad write parameters' in str(exc_info.value)


def test_configure_does_not_swallow_non_driver_reload_errors():
    cursor = _make_mysql_cursor(reload_error=TypeError('bad reload call'))

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='8.0.34')

    with pytest.raises(TypeError) as exc_info:
        tls.configure({'require_secure_transport': True}, reload=True)

    assert 'bad reload call' in str(exc_info.value)


def test_configure_surfaces_driver_write_errors(monkeypatch):
    cursor = _make_mysql_cursor(write_error=DummyDriverError('db write failure'))

    monkeypatch.setattr(
        mysql_tls_module,
        'mysql_driver',
        type('FakeDriver', (), {'Error': DummyDriverError}),
    )

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='8.0.34')

    with pytest.raises(RuntimeError) as exc_info:
        tls.configure({'require_secure_transport': True})

    assert 'db write failure' in str(exc_info.value)


def test_configure_surfaces_driver_reload_errors(monkeypatch):
    cursor = _make_mysql_cursor(reload_error=DummyDriverError('db reload failure'))

    monkeypatch.setattr(
        mysql_tls_module,
        'mysql_driver',
        type('FakeDriver', (), {'Error': DummyDriverError}),
    )

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql', server_version='8.0.34')

    with pytest.raises(RuntimeError) as exc_info:
        tls.configure({'require_secure_transport': True}, reload=True)

    assert "ALTER INSTANCE RELOAD TLS" in str(exc_info.value)
    assert 'db reload failure' in str(exc_info.value)


# ---------------------------------------------------------------------------
# MySQL - persist mode
# ---------------------------------------------------------------------------

def test_configure_with_global_mode_uses_set_global():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure(
        {'require_secure_transport': True},
        mode='global',
    )

    assert result['changed'] is True
    assert any(
        q.startswith('SET GLOBAL ') and '`require_secure_transport`' in q
        for q in result['queries']
    )
    assert not any('SET PERSIST' in q for q in result['queries'])


def test_configure_with_persist_mode_uses_set_persist():
    cursor = _make_mysql_cursor()

    tls = MySQLTLS(ModuleStub(), cursor, 'mysql')
    result = tls.configure(
        {'require_secure_transport': True},
        mode='persist',
    )

    assert result['changed'] is True
    assert any('SET PERSIST' in q for q in result['queries'])
    assert not any('SET GLOBAL' in q for q in result['queries'])
