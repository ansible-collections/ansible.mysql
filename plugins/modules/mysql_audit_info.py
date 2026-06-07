#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_audit_info

short_description: Gather information about MySQL audit log configuration

description:
- Returns the current audit log plugin status, active filters,
  user filter assignments, log format, and log file path.

version_added: '5.1.0'

author:
- Steve Fulmer (@stevefulme1)

options: {}

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

seealso:
- module: ansible.mysql.mysql_audit
- module: ansible.mysql.mysql_info

notes:
   - Compatible with MySQL only. MariaDB has a separate audit plugin.

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Gather audit log information
  ansible.mysql.mysql_audit_info:
    login_unix_socket: /run/mysqld/mysqld.sock
  register: audit_info

- name: Display audit plugin status
  ansible.builtin.debug:
    var: audit_info.plugin_installed

- name: Display active filters
  ansible.builtin.debug:
    var: audit_info.filters
'''

RETURN = r'''
plugin_installed:
  description: Whether the audit log plugin is installed and active.
  returned: always
  type: bool
  sample: true
log_format:
  description: Current audit log format setting.
  returned: when plugin is installed
  type: str
  sample: "JSON"
log_file:
  description: Path to the audit log file.
  returned: when plugin is installed
  type: str
  sample: "/var/lib/mysql/audit.log"
  version_added: '5.1.0'
filters:
  description: Dictionary of defined audit filters and their rules.
  returned: when plugin is installed
  type: dict
  sample: {"log_all": {"filter": {"log": true}}}
  version_added: '5.1.0'
user_assignments:
  description: Dictionary mapping users to their assigned filter names.
  returned: when plugin is installed
  type: dict
  sample: {"root@localhost": "log_all"}
  version_added: '5.1.0'
'''

import json
import os
import warnings

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
    mysql_common_argument_spec,
    get_server_implementation,
)
from ansible.module_utils.common.text.converters import to_native


def is_audit_plugin_installed(cursor):
    """Check whether any audit log component or plugin is installed."""
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM mysql.component "
            "WHERE component_urn = 'file://component_audit_api_message_emit'"
        )
        row = cursor.fetchone()
        if row and row[0] > 0:
            return True
    except Exception:
        pass

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.PLUGINS "
            "WHERE PLUGIN_NAME = 'audit_log' AND PLUGIN_STATUS = 'ACTIVE'"
        )
        row = cursor.fetchone()
        if row and row[0] > 0:
            return True
    except Exception:
        pass

    return False


def get_variable(cursor, var_name):
    """Return the value of a MySQL variable or None."""
    try:
        cursor.execute("SHOW VARIABLES LIKE %s", (var_name,))
        row = cursor.fetchone()
        if row:
            return row[1]
    except Exception:
        pass
    return None


def get_filters(cursor):
    """Return a dict of filter names to their parsed definitions."""
    filters = {}
    try:
        cursor.execute("SELECT NAME, FILTER FROM mysql.audit_log_filter")
        for row in cursor.fetchall():
            name = row[0]
            rule = row[1]
            if isinstance(rule, str):
                try:
                    rule = json.loads(rule)
                except (ValueError, TypeError):
                    pass
            filters[name] = rule
    except Exception:
        pass
    return filters


def get_user_assignments(cursor):
    """Return a dict of user -> filter_name assignments."""
    assignments = {}
    try:
        cursor.execute("SELECT USER, FILTERNAME FROM mysql.audit_log_user")
        for row in cursor.fetchall():
            assignments[row[0]] = row[1]
    except Exception:
        pass
    return assignments


def main():
    argument_spec = mysql_common_argument_spec()

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
                msg="unable to find %s. Exception message: %s"
                    % (config_file, to_native(e))
            )

    server_implementation = get_server_implementation(cursor)
    if server_implementation == "mariadb":
        module.fail_json(
            msg="mysql_audit_info does not support MariaDB. "
                "MariaDB uses a separate audit plugin (server_audit). "
                "See https://mariadb.com/kb/en/mariadb-audit-plugin/"
        )

    result = {}

    try:
        result['plugin_installed'] = is_audit_plugin_installed(cursor)

        if result['plugin_installed']:
            result['log_format'] = get_variable(cursor, 'audit_log_format')
            result['log_file'] = get_variable(cursor, 'audit_log_file')
            result['filters'] = get_filters(cursor)
            result['user_assignments'] = get_user_assignments(cursor)
        else:
            result['log_format'] = None
            result['log_file'] = None
            result['filters'] = {}
            result['user_assignments'] = {}

    except Exception as e:
        module.fail_json(msg="Error gathering audit info: %s" % to_native(e))

    module.exit_json(changed=False, **result)


if __name__ == '__main__':
    main()
