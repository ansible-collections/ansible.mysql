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
- On MySQL 8.0+ the module uses C(INSTALL COMPONENT) for the
  C(component_audit_api_message_emit) component.

version_added: '5.1.0'

author:
- Steve Fulmer (@stevefulme1)

options:
  state:
    description:
    - Controls what the module manages.
    - When V(present), installs the audit plugin, configures
      log format, creates or updates filters, and assigns users.
    - When V(absent) without O(filter_name), uninstalls the audit plugin.
    - When V(absent) with O(filter_name), removes the named filter and
      all its user assignments.
    - When V(absent) with O(filter_name) and O(users), removes only the
      listed users from the filter without deleting the filter itself.
    type: str
    choices: ['present', 'absent']
    default: present
  log_format:
    description:
    - The audit log output format.
    - Only applied when the audit plugin is installed.
    type: str
    choices: ['JSON', 'XML', 'CSV']
    default: JSON
  mode:
    description:
    - How the log format variable is set.
    - V(global) uses C(SET GLOBAL) which does not survive a MySQL restart
      unless also configured in C(my.cnf).
    - V(persist) uses C(SET PERSIST) (MySQL 8.0+ only) which writes the
      value to C(mysqld-auto.cnf) and survives restarts.
    type: str
    choices: ['global', 'persist']
    default: global
    version_added: '5.1.0'
  filter_name:
    description:
    - Name of the audit filter to manage.
    - When O(state=present) and O(filter_rule) is provided, creates or
      replaces the filter.
    - When O(state=present) without O(filter_rule), the filter must
      already exist; users can be assigned to it.
    - When O(state=absent), removes the filter or specific users from it
      (see O(state) for details).
    type: str
    version_added: '5.1.0'
  filter_rule:
    description:
    - A dictionary defining the audit filter rule (JSON filter document).
    - Required when creating a new filter with O(state=present).
    - Optional when assigning users to an existing filter.
    type: dict
    version_added: '5.1.0'
  users:
    description:
    - List of MySQL user accounts (in C(user@host) format) to manage.
    - Requires O(filter_name) to be set.
    - By default the module enforces exact match (replace mode). Users
      assigned to the filter but not in this list are removed.
    - Use O(append_users=true) for additive-only assignment.
    - Use O(detach_users=true) to remove listed users from the filter.
    type: list
    elements: str
    version_added: '5.1.0'
  append_users:
    description:
    - When C(true), users in O(users) are added to the filter without
      removing existing assignments (additive mode).
    - Mutually exclusive with O(detach_users).
    type: bool
    default: false
    version_added: '5.1.0'
  detach_users:
    description:
    - When C(true), users in O(users) are removed from the filter
      (subtractive mode).
    - Mutually exclusive with O(append_users).
    type: bool
    default: false
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
   - On MySQL 8.0+ the module manages the audit component.
     On MySQL 5.7 it manages the legacy audit_log plugin.
   - When O(mode=global), the log format setting does not survive a
     MySQL restart unless also set in C(my.cnf).
     Use O(mode=persist) on MySQL 8.0+ or the
     M(ansible.mysql.mysql_variables) module with C(mode=persist)
     for persistent configuration.

extends_documentation_fragment:
- ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Install the audit log plugin
  ansible.mysql.mysql_audit:
    state: present
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Set audit log format to JSON (persists across restart)
  ansible.mysql.mysql_audit:
    state: present
    log_format: JSON
    mode: persist
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

- name: Assign users to an existing filter (no rule needed)
  ansible.mysql.mysql_audit:
    state: present
    filter_name: log_all
    users:
      - app@10.0.0.%
    append_users: true
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Remove specific users from a filter
  ansible.mysql.mysql_audit:
    state: present
    filter_name: log_all
    users:
      - app@10.0.0.%
    detach_users: true
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Remove users from a filter using state absent
  ansible.mysql.mysql_audit:
    state: absent
    filter_name: log_all
    users:
      - root@localhost
    login_unix_socket: /run/mysqld/mysqld.sock

- name: Remove a filter and all its user assignments
  ansible.mysql.mysql_audit:
    state: absent
    filter_name: log_all
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
    get_server_version,
)
from ansible_collections.ansible.mysql.plugins.module_utils._version import (
    LooseVersion,
)
from ansible.module_utils.common.text.converters import to_native

