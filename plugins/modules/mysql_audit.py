#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_audit

short_description: Manage MySQL audit log plugin and filters

description:
- Install or uninstall the MySQL audit log plugin.
- Configure audit log filters and assign them to users.
- Set the audit log format and trigger log rotation.
- Supports the component_audit_api_message_emit component (MySQL 8.0+)
  and the audit_log plugin.

version_added: '5.1.0'

author:
- Steve Fulmer (@stevefulme1)

options:
  state:
    description:
    - Whether the audit plugin should be installed (C(present)) or removed (C(absent)).
    type: str
    choices: ['present', 'absent']
    default: present
    version_added: '5.1.0'
  log_format:
    description:
    - The audit log output format.
    - Only applied when the audit plugin is installed.
    type: str
    choices: ['JSON', 'XML', 'CSV']
    default: JSON
    version_added: '5.1.0'
  filter_name:
    description:
    - Name of the audit filter to create or remove.
    - Required when O(filter_rule) is provided.
    type: str
    version_added: '5.1.0'
  filter_rule:
    description:
    - A dictionary defining the audit filter rule (JSON filter document).
    - Requires O(filter_name) to be set.
    type: dict
    version_added: '5.1.0'
  users:
    description:
    - List of MySQL user accounts (in C(user@host) format) to apply the filter to.
    - Requires O(filter_name) to be set.
    type: list
    elements: str
    version_added: '5.1.0'
  rotate:
    description:
    - Whether to trigger audit log rotation.
    type: bool
    default: false
    version_added: '5.1.0'

attributes:
  check_mode:
    support: partial
    details:
      - In check mode the module reports what changes would be made
        without executing them.
  idempotent:
    support: partial
    details:
      - The module checks current state before making changes.
      - Log rotation (O(rotate=true)) always reports changed.

seealso:
- module: ansible.mysql.mysql_audit_info
- module: ansible.mysql.mysql_variables
- name: MySQL Audit Log reference
  description: MySQL Enterprise Audit documentation.
  link: https://dev.mysql.com/doc/refman/8.0/en/audit-log.html

notes:
   - Compatible with MySQL only. MariaDB has a separate audit plugin.
   - Requires the MySQL Enterprise Audit plugin files to be available
     on the server.

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Install the audit log plugin
  ansible.mysql.mysql_audit:
    state: present
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Set audit log format to JSON
  ansible.mysql.mysql_audit:
    state: present
    log_format: JSON
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Create and assign an audit filter
  ansible.mysql.mysql_audit:
    state: present
    filter_name: log_all
    filter_rule:
      filter:
        log: true
    users:
      - root@localhost
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Rotate the audit log
  ansible.mysql.mysql_audit:
    state: present
    rotate: true
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Uninstall the audit log plugin
  ansible.mysql.mysql_audit:
    state: absent
    login_unix_socket: /run/mysqld/mysqld.sock
'''

RETURN = r'''
queries:
  description: List of executed queries which modified the server state.
  returned: if executed
  type: list
  sample: ["INSTALL COMPONENT 'file://component_audit_api_message_emit'"]
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

executed_queries = []


def is_audit_plugin_installed(cursor):
    """Check whether any audit log component or plugin is installed."""
    # Check for component (MySQL 8.0+)
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

    # Check for legacy plugin
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


def install_audit_plugin(cursor):
    """Install the audit log component."""
    query = "INSTALL COMPONENT 'file://component_audit_api_message_emit'"
    cursor.execute(query)
    executed_queries.append(query)


def uninstall_audit_plugin(cursor):
    """Uninstall the audit log component."""
    query = "UNINSTALL COMPONENT 'file://component_audit_api_message_emit'"
    cursor.execute(query)
    executed_queries.append(query)


def get_audit_log_format(cursor):
    """Return current audit_log_format value or None."""
    try:
        cursor.execute("SHOW VARIABLES LIKE 'audit_log_format'")
        row = cursor.fetchone()
        if row:
            return row[1]
    except Exception:
        pass
    return None


def set_audit_log_format(cursor, log_format):
    """Set the global audit_log_format variable."""
    query = "SET GLOBAL audit_log_format = %s"
    cursor.execute(query, (log_format,))
    executed_queries.append("SET GLOBAL audit_log_format = '%s'" % log_format)


def set_audit_filter(cursor, filter_name, filter_rule):
    """Create or replace an audit filter."""
    rule_json = json.dumps(filter_rule)
    query = "SELECT audit_log_filter_set_filter(%s, %s)"
    cursor.execute(query, (filter_name, rule_json))
    executed_queries.append(
        "SELECT audit_log_filter_set_filter('%s', '%s')" % (filter_name, rule_json)
    )


