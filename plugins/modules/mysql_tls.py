#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_tls

short_description: Manage MySQL or MariaDB TLS runtime settings

description:
  - Manage selected TLS runtime settings for MySQL or MariaDB.
  - MySQL supports certificate paths, TLS versions, secure transport, and explicit reloads.
  - MariaDB support in this module is limited to the runtime C(require_secure_transport) setting.
  - In this module, MariaDB does not support certificate path management, C(tls_version),
    explicit reloads, or C(mode=persist).

author:
  - Ron Gershburg (@ronger4)
  - Steve Fulmer (@stevefulme1)

version_added: '5.2.0'

options:
  server_cert:
    description:
      - Path to the TLS server certificate on the database host.
    type: path
    version_added: '5.2.0'
  server_key:
    description:
      - Path to the TLS server private key on the database host.
    type: path
    version_added: '5.2.0'
  server_ca:
    description:
      - Path to the TLS CA certificate on the database host.
    type: path
    version_added: '5.2.0'
  require_secure_transport:
    description:
      - Require encrypted client connections.
    type: bool
    version_added: '5.2.0'
  tls_version:
    description:
      - Allowed TLS protocol versions.
    type: str
    version_added: '5.2.0'
  reload:
    description:
      - Execute C(ALTER INSTANCE RELOAD TLS) after applying changes.
      - Reload is explicit and is only attempted when settings actually change.
      - MariaDB does not support O(reload) in this module.
    type: bool
    default: false
    version_added: '5.2.0'
  mode:
    description:
      - How runtime values are written.
      - C(global) uses C(SET GLOBAL).
      - C(persist) uses C(SET PERSIST) and depends on MySQL 8.0 or later support for that statement.
      - In this module, C(persist) is supported only for MySQL and is rejected for MariaDB.
    type: str
    choices:
      - global
      - persist
    default: global
    version_added: '5.2.0'

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

notes:
  - MariaDB support in this module is limited to runtime C(require_secure_transport).
  - On MariaDB, O(server_cert), O(server_key), O(server_ca), O(tls_version), O(reload),
    and O(mode=persist) are not supported by this module.

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Require secure transport
  ansible.mysql.mysql_tls:
    login_user: root
    login_password: rootpass
    require_secure_transport: true

- name: Configure MySQL TLS files and reload explicitly
  ansible.mysql.mysql_tls:
    login_user: root
    login_password: rootpass
    server_cert: /etc/mysql/ssl/server-cert.pem
    server_key: /etc/mysql/ssl/server-key.pem
    server_ca: /etc/mysql/ssl/ca-cert.pem
    reload: true
'''

RETURN = r'''
queries:
  description: List of executed queries which modified DB state.
  returned: always
  type: list
  elements: str
  sample:
    - SET GLOBAL `ssl_cert` = '/etc/mysql/ssl/server-cert.pem'
settings:
  description: Effective TLS settings after applying requested changes.
  returned: always
  type: dict
  sample:
    server_cert: /etc/mysql/ssl/server-cert.pem
    server_key: /etc/mysql/ssl/server-key.pem
    server_ca: /etc/mysql/ssl/ca-cert.pem
    require_secure_transport: 'ON'
    tls_version: TLSv1.3
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.ansible.mysql.plugins.module_utils.database import mysql_quote_identifier
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    get_server_implementation,
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)


PARAM_TO_VAR = {
    'server_cert': 'ssl_cert',
    'server_key': 'ssl_key',
    'server_ca': 'ssl_ca',
    'require_secure_transport': 'require_secure_transport',
    'tls_version': 'tls_version',
}

SUPPORTED_SETTINGS = {
    'mysql': tuple(PARAM_TO_VAR.keys()),
    'mariadb': ('require_secure_transport',),
}

MODE_CHOICES = ('global', 'persist')
RELOAD_QUERY = 'ALTER INSTANCE RELOAD TLS'


def get_variable(cursor, mysqlvar):
    cursor.execute("SHOW GLOBAL VARIABLES WHERE Variable_name = %s", (mysqlvar,))
    mysqlvar_val = cursor.fetchone()
    if mysqlvar_val:
        return mysqlvar_val[1]
    return None


def normalize_bool_setting(value):
    if isinstance(value, str):
        value = value.upper()

    if value in ('ON', '1', 1, True):
        return 'ON'
    if value in ('OFF', '0', 0, False):
        return 'OFF'
    return value


def format_query_value(value):
    if isinstance(value, str):
        if value in ('ON', 'OFF'):
            return value
        return "'%s'" % value.replace("'", "\\'")
    return str(value)


def set_variable(cursor, mysqlvar, value, mode, executed_queries):
    prefix = 'SET PERSIST' if mode == 'persist' else 'SET GLOBAL'
    query = "%s %s = " % (prefix, mysql_quote_identifier(mysqlvar, 'vars'))

    try:
        cursor.execute(query + "%s", (value,))
        cursor.fetchall()
    except Exception as e:
        return to_native(e)

    executed_queries.append(query + format_query_value(value))
    return True