executed_queries = []


def get_audit_plugin_type(cursor):
    """Return 'component', 'plugin', or None."""
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM mysql.component "
            "WHERE component_urn = 'file://component_audit_api_message_emit'"
        )
        row = cursor.fetchone()
        if row and row[0] > 0:
            return 'component'
    except Exception:
        pass

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.PLUGINS "
            "WHERE PLUGIN_NAME = 'audit_log' AND PLUGIN_STATUS = 'ACTIVE'"
        )
        row = cursor.fetchone()
        if row and row[0] > 0:
            return 'plugin'
    except Exception:
        pass

    return None


def install_audit_plugin(cursor, server_version):
    """Install the audit plugin using the appropriate method."""
    version = server_version.split('-')[0]
    if LooseVersion(version) >= LooseVersion("8.0"):
        query = "INSTALL COMPONENT 'file://component_audit_api_message_emit'"
    else:
        query = "INSTALL PLUGIN audit_log SONAME 'audit_log.so'"
    cursor.execute(query)
    executed_queries.append(query)


def uninstall_audit_plugin(cursor, plugin_type):
    """Uninstall the audit plugin based on detected install type."""
    if plugin_type == 'component':
        query = "UNINSTALL COMPONENT 'file://component_audit_api_message_emit'"
    elif plugin_type == 'plugin':
        query = "UNINSTALL PLUGIN audit_log"
    else:
        return
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


def set_audit_log_format(cursor, log_format, mode, server_version):
    """Set the audit_log_format variable."""
    if mode == 'persist':
        version = server_version.split('-')[0]
        if LooseVersion(version) < LooseVersion("8.0"):
            raise Exception(
                "mode=persist requires MySQL 8.0+, "
                "server is %s" % server_version
            )
        query = "SET PERSIST audit_log_format = %s"
    else:
        query = "SET GLOBAL audit_log_format = %s"
    cursor.execute(query, (log_format,))
    display = query.replace('%s', "'%s'" % log_format)
    executed_queries.append(display)


