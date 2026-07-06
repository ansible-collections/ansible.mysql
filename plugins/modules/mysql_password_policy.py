#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_password_policy

short_description: Manage MySQL or MariaDB password policy settings

description:
  - Manage password policy settings on MySQL or MariaDB.
  - This module is configuration-only and does not install or uninstall password validation components or plugins.
  - On MySQL, the module manages C(validate_password) settings and related global password policy variables.
  - On MariaDB, the module manages the C(simple_password_check) plugin settings only.

author:
  - Steve Fulmer (@stevefulme1)
  - Ron Gershburg (@ronger4)

version_added: '5.2.0'

options:
  policy:
    description:
      - Password validation policy level on MySQL.
      - Supported only on MySQL.
    type: str
    choices: [low, medium, strong]
  length:
    description:
      - Minimum number of characters in a password.
      - Maps to the active password validation facility for the current engine.
    type: int
  mixed_case_count:
    description:
      - Minimum number of lowercase and uppercase letters required each by the active password validation facility.
      - Supported on MySQL and on MariaDB C(simple_password_check).
    type: int
  number_count:
    description:
      - Minimum number of numeric characters required.
      - Supported on MySQL and on MariaDB C(simple_password_check).
    type: int
  special_char_count:
    description:
      - Minimum number of non-alphanumeric characters required.
      - Supported on MySQL and on MariaDB C(simple_password_check).
    type: int
  check_user_name:
    description:
      - Whether passwords are checked against the user name.
      - Supported only on MySQL.
    type: bool
  password_lifetime:
    description:
      - Default password expiration lifetime in days.
      - Supported only on MySQL.
    type: int
  password_history:
    description:
      - Number of previous passwords that cannot be reused.
      - Supported only on MySQL.
    type: int
  reuse_interval:
    description:
      - Number of days before a password can be reused.
      - Supported only on MySQL.
    type: int
  mode:
    description:
      - How supported MySQL variables are set.
      - V(global) uses C(SET GLOBAL) and does not survive restarts by itself.
      - V(persist) uses C(SET PERSIST) on MySQL.
      - Supported only on MySQL.
    type: str
    choices: [global, persist]
    default: global

notes:
  - The required password validation component or plugin must already be enabled on the target server.
  - The module does not install C(validate_password) or MariaDB password validation plugins.
  - MariaDB support in the first iteration is limited to C(simple_password_check).

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
  - module: ansible.mysql.mysql_query
  - module: ansible.mysql.mysql_variables
  - name: MySQL password validation component
    description: Oracle MySQL reference for validate_password.
    link: https://dev.mysql.com/doc/refman/8.4/en/validate-password.html
  - name: MariaDB simple password check plugin
    description: MariaDB reference for simple_password_check.
    link: https://mariadb.com/docs/server/reference/plugins/password-validation-plugins/simple-password-check-plugin

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Configure shared password complexity settings on MySQL
  ansible.mysql.mysql_password_policy:
    login_unix_socket: /run/mysqld/mysqld.sock
    length: 12
    mixed_case_count: 2
    number_count: 2
    special_char_count: 1

- name: Configure MySQL-specific password policy settings persistently
  ansible.mysql.mysql_password_policy:
    login_unix_socket: /run/mysqld/mysqld.sock
    policy: medium
    check_user_name: true
    password_lifetime: 90
    password_history: 5
    reuse_interval: 365
    mode: persist

- name: Configure MariaDB simple_password_check settings
  ansible.mysql.mysql_password_policy:
    login_unix_socket: /run/mysqld/mysqld.sock
    length: 14
    mixed_case_count: 2
    number_count: 2
    special_char_count: 2
'''

RETURN = r'''
queries:
  description: List of executed or predicted (in check mode) SQL statements.
  returned: always
  type: list
  elements: str
  sample:
    - SET GLOBAL `validate_password`.`length` = 12
