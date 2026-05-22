#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_password_policy

short_description: Configure MySQL password validation policy

description:
- Manage the MySQL C(validate_password) component and related global variables.
- Install or uninstall the C(validate_password) component (MySQL 8.0+).
- Configure password complexity requirements, lifetime, and reuse policies.

version_added: '5.1.0'

author:
- Steve Fulmer (@stevefulme1)

options:
  state:
    description:
    - V(present) ensures the C(validate_password) component is installed
      and configured with the specified settings.
    - V(absent) uninstalls the C(validate_password) component.
    type: str
    choices: ['present', 'absent']
    default: present
  policy:
    description:
    - Password validation policy level.
    - V(LOW) checks length only.
    - V(MEDIUM) checks length, numeric, mixed case, and special characters.
    - V(STRONG) checks all of V(MEDIUM) plus dictionary file.
    type: str
    choices: ['LOW', 'MEDIUM', 'STRONG']
  length:
    description:
    - Minimum number of characters in a password.
    type: int
  mixed_case_count:
    description:
    - Minimum number of uppercase and lowercase characters required.
    type: int
  number_count:
    description:
    - Minimum number of numeric characters required.
    type: int
  special_char_count:
    description:
    - Minimum number of special (non-alphanumeric) characters required.
    type: int
  check_user_name:
    description:
    - Whether passwords are checked against the user name.
    - When V(true), passwords that match the user name are rejected.
    type: bool
  password_lifetime:
    description:
    - Default password expiration lifetime in days.
    - V(0) disables automatic password expiration.
    type: int
  password_history:
    description:
    - Number of previous passwords that cannot be reused.
    - V(0) disables password history checks.
    type: int
  reuse_interval:
    description:
    - Number of days before a password can be reused.
    - V(0) disables reuse interval checks.
    type: int

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_variables
- module: ansible.mysql.mysql_user
- name: MySQL Password Validation Component
  description: Reference for the validate_password component.
  link: https://dev.mysql.com/doc/refman/8.0/en/validate-password.html

notes:
   - Requires MySQL 8.0 or later.
   - The C(validate_password) component must be available on the server.
   - In MySQL 5.7, the validate_password plugin uses underscores in variable
     names (e.g., C(validate_password_policy)) rather than dots. This module
     targets MySQL 8.0+ component syntax with dot notation.

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Install validate_password component with MEDIUM policy
  ansible.mysql.mysql_password_policy:
    state: present
    policy: MEDIUM
    length: 12
    mixed_case_count: 1
    number_count: 1
    special_char_count: 1
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Set password lifetime and history policies
  ansible.mysql.mysql_password_policy:
    password_lifetime: 90
    password_history: 5
    reuse_interval: 365
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Uninstall validate_password component
  ansible.mysql.mysql_password_policy:
    state: absent
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Enforce STRONG policy with username check
  ansible.mysql.mysql_password_policy:
    policy: STRONG
    length: 16
    check_user_name: true
    login_unix_socket: /run/mysqld/mysqld.sock
'''

RETURN = r'''
queries:
  description: List of executed queries which modified the server state.
  returned: if changed
  type: list
  sample: ["SET GLOBAL `validate_password.policy` = 'MEDIUM'"]
  version_added: '5.1.0'