def set_audit_filter(cursor, filter_name, filter_rule):
    """Create or replace an audit filter."""
    rule_json = json.dumps(filter_rule)
    query = "SELECT audit_log_filter_set_filter(%s, %s)"
    cursor.execute(query, (filter_name, rule_json))
    executed_queries.append(
        "SELECT audit_log_filter_set_filter('%s', '%s')"
        % (filter_name, rule_json)
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
        "SELECT audit_log_filter_set_user('%s', '%s')"
        % (user, filter_name)
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


def get_users_for_filter(cursor, filter_name):
    """Return list of users assigned to a specific filter."""
    users = []
    try:
        cursor.execute(
            "SELECT USER FROM mysql.audit_log_user WHERE FILTERNAME = %s",
            (filter_name,)
        )
        for row in cursor.fetchall():
            users.append(row[0])
    except Exception:
        pass
    return users


def rotate_audit_log(cursor):
    """Trigger audit log rotation."""
    query = "SET GLOBAL audit_log_rotate = ON"
    cursor.execute(query)
    executed_queries.append(query)


def main():
    argument_spec = mysql_common_argument_spec()
    argument_spec.update(
        state=dict(type='str', choices=['present', 'absent'],
                   default='present'),
        log_format=dict(type='str', choices=['JSON', 'XML', 'CSV'],
                        default='JSON'),
        mode=dict(type='str', choices=['global', 'persist'],
                  default='global'),
        filter_name=dict(type='str'),
        filter_rule=dict(type='dict'),
        users=dict(type='list', elements='str'),
        append_users=dict(type='bool', default=False),
        detach_users=dict(type='bool', default=False),
        rotate=dict(type='bool', default=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[
            ('append_users', 'detach_users'),
        ],
    )

    login_user = module.params["login_user"]
    login_password = module.params["login_password"]
    connect_timeout = module.params['connect_timeout']
    ssl_cert = module.params["client_cert"]
    ssl_key = module.params["client_key"]
    ssl_ca = module.params["ca_cert"]
    check_hostname = module.params["check_hostname"]
    config_file = module.params['config_file']
    db = 'mysql'

    state = module.params['state']
    log_format = module.params['log_format']
    mode = module.params['mode']
    filter_name = module.params['filter_name']
    filter_rule = module.params['filter_rule']
    users = module.params['users']
    append_users = module.params['append_users']
    detach_users = module.params['detach_users']
    rotate = module.params['rotate']

    # Manual validation
    if users and not filter_name:
        module.fail_json(
            msg="'users' requires 'filter_name' to be set."
        )
    if (append_users or detach_users) and not users:
        module.fail_json(
            msg="'append_users' and 'detach_users' require "
                "'users' to be set."
        )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)
    else:
        warnings.filterwarnings('error', category=mysql_driver.Warning)

    try:
        cursor, db_conn = mysql_connect(
            module, login_user, login_password, config_file,
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

    server_version = get_server_version(cursor)
    changed = False

    try:
        plugin_type = get_audit_plugin_type(cursor)

        # ---- state=absent ----
        if state == 'absent':
            if filter_name and users:
                # Remove specific users from the filter
                if not module.check_mode:
                    current_filter_users = get_users_for_filter(
                        cursor, filter_name)
                    for u in users:
                        if u in current_filter_users:
                            remove_user_filter(cursor, u)
                            changed = True
                else:
                    changed = True

            elif filter_name:
                # Remove filter and all its user assignments
                existing_filters = (
                    get_existing_filters(cursor)
                    if not module.check_mode else {}
                )
                if module.check_mode or filter_name in existing_filters:
                    if not module.check_mode:
                        for u in get_users_for_filter(cursor, filter_name):
                            remove_user_filter(cursor, u)
                        remove_audit_filter(cursor, filter_name)
                    changed = True

            else:
                # Uninstall the plugin entirely
                if plugin_type is not None:
                    if not module.check_mode:
                        uninstall_audit_plugin(cursor, plugin_type)
                    changed = True

            module.exit_json(changed=changed, queries=executed_queries)

        # ---- state=present ----
        # Install plugin if needed
        if plugin_type is None:
            if not module.check_mode:
                install_audit_plugin(cursor, server_version)
            changed = True

        # Set log format
        if not module.check_mode and (plugin_type is not None or changed):
            current_format = get_audit_log_format(cursor)
            if (current_format
                    and current_format.upper() != log_format.upper()):
                set_audit_log_format(
                    cursor, log_format, mode, server_version)
                changed = True

        # Configure filter
        if filter_name:
            if filter_rule:
                # Create or update filter
                existing_filters = (
                    get_existing_filters(cursor)
                    if not module.check_mode else {}
                )
                needs_update = True
                if filter_name in existing_filters:
                    existing_rule = existing_filters[filter_name]
                    if isinstance(existing_rule, str):
                        try:
                            existing_rule = json.loads(existing_rule)
                        except (ValueError, TypeError):
                            pass
                    if existing_rule == filter_rule:
                        needs_update = False

                if needs_update:
                    if not module.check_mode:
                        set_audit_filter(cursor, filter_name, filter_rule)
                    changed = True
            else:
                # Verify existing filter
                if not module.check_mode:
                    existing_filters = get_existing_filters(cursor)
                    if filter_name not in existing_filters:
                        module.fail_json(
                            msg="Filter '%s' does not exist. Provide "
                                "'filter_rule' to create it."
                                % filter_name
                        )

        # Manage user assignments
        if users and filter_name:
            if not module.check_mode:
                current_assignments = get_user_filter_assignments(cursor)
                current_filter_users = get_users_for_filter(
                    cursor, filter_name)

                if detach_users:
                    for u in users:
                        if u in current_filter_users:
                            remove_user_filter(cursor, u)
                            changed = True

                elif append_users:
                    for u in users:
                        if current_assignments.get(u) != filter_name:
                            set_user_filter(cursor, u, filter_name)
                            changed = True

                else:
                    # Replace mode: enforce exact match
                    for u in users:
                        if current_assignments.get(u) != filter_name:
                            set_user_filter(cursor, u, filter_name)
                            changed = True
                    for u in current_filter_users:
                        if u not in users:
                            remove_user_filter(cursor, u)
                            changed = True
            else:
                changed = True

        # Rotate log
        if rotate:
            if not module.check_mode:
                rotate_audit_log(cursor)
            changed = True

    except Exception as e:
        module.fail_json(
            msg="Error managing audit plugin: %s" % to_native(e))

    module.exit_json(changed=changed, queries=executed_queries)


if __name__ == '__main__':
    main()