settings:
  description: Normalized requested settings after execution or prediction (in check mode).
  returned: always
  type: dict
  sample:
    length: 12
    number_count: 2
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.ansible.mysql.plugins.module_utils._version import LooseVersion
from ansible_collections.ansible.mysql.plugins.module_utils.database import mysql_quote_identifier
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    get_server_implementation,
    get_server_version,
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)


SETTING_VARIABLES = {
    'mysql': {
        'policy': 'validate_password.policy',
        'length': 'validate_password.length',
        'mixed_case_count': 'validate_password.mixed_case_count',
        'number_count': 'validate_password.number_count',
        'special_char_count': 'validate_password.special_char_count',
        'check_user_name': 'validate_password.check_user_name',
        'password_lifetime': 'default_password_lifetime',
        'password_history': 'password_history',
        'reuse_interval': 'password_reuse_interval',
    },
    'mariadb': {
        'length': 'simple_password_check_minimal_length',
        'mixed_case_count': 'simple_password_check_letters_same_case',
        'number_count': 'simple_password_check_digits',
        'special_char_count': 'simple_password_check_other_characters',
    },
}

MYSQL_ONLY_OPTIONS = (
    'policy',
    'check_user_name',
    'password_lifetime',
    'password_history',
    'reuse_interval',
)

INTEGER_OPTIONS = (
    'length',
    'mixed_case_count',
    'number_count',
    'special_char_count',
    'password_lifetime',
    'password_history',
    'reuse_interval',
)


def normalize_int_value(value):
    if isinstance(value, int):
        return value

    return int(value)


def get_variable(cursor, mysqlvar):
    cursor.execute("SHOW GLOBAL VARIABLES WHERE Variable_name = %s", (mysqlvar,))
    rows = cursor.fetchall()
    return rows[0][1] if rows else None


def set_variable(cursor, mysqlvar, value, mode):
    query = "SET %s %s = " % (mode.upper(), mysql_quote_identifier(mysqlvar, 'vars'))
    cursor.execute(query + "%s", (value,))


def normalize_bool_setting_value(value):
    if isinstance(value, str):
        value = value.upper()

    if value in ('ON', '1', 1, True):
        return 'ON'
    if value in ('OFF', '0', 0, False):
        return 'OFF'
    return value


def normalize_policy_value(value):
    value = str(value).strip().lower()
    numeric_policy = {
        '0': 'low',
        '1': 'medium',
        '2': 'strong',
    }
    return numeric_policy.get(value, value)