'''

import os
import warnings

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansible.mysql.plugins.module_utils.database import mysql_quote_identifier
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
    mysql_common_argument_spec,
)
from ansible.module_utils.common.text.converters import to_native


# Mapping of module parameters to MySQL global variable names
# validate_password.* variables only exist when the component is installed
VALIDATE_PASSWORD_PARAMS = {
    'policy': 'validate_password.policy',
    'length': 'validate_password.length',
    'mixed_case_count': 'validate_password.mixed_case_count',
    'number_count': 'validate_password.number_count',
    'special_char_count': 'validate_password.special_char_count',
    'check_user_name': 'validate_password.check_user_name',
}

# Global password policy variables (exist regardless of component)
GLOBAL_PASSWORD_PARAMS = {
    'password_lifetime': 'default_password_lifetime',
    'password_history': 'password_history',
    'reuse_interval': 'password_reuse_interval',
}

# Policy name to numeric value mapping for comparison
POLICY_MAP = {
    'LOW': '0',
    'MEDIUM': '1',
    'STRONG': '2',
    '0': '0',
    '1': '1',
    '2': '2',
}


def is_component_installed(cursor):
    """Check if validate_password component is installed."""
    try:
        cursor.execute("SHOW VARIABLES LIKE 'validate_password.policy'")
        return cursor.fetchone() is not None
    except Exception:
        return False


def get_current_variables(cursor, var_pattern):
    """Retrieve current variable values matching a LIKE pattern."""
    result = {}
    cursor.execute("SHOW VARIABLES LIKE %s", (var_pattern,))
    for row in cursor.fetchall():
        result[row[0]] = row[1]
    return result


def get_variable(cursor, var_name):
    """Get a single variable value."""
    cursor.execute("SHOW VARIABLES WHERE Variable_name = %s", (var_name,))
    row = cursor.fetchone()
    if row:
        return row[1]
    return None


def set_global_variable(cursor, var_name, value):
    """Set a global variable and return the query string."""
    query = "SET GLOBAL %s = " % mysql_quote_identifier(var_name, 'vars')
    cursor.execute(query + "%s", (value,))
    return query + "'%s'" % value


def install_component(cursor):
    """Install the validate_password component."""
    query = "INSTALL COMPONENT 'file://component_validate_password'"
    cursor.execute(query)
    return query


def uninstall_component(cursor):
    """Uninstall the validate_password component."""
    query = "UNINSTALL COMPONENT 'file://component_validate_password'"
    cursor.execute(query)
    return query


def values_match(var_name, current_val, desired_val):
    """Compare current and desired values, handling type differences."""
    if current_val is None:
        return False

    # Policy can be reported as name or number
    if var_name == 'validate_password.policy':
        current_norm = POLICY_MAP.get(str(current_val).upper(), str(current_val))
        desired_norm = POLICY_MAP.get(str(desired_val).upper(), str(desired_val))
        return current_norm == desired_norm

    # Boolean ON/OFF comparison
    if var_name == 'validate_password.check_user_name':
        current_norm = str(current_val).upper()
        if isinstance(desired_val, bool):
            desired_norm = 'ON' if desired_val else 'OFF'
        else:
            desired_norm = str(desired_val).upper()
        return current_norm == desired_norm

    return str(current_val) == str(desired_val)


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        policy=dict(type='str', choices=['LOW', 'MEDIUM', 'STRONG']),
        length=dict(type='int'),
        mixed_case_count=dict(type='int'),
        number_count=dict(type='int'),
        special_char_count=dict(type='int'),
        check_user_name=dict(type='bool'),
        password_lifetime=dict(type='int', no_log=False),
        password_history=dict(type='int', no_log=False),
        reuse_interval=dict(type='int'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    user = module.params["login_user"]
    password = module.params["login_password"]
    connect_timeout = module.params['connect_timeout']
    ssl_cert = module.params["client_cert"]
    ssl_key = module.params["client_key"]
    ssl_ca = module.params["ca_cert"]
    check_hostname = module.params["check_hostname"]
    config_file = module.params['config_file']
    db = 'mysql'

    state = module.params['state']

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)
    else:
        warnings.filterwarnings('error', category=mysql_driver.Warning)

    try:
        cursor, db_conn = mysql_connect(
            module, user, password, config_file,
            ssl_cert, ssl_key, ssl_ca, db,
            connect_timeout=connect_timeout,
            check_hostname=check_hostname,
        )
    except Exception as e:
        if os.path.exists(config_file):
            module.fail_json(
                msg="unable to connect to database, check login_user and "
                    "login_password are correct or %s has the credentials. "
                    "Exception message: %s" % (config_file, to_native(e))
            )
        else:
            module.fail_json(
                msg="unable to find %s. Exception message: %s" % (config_file, to_native(e))
            )

    installed = is_component_installed(cursor)
    changed = False
    executed_queries = []

    if state == 'absent':
        if not installed:
            module.exit_json(changed=False, msg="validate_password component is not installed.")

        if module.check_mode:
            module.exit_json(
                changed=True,
                queries=["UNINSTALL COMPONENT 'file://component_validate_password'"],
            )

        try:
            query = uninstall_component(cursor)
            executed_queries.append(query)
            changed = True
        except Exception as e:
            module.fail_json(msg="Failed to uninstall validate_password component: %s" % to_native(e))

        module.exit_json(changed=changed, queries=executed_queries)

    # state == 'present'
    # Install component if not present
    if not installed:
        if module.check_mode:
            executed_queries.append("INSTALL COMPONENT 'file://component_validate_password'")
            changed = True
        else:
            try:
                query = install_component(cursor)
                executed_queries.append(query)
                changed = True
            except Exception as e:
                module.fail_json(
                    msg="Failed to install validate_password component: %s" % to_native(e)
                )

    # Configure validate_password.* variables
    for param, var_name in VALIDATE_PASSWORD_PARAMS.items():
        desired_val = module.params[param]
        if desired_val is None:
            continue

        if not module.check_mode:
            current_val = get_variable(cursor, var_name)
        else:
            # In check mode after install, we cannot read vars that don't exist yet
            current_val = None if not installed and changed else get_variable(cursor, var_name)

        if param == 'check_user_name':
            set_val = 'ON' if desired_val else 'OFF'
        else:
            set_val = desired_val

        if not values_match(var_name, current_val, desired_val):
            if module.check_mode:
                executed_queries.append("SET GLOBAL `%s` = '%s'" % (var_name, set_val))
            else:
                try:
                    query = set_global_variable(cursor, var_name, set_val)
                    executed_queries.append(query)
                except Exception as e:
                    module.fail_json(msg="Failed to set %s: %s" % (var_name, to_native(e)))
            changed = True

    # Configure global password policy variables
    for param, var_name in GLOBAL_PASSWORD_PARAMS.items():
        desired_val = module.params[param]
        if desired_val is None:
            continue

        current_val = get_variable(cursor, var_name)

        if not values_match(var_name, current_val, desired_val):
            if module.check_mode:
                executed_queries.append("SET GLOBAL `%s` = '%s'" % (var_name, desired_val))
            else:
                try:
                    query = set_global_variable(cursor, var_name, desired_val)
                    executed_queries.append(query)
                except Exception as e:
                    module.fail_json(msg="Failed to set %s: %s" % (var_name, to_native(e)))
            changed = True

    module.exit_json(changed=changed, queries=executed_queries)


if __name__ == '__main__':
    main()