def remove_audit_filter(cursor, filter_name):
    """Remove an audit filter."""
    query = "SELECT audit_log_filter_remove_filter(%s)"
    cursor.execute(query, (filter_name,))
    executed_queries.append(
        "SELECT audit_log_filter_remove_filter('%s')" % filter_name
    )


def set_user_filter(cursor, user, filter_name):
    """Assign a filter to a user."""
    query = "SELECT audit_log_filter_set_user(%s, %s)"
    cursor.execute(query, (user, filter_name))
    executed_queries.append(
        "SELECT audit_log_filter_set_user('%s', '%s')" % (user, filter_name)
    )


def remove_user_filter(cursor, user):
    """Remove filter assignment from a user."""
    query = "SELECT audit_log_filter_remove_user(%s)"
    cursor.execute(query, (user,))
    executed_queries.append(
        "SELECT audit_log_filter_remove_user('%s')" % user
    )


def get_existing_filters(cursor):
    """Return a dict of existing filter names to their definitions."""
    filters = {}
    try:
        cursor.execute(
            "SELECT NAME, FILTER FROM mysql.audit_log_filter"
        )
        for row in cursor.fetchall():
            filters[row[0]] = row[1]
    except Exception:
        pass
    return filters


def get_user_filter_assignments(cursor):
    """Return a dict of user -> filter_name assignments."""
    assignments = {}
    try:
        cursor.execute(
            "SELECT USER, FILTERNAME FROM mysql.audit_log_user"
        )
        for row in cursor.fetchall():
            assignments[row[0]] = row[1]
    except Exception:
        pass
    return assignments


def rotate_audit_log(cursor):
    """Trigger audit log rotation."""
    query = "SET GLOBAL audit_log_rotate = ON"
    cursor.execute(query)
    executed_queries.append(query)


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        state=dict(type='str', choices=['present', 'absent'], default='present'),
        log_format=dict(type='str', choices=['JSON', 'XML', 'CSV'], default='JSON'),
        filter_name=dict(type='str'),
        filter_rule=dict(type='dict'),
        users=dict(type='list', elements='str'),
        rotate=dict(type='bool', default=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_together=[
            ('filter_name', 'filter_rule'),
        ],
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
    log_format = module.params['log_format']
    filter_name = module.params['filter_name']
    filter_rule = module.params['filter_rule']
    users = module.params['users']
    rotate = module.params['rotate']

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
            msg="mysql_audit does not support MariaDB. "
                "MariaDB uses a separate audit plugin (server_audit). "
                "See https://mariadb.com/kb/en/mariadb-audit-plugin/"
        )

    changed = False

    try:
        plugin_installed = is_audit_plugin_installed(cursor)

        if state == 'absent':
            if plugin_installed:
                if not module.check_mode:
                    uninstall_audit_plugin(cursor)
                changed = True

            module.exit_json(changed=changed, queries=executed_queries)

        # state == 'present'
        if not plugin_installed:
            if not module.check_mode:
                install_audit_plugin(cursor)
            changed = True

        # Set log format if plugin is now installed
        if not module.check_mode and (plugin_installed or changed):
            current_format = get_audit_log_format(cursor)
            if current_format and current_format.upper() != log_format.upper():
                set_audit_log_format(cursor, log_format)
                changed = True

        # Configure filter
        if filter_name and filter_rule:
            existing_filters = get_existing_filters(cursor) if not module.check_mode else {}
            rule_json = json.dumps(filter_rule)

            needs_filter_update = True
            if filter_name in existing_filters:
                existing_rule = existing_filters[filter_name]
                if isinstance(existing_rule, str):
                    try:
                        existing_rule = json.loads(existing_rule)
                    except (ValueError, TypeError):
                        pass
                if existing_rule == filter_rule:
                    needs_filter_update = False

            if needs_filter_update:
                if not module.check_mode:
                    set_audit_filter(cursor, filter_name, filter_rule)
                changed = True

            # Assign filter to users
            if users:
                current_assignments = get_user_filter_assignments(cursor) if not module.check_mode else {}
                for u in users:
                    if current_assignments.get(u) != filter_name:
                        if not module.check_mode:
                            set_user_filter(cursor, u, filter_name)
                        changed = True

        # Rotate log
        if rotate:
            if not module.check_mode:
                rotate_audit_log(cursor)
            changed = True

    except Exception as e:
        module.fail_json(msg="Error managing audit plugin: %s" % to_native(e))

    module.exit_json(changed=changed, queries=executed_queries)


if __name__ == '__main__':
    main()