class MySQLPasswordPolicy(object):
    def __init__(self, module, cursor, server_implementation):
        self.module = module
        self.cursor = cursor
        self.server_implementation = server_implementation

    def configure(self, desired_settings, mode='global', check_mode=False):
        self.validate_supported_settings(desired_settings, mode)

        effective_settings = {}
        planned_changes = []

        for setting_name, desired_value in desired_settings.items():
            if desired_value is None:
                continue

            variable_name, current_value = self.read_setting(setting_name)
            normalized_current = self.normalize_value(setting_name, current_value)
            normalized_desired = self.normalize_value(setting_name, desired_value)

            effective_settings[setting_name] = normalized_desired

            if normalized_current != normalized_desired:
                planned_changes.append(
                    (setting_name, variable_name, self.query_value(setting_name, normalized_desired))
                )

        queries = []
        changed = bool(planned_changes)

        if check_mode:
            for _setting_name, variable_name, query_value in planned_changes:
                queries.append(self.format_set_query(variable_name, query_value, mode))
            return dict(changed=changed, queries=queries, settings=effective_settings)

        for _setting_name, variable_name, query_value in planned_changes:
            try:
                set_variable(self.cursor, variable_name, query_value, mode)
            except Exception as exc:
                self.module.fail_json(
                    msg='Failed to set %s: %s' % (variable_name, to_native(exc)),
                    changed=False,
                )
            queries.append(self.format_set_query(variable_name, query_value, mode))

        return dict(changed=changed, queries=queries, settings=effective_settings)

    def validate_supported_settings(self, desired_settings, mode):
        if self.server_implementation == 'mariadb':
            if mode == 'persist':
                self.module.fail_json(msg='mode=persist is supported only on MySQL.', changed=False)

            for option_name in MYSQL_ONLY_OPTIONS:
                if desired_settings.get(option_name) is not None:
                    self.module.fail_json(
                        msg='Parameter "%s" is supported only on MySQL.' % option_name,
                        changed=False,
                    )

    def read_setting(self, setting_name):
        variable_name = SETTING_VARIABLES[self.server_implementation][setting_name]
        value = get_variable(self.cursor, variable_name)
        if value is not None:
            return variable_name, value

        self.module.fail_json(
            msg='Password policy setting "%s" is not available on this server.' % setting_name,
            changed=False,
        )

    def normalize_value(self, setting_name, value):
        if setting_name == 'policy':
            return normalize_policy_value(value)
        if setting_name == 'check_user_name':
            return normalize_bool_setting_value(value)
        if setting_name in INTEGER_OPTIONS:
            return normalize_int_value(value)
        return value

    def query_value(self, setting_name, normalized_value):
        if setting_name == 'policy':
            return str(normalized_value).upper()
        if setting_name == 'check_user_name':
            return normalize_bool_setting_value(normalized_value)
        return normalized_value

    @staticmethod
    def format_set_query(variable_name, value, mode):
        return "SET %s %s = %s" % (mode.upper(), mysql_quote_identifier(variable_name, 'vars'), value)


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        policy=dict(type='str', choices=['low', 'medium', 'strong']),
        length=dict(type='int'),
        mixed_case_count=dict(type='int'),
        number_count=dict(type='int'),
        special_char_count=dict(type='int'),
        check_user_name=dict(type='bool'),
        password_lifetime=dict(type='int', no_log=False),
        password_history=dict(type='int', no_log=False),
        reuse_interval=dict(type='int', no_log=False),
        mode=dict(type='str', choices=['global', 'persist'], default='global'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=[(
            'policy',
            'length',
            'mixed_case_count',
            'number_count',
            'special_char_count',
            'check_user_name',
            'password_lifetime',
            'password_history',
            'reuse_interval',
        )],
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    try:
        cursor, _db_conn = mysql_connect(
            module,
            module.params['login_user'],
            module.params['login_password'],
            module.params['config_file'],
            module.params['client_cert'],
            module.params['client_key'],
            module.params['ca_cert'],
            'mysql',
            connect_timeout=module.params['connect_timeout'],
            check_hostname=module.params['check_hostname'],
        )
    except Exception as exc:
        module.fail_json(
            msg="unable to connect to database, check login_user and "
                "login_password are correct or %s has the credentials. "
                "Exception message: %s" % (module.params['config_file'], to_native(exc))
        )

    server_implementation = get_server_implementation(cursor)
    if server_implementation == 'mysql':
        server_version = get_server_version(cursor).split('-', 1)[0]
        if module.params['mode'] == 'persist' and LooseVersion(server_version) < LooseVersion('8.0'):
            module.fail_json(msg='mode=persist requires MySQL 8.0 or later.', changed=False)

    desired_settings = {
        'policy': module.params['policy'],
        'length': module.params['length'],
        'mixed_case_count': module.params['mixed_case_count'],
        'number_count': module.params['number_count'],
        'special_char_count': module.params['special_char_count'],
        'check_user_name': module.params['check_user_name'],
        'password_lifetime': module.params['password_lifetime'],
        'password_history': module.params['password_history'],
        'reuse_interval': module.params['reuse_interval'],
    }

    password_policy = MySQLPasswordPolicy(module, cursor, server_implementation)
    module.exit_json(
        **password_policy.configure(
            desired_settings,
            mode=module.params['mode'],
            check_mode=module.check_mode,
        )
    )


if __name__ == '__main__':
    main()
