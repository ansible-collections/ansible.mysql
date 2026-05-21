#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_tls

short_description: Configure server-side TLS for MySQL

description:
- Configure server-side TLS settings for MySQL 8.0+.
- Set TLS certificate paths, enforce secure transport, and control allowed TLS versions.
- Supports hot-reloading TLS configuration without server restart (MySQL 8.0.16+).

version_added: '5.1.0'

author:
- Steve Fulmer (@stevefulme1)

options:
  server_cert:
    description:
    - Path to the server SSL/TLS certificate file on the MySQL server host.
    type: path
  server_key:
    description:
    - Path to the server SSL/TLS private key file on the MySQL server host.
    type: path
  server_ca:
    description:
    - Path to the Certificate Authority (CA) certificate file on the MySQL server host.
    type: path
  require_secure_transport:
    description:
    - Whether to require encrypted connections from all clients.
    - When V(true), the server rejects non-SSL connections.
    type: bool
  tls_version:
    description:
    - Comma-separated list of TLS protocol versions the server permits.
    - For example, V(TLSv1.2,TLSv1.3).
    type: str
  reload:
    description:
    - Whether to execute C(ALTER INSTANCE RELOAD TLS) after applying changes.
    - This causes the server to hot-reload its TLS context without a restart.
    - Requires MySQL 8.0.16 or later.
    type: bool
    default: false
  state:
    description:
    - V(present) configures TLS with the specified parameters.
    - V(absent) resets TLS-related variables to their compiled-in defaults
      (empty strings for paths, V(OFF) for require_secure_transport).
    type: str
    choices: ['present', 'absent']
    default: present

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_variables
- name: MySQL TLS configuration reference
  description: Complete reference for configuring MySQL encrypted connections.
  link: https://dev.mysql.com/doc/refman/8.0/en/using-encrypted-connections.html

notes:
   - Requires MySQL 8.0 or later.
   - The O(server_cert), O(server_key), and O(server_ca) paths must be readable by the MySQL server process.
   - The O(reload) option requires MySQL 8.0.16 or later.

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Configure TLS with certificate files
  ansible.mysql.mysql_tls:
    server_cert: /etc/mysql/ssl/server-cert.pem
    server_key: /etc/mysql/ssl/server-key.pem
    server_ca: /etc/mysql/ssl/ca-cert.pem
    reload: true
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Enforce secure transport and restrict to TLSv1.3
  ansible.mysql.mysql_tls:
    require_secure_transport: true
    tls_version: 'TLSv1.3'
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Reset TLS configuration to defaults
  ansible.mysql.mysql_tls:
    state: absent
    reload: true
    login_unix_socket: /run/mysqld/mysqld.sock
'''

RETURN = r'''
queries:
  description: List of executed queries which modified the server state.
  returned: if changed
  type: list
  sample: ["SET GLOBAL `ssl_cert` = '/etc/mysql/ssl/server-cert.pem'"]
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
PARAM_TO_VAR = {
    'server_cert': 'ssl_cert',
    'server_key': 'ssl_key',
    'server_ca': 'ssl_ca',
    'require_secure_transport': 'require_secure_transport',
    'tls_version': 'tls_version',
}

# Default (absent) values for each variable
DEFAULT_VALUES = {
    'server_cert': '',
    'server_key': '',
    'server_ca': '',
    'require_secure_transport': 'OFF',
    'tls_version': '',
}


def get_tls_variables(cursor):
    """Retrieve current TLS-related global variables."""
    result = {}
    for var_name in PARAM_TO_VAR.values():
        cursor.execute("SHOW VARIABLES WHERE Variable_name = %s", (var_name,))
        row = cursor.fetchone()
        if row:
            result[var_name] = row[1]
        else:
            result[var_name] = None
    return result


def set_global_variable(cursor, var_name, value):
    """Set a global variable and return the query string."""
    query = "SET GLOBAL %s = " % mysql_quote_identifier(var_name, 'vars')
    cursor.execute(query + "%s", (value,))
    return query + "'%s'" % value


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        server_cert=dict(type='path'),
        server_key=dict(type='path'),
        server_ca=dict(type='path'),
        require_secure_transport=dict(type='bool'),
        tls_version=dict(type='str'),
        reload=dict(type='bool', default=False),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    user = module.params["login_user"]
    password = module.params["login_password"]
    connect_timeout = module.params['connect_timeout']
    server_cert = module.params["client_cert"]
    server_key = module.params["client_key"]
    server_ca = module.params["ca_cert"]
    check_hostname = module.params["check_hostname"]
    config_file = module.params['config_file']
    db = 'mysql'

    state = module.params['state']
    do_reload = module.params['reload']

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)
    else:
        warnings.filterwarnings('error', category=mysql_driver.Warning)

    try:
        cursor, db_conn = mysql_connect(
            module, user, password, config_file,
            server_cert, server_key, server_ca, db,
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

    # Get current state
    current = get_tls_variables(cursor)

    # Build desired state
    desired = {}
    if state == 'absent':
        desired = dict(DEFAULT_VALUES)
    else:
        for param, var_name in PARAM_TO_VAR.items():
            val = module.params[param]
            if val is not None:
                if param == 'require_secure_transport':
                    desired[var_name] = 'ON' if val else 'OFF'
                else:
                    desired[var_name] = val

    # Determine changes needed
    changes = {}
    for var_name, desired_val in desired.items():
        current_val = current.get(var_name, '')
        if str(desired_val) != str(current_val):
            changes[var_name] = desired_val

    changed = bool(changes)

    if not changed and not do_reload:
        module.exit_json(changed=False, msg="TLS configuration is already in the desired state.")

    executed_queries = []

    if module.check_mode:
        # In check mode, predict what would change
        for var_name, val in changes.items():
            executed_queries.append("SET GLOBAL `%s` = '%s'" % (var_name, val))
        if do_reload and (changed or do_reload):
            executed_queries.append("ALTER INSTANCE RELOAD TLS")
        module.exit_json(changed=changed or do_reload, queries=executed_queries)

    # Apply changes
    try:
        for var_name, val in changes.items():
            query_str = set_global_variable(cursor, var_name, val)
            executed_queries.append(query_str)
    except Exception as e:
        module.fail_json(msg="Failed to set TLS variable: %s" % to_native(e))

    # Reload TLS context if requested
    if do_reload:
        try:
            cursor.execute("ALTER INSTANCE RELOAD TLS")
            executed_queries.append("ALTER INSTANCE RELOAD TLS")
            changed = True
        except Exception as e:
            module.fail_json(
                msg="Failed to reload TLS context. "
                    "This requires MySQL 8.0.16 or later. "
                    "Exception: %s" % to_native(e)
            )

    module.exit_json(changed=changed, queries=executed_queries)


if __name__ == '__main__':
    main()