class MySQLTLS(object):
    def __init__(self, module, cursor, server_implementation):
        self.module = module
        self.cursor = cursor
        self.server_implementation = server_implementation

    def configure(self, desired_settings, reload=False, mode='global', check_mode=False):
        self.validate_server_support(desired_settings, reload, mode)

        current_settings = self.get_current_settings()
        effective_settings = current_settings.copy()
        planned_changes = []

        for setting_name, value in desired_settings.items():
            if value is None:
                continue

            normalized_value = self.normalize_value(setting_name, value)
            variable_name = PARAM_TO_VAR[setting_name]
            effective_settings[setting_name] = normalized_value

            if current_settings.get(setting_name) != normalized_value:
                planned_changes.append((setting_name, variable_name, normalized_value))

        changed = bool(planned_changes)
        queries = []

        if check_mode:
            for _setting_name, variable_name, value in planned_changes:
                queries.append(self.format_set_query(variable_name, value, mode))

            if reload and changed:
                queries.append(RELOAD_QUERY)

            return dict(changed=changed, queries=queries, settings=effective_settings)

        for _setting_name, variable_name, value in planned_changes:
            result = set_variable(self.cursor, variable_name, value, mode, queries)
            if result is not True:
                self.module.fail_json(msg=result, changed=False)

        if reload and changed:
            try:
                self.cursor.execute(RELOAD_QUERY)
                self.cursor.fetchall()
            except Exception as e:
                self.module.fail_json(msg="Cannot execute SQL '%s': %s" % (RELOAD_QUERY, to_native(e)))

            queries.append(RELOAD_QUERY)

        return dict(changed=changed, queries=queries, settings=effective_settings)

    def validate_server_support(self, desired_settings, reload, mode):
        if self.server_implementation != 'mariadb':
            return

        if mode == 'persist':
            self.module.fail_json(
                msg='MariaDB does not support mysql_tls mode "persist"',
                changed=False,
            )

        unsupported_settings = [
            setting_name for setting_name, value in desired_settings.items()
            if value is not None and setting_name not in SUPPORTED_SETTINGS['mariadb']
        ]
        if unsupported_settings:
            self.module.fail_json(
                msg='MariaDB does not support mysql_tls setting "%s"' % unsupported_settings[0],
                changed=False,
            )

        if reload:
            self.module.fail_json(msg='MariaDB does not support mysql_tls reload', changed=False)

    def get_current_settings(self):
        settings = {}

        for setting_name in SUPPORTED_SETTINGS[self.server_implementation]:
            variable_name = PARAM_TO_VAR[setting_name]
            value = get_variable(self.cursor, variable_name)
            if value is None:
                self.module.fail_json(
                    msg='TLS setting "%s" is not available on this server.' % setting_name,
                    changed=False,
                )

            settings[setting_name] = self.normalize_value(setting_name, value)

        return settings

    def normalize_value(self, setting_name, value):
        if setting_name == 'require_secure_transport':
            return normalize_bool_setting(value)
        return value

    @staticmethod
    def format_set_query(variable_name, value, mode):
        prefix = 'SET PERSIST' if mode == 'persist' else 'SET GLOBAL'
        return "%s `%s` = %s" % (prefix, variable_name, format_query_value(value))


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        server_cert=dict(type='path'),
        server_key=dict(type='path'),
        server_ca=dict(type='path'),
        require_secure_transport=dict(type='bool'),
        tls_version=dict(type='str'),
        reload=dict(type='bool', default=False),
        mode=dict(type='str', choices=list(MODE_CHOICES), default='global'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    connect_timeout = module.params['connect_timeout']
    login_user = module.params['login_user']
    login_password = module.params['login_password']
    ssl_cert = module.params['client_cert']
    ssl_key = module.params['client_key']
    ssl_ca = module.params['ca_cert']
    check_hostname = module.params['check_hostname']
    config_file = module.params['config_file']

    try:
        cursor, _db_conn = mysql_connect(
            module,
            login_user,
            login_password,
            config_file,
            ssl_cert,
            ssl_key,
            ssl_ca,
            'mysql',
            connect_timeout=connect_timeout,
            check_hostname=check_hostname,
        )
    except Exception as e:
        module.fail_json(
            msg="unable to connect to database, check login_user and "
                "login_password are correct or %s has the credentials. "
                "Exception message: %s" % (config_file, to_native(e))
        )

    desired_settings = {
        'server_cert': module.params['server_cert'],
        'server_key': module.params['server_key'],
        'server_ca': module.params['server_ca'],
        'require_secure_transport': module.params['require_secure_transport'],
        'tls_version': module.params['tls_version'],
    }

    tls = MySQLTLS(module, cursor, get_server_implementation(cursor))

    module.exit_json(
        **tls.configure(
            desired_settings,
            reload=module.params['reload'],
            mode=module.params['mode'],
            check_mode=module.check_mode,
        )
    )


if __name__ == '__main__':
    main()
