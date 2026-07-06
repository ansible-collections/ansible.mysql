#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mysql_replication_filter

short_description: Manage MySQL or MariaDB replication filters

description:
  - Manage replica-side replication filters declaratively.
  - MySQL uses C(CHANGE REPLICATION FILTER).
  - MariaDB uses C(SET GLOBAL replicate_*) variables.
  - Changes are runtime only and are not persisted across restart by this module.
  - Persist filter settings separately through server configuration if they must survive a restart.

author:
  - Ron Gershburg (@ronger4)

version_added: '5.2.0'

options:
  replicate_do_db:
    description:
      - Databases that should be replicated.
      - Provide an empty list to clear the filter.
    type: list
    elements: str
  replicate_ignore_db:
    description:
      - Databases that should be ignored during replication.
      - Provide an empty list to clear the filter.
    type: list
    elements: str
  replicate_do_table:
    description:
      - Fully qualified tables that should be replicated.
      - Values must use C(database.table) syntax.
      - Provide an empty list to clear the filter.
    type: list
    elements: str
  replicate_ignore_table:
    description:
      - Fully qualified tables that should be ignored during replication.
      - Values must use C(database.table) syntax.
      - Provide an empty list to clear the filter.
    type: list
    elements: str
  replicate_wild_do_table:
    description:
      - Wildcard table patterns that should be replicated.
      - Values must use C(database.table) syntax with C(%) and C(_) wildcards.
      - Provide an empty list to clear the filter.
    type: list
    elements: str
  replicate_wild_ignore_table:
    description:
      - Wildcard table patterns that should be ignored during replication.
      - Values must use C(database.table) syntax with C(%) and C(_) wildcards.
      - Provide an empty list to clear the filter.
    type: list
    elements: str
  channel:
    description:
      - MySQL replication channel name.
      - Supported only for MySQL.
    type: str
  connection_name:
    description:
      - MariaDB replication connection name.
      - Supported only for MariaDB multi-source replication.
    type: str

notes:
  - Compatible with MariaDB or MySQL.
  - At least one replication filter option must be provided.
  - Unspecified filters are left unchanged.

attributes:
  check_mode:
    support: full
  idempotent:
    support: full

extends_documentation_fragment:
  - ansible.mysql.mysql
'''

EXAMPLES = r'''
- name: Ignore one database on a MySQL replica
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    replicate_ignore_db:
      - audit

- name: Replicate selected tables on a MySQL replica
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    replicate_do_table:
      - app.orders
      - reporting.summary

- name: Set wildcard filters on a MySQL replica
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    replicate_wild_do_table:
      - app.%
      - reporting.sales_%
    replicate_wild_ignore_table:
      - archive.old_%
      - tmp.%

- name: Set multiple MySQL filters in one task
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    replicate_do_db:
      - app
    replicate_ignore_table:
      - archive.events

- name: Set one channel-specific MySQL filter
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    channel: analytics
    replicate_do_db:
      - reporting

- name: Set one named MariaDB replication filter
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    connection_name: analytics
    replicate_do_db:
      - reporting

- name: Clear one MariaDB wildcard filter
  ansible.mysql.mysql_replication_filter:
    login_unix_socket: /run/mysqld/mysqld.sock
    replicate_wild_ignore_table: []
'''

RETURN = r'''
queries:
  description: Executed SQL statements or predicted SQL statements in check mode.
  returned: always
  type: list
  elements: str
  sample:
    - CHANGE REPLICATION FILTER REPLICATE_DO_DB = (`app`,`reporting`)
filters:
  description: Effective normalized filter state after execution or prediction.
  returned: always
  type: dict
  contains:
    replicate_do_db:
      description: Databases that should be replicated.
      returned: always
      type: list
      elements: str
    replicate_ignore_db:
      description: Databases that should be ignored during replication.
      returned: always
      type: list
      elements: str
    replicate_do_table:
      description: Fully qualified tables that should be replicated.
      returned: always
      type: list
      elements: str
    replicate_ignore_table:
      description: Fully qualified tables that should be ignored during replication.
      returned: always
      type: list
      elements: str
    replicate_wild_do_table:
      description: Wildcard table patterns that should be replicated.
      returned: always
      type: list
      elements: str
    replicate_wild_ignore_table:
      description: Wildcard table patterns that should be ignored during replication.
      returned: always
      type: list
      elements: str
  sample:
    replicate_do_db:
      - app
      - reporting
    replicate_ignore_db: []
    replicate_do_table: []
    replicate_ignore_table: []
    replicate_wild_do_table: []
    replicate_wild_ignore_table: []
'''

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native

from ansible_collections.ansible.mysql.plugins.module_utils.database import check_input, mysql_quote_identifier
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    get_server_implementation,
    get_server_version,
    mysql_common_argument_spec,
    mysql_connect,
    mysql_driver,
    mysql_driver_fail_msg,
)
from ansible_collections.ansible.mysql.plugins.module_utils.version import LooseVersion


FILTER_DEFINITIONS = {
    'replicate_do_db': {
        'mysql_name': 'REPLICATE_DO_DB',
        'mariadb_name': 'replicate_do_db',
        'value_kind': 'database',
    },
    'replicate_ignore_db': {
        'mysql_name': 'REPLICATE_IGNORE_DB',
        'mariadb_name': 'replicate_ignore_db',
        'value_kind': 'database',
    },
    'replicate_do_table': {
        'mysql_name': 'REPLICATE_DO_TABLE',
        'mariadb_name': 'replicate_do_table',
        'value_kind': 'table',
    },
    'replicate_ignore_table': {
        'mysql_name': 'REPLICATE_IGNORE_TABLE',
        'mariadb_name': 'replicate_ignore_table',
        'value_kind': 'table',
    },
    'replicate_wild_do_table': {
        'mysql_name': 'REPLICATE_WILD_DO_TABLE',
        'mariadb_name': 'replicate_wild_do_table',
        'value_kind': 'pattern',
    },
    'replicate_wild_ignore_table': {
        'mysql_name': 'REPLICATE_WILD_IGNORE_TABLE',
        'mariadb_name': 'replicate_wild_ignore_table',
        'value_kind': 'pattern',
    },
}

MYSQL_FILTER_NAME_TO_PARAM = dict(
    (definition['mysql_name'], param)
    for param, definition in FILTER_DEFINITIONS.items()
)


def normalize_filter_values(values):
    normalized = []

    for value in values:
        value = value.strip()
        if not value:
            continue
        normalized.append(value)

    return sorted(set(normalized))


def normalize_mysql_filter_rows(rows):
    filters = _empty_filters()

    for row in rows:
        param = MYSQL_FILTER_NAME_TO_PARAM.get(row['FILTER_NAME'])
        if not param:
            continue
        filters[param] = normalize_filter_values(_split_filter_rule(row.get('FILTER_RULE', '')))

    return filters


def normalize_mariadb_filter_values(variables):
    filters = _empty_filters()

    for param, definition in FILTER_DEFINITIONS.items():
        raw_value = variables.get(definition['mariadb_name'], '')
        filters[param] = normalize_filter_values(_split_filter_rule(raw_value))

    return filters


def plan_filter_changes(desired_filters, current_filters, query_builder):
    planned_filters = dict((name, list(values)) for name, values in current_filters.items())
    queries = []

    for param, desired_values in desired_filters.items():
        if desired_values is None:
            continue

        normalized_values = normalize_filter_values(desired_values)
        planned_filters[param] = normalized_values

        if current_filters.get(param, []) != normalized_values:
            queries.append(query_builder(param, normalized_values))

    return {
        'changed': bool(queries),
        'queries': queries,
        'filters': planned_filters,
    }


def build_mysql_filter_query(filter_name, value_kind, values, channel=''):
    values_sql = _build_mysql_filter_values(value_kind, values)
    query = 'CHANGE REPLICATION FILTER %s = (%s)' % (filter_name, values_sql)

    if channel:
        query += ' FOR CHANNEL %s' % _quote_sql_string(channel)

    return {
        'sql': query,
        'params': (),
        'display': query,
    }


def build_mariadb_set_query(variable_name, values):
    value = ','.join(normalize_filter_values(values))
    identifier = mysql_quote_identifier(variable_name, 'vars')
    query = 'SET GLOBAL %s = %%s' % identifier

    return {
        'sql': query,
        'params': (value,),
        'display': 'SET GLOBAL %s = %s' % (identifier, _quote_sql_string(value)),
    }


def build_mysql_query_from_param(param, values, channel=''):
    definition = FILTER_DEFINITIONS[param]
    return build_mysql_filter_query(
        definition['mysql_name'],
        definition['value_kind'],
        values,
        channel=channel,
    )


def build_mariadb_query_from_param(param, values):
    definition = FILTER_DEFINITIONS[param]
    return build_mariadb_set_query(definition['mariadb_name'], values)


def _empty_filters():
    return dict((name, []) for name in FILTER_DEFINITIONS)


def _split_filter_rule(value):
    if not value:
        return []

    return [item.strip() for item in value.split(',')]


def _build_mysql_filter_values(value_kind, values):
    normalized = normalize_filter_values(values)
    if not normalized:
        return ''

    if value_kind == 'pattern':
        return ','.join(_quote_sql_string(value) for value in normalized)

    return ','.join(mysql_quote_identifier(value, value_kind) for value in normalized)


def _quote_sql_string(value):
    return "'%s'" % value.replace('\\', '\\\\').replace("'", "''")


def _uses_database_table_syntax(value):
    database_name, separator, table_name = value.partition('.')
    return bool(separator and database_name and table_name and '.' not in table_name)


def get_mysql_filter_rows(cursor, channel=''):
    if channel:
        cursor.execute(
            'SELECT CHANNEL_NAME, FILTER_NAME, FILTER_RULE '
            'FROM performance_schema.replication_applier_filters WHERE CHANNEL_NAME = %s',
            (channel,),
        )
    else:
        cursor.execute(
            'SELECT FILTER_NAME, FILTER_RULE FROM performance_schema.replication_applier_global_filters'
        )

    return cursor.fetchall()


def supports_mariadb_connection_name(server_version):
    return LooseVersion(server_version) >= LooseVersion('10.0.1')


def get_mariadb_filter_values(module, cursor, server_version, connection_name=''):
    if connection_name and not supports_mariadb_connection_name(server_version):
        module.fail_json(msg='connection_name requires MariaDB 10.0.1 or newer')

    if connection_name:
        replica_term = 'REPLICA' if LooseVersion(server_version) >= LooseVersion('10.5.1') else 'SLAVE'
        cursor.execute('SHOW %s %s STATUS' % (replica_term, _quote_sql_string(connection_name)))
        rows = cursor.fetchall()
        if rows:
            row = rows[0]
            return {
                'replicate_do_db': row.get('Replicate_Do_DB', ''),
                'replicate_ignore_db': row.get('Replicate_Ignore_DB', ''),
                'replicate_do_table': row.get('Replicate_Do_Table', ''),
                'replicate_ignore_table': row.get('Replicate_Ignore_Table', ''),
                'replicate_wild_do_table': row.get('Replicate_Wild_Do_Table', ''),
                'replicate_wild_ignore_table': row.get('Replicate_Wild_Ignore_Table', ''),
            }
        return dict((param, '') for param in FILTER_DEFINITIONS)

    variables = {}
    for definition in FILTER_DEFINITIONS.values():
        variable_name = definition['mariadb_name']
        cursor.execute('SELECT @@GLOBAL.%s AS Value' % variable_name)
        rows = cursor.fetchall()
        variables[variable_name] = _extract_variable_value(rows)

    return variables


def _extract_variable_value(rows):
    if not rows:
        return ''

    row = rows[0]
    if isinstance(row, dict):
        return row.get('Value', row.get('VALUE', ''))

    if len(row) == 1:
        return row[0]

    return row[1]


class MySQLReplicationFilter(object):
    def __init__(self, module, cursor, server_implementation, server_version):
        self.module = module
        self.cursor = cursor
        self.server_implementation = server_implementation
        self.server_version = server_version

    def apply(self, desired_filters, channel='', connection_name=''):
        self.validate_filters(desired_filters)
        self.validate_target(channel, connection_name)

        if self.server_implementation == 'mysql':
            def build_query(param, values):
                return build_mysql_query_from_param(param, values, channel=channel)

            planned = plan_filter_changes(
                desired_filters,
                normalize_mysql_filter_rows(get_mysql_filter_rows(self.cursor, channel=channel)),
                build_query,
            )
        elif self.server_implementation == 'mariadb':
            planned = plan_filter_changes(
                desired_filters,
                normalize_mariadb_filter_values(get_mariadb_filter_values(
                    self.module,
                    self.cursor,
                    self.server_version,
                    connection_name=connection_name,
                )),
                build_mariadb_query_from_param,
            )
        else:
            self.module.fail_json(
                msg='mysql_replication_filter supports only MySQL or MariaDB, got "%s"' % self.server_implementation
            )

        if not self.module.check_mode:
            self.execute_queries(planned['queries'], connection_name=connection_name)

        return {
            'changed': planned['changed'],
            'queries': [query['display'] for query in planned['queries']],
            'filters': planned['filters'],
        }

    def execute_queries(self, queries, connection_name=''):
        if self.server_implementation == 'mariadb' and connection_name:
            self.cursor.execute('SET @@default_master_connection = %s', (connection_name,))
            self.cursor.fetchall()

        try:
            for query in queries:
                if query['params']:
                    self.cursor.execute(query['sql'], query['params'])
                else:
                    self.cursor.execute(query['sql'])
                self.cursor.fetchall()
        finally:
            if self.server_implementation == 'mariadb' and connection_name:
                self.cursor.execute('SET @@default_master_connection = %s', ('',))
                self.cursor.fetchall()

    def validate_filters(self, desired_filters):
        for param, values in desired_filters.items():
            if values is None:
                continue
            check_input(self.module, values)
            values_with_commas = [value for value in values if ',' in value]
            if values_with_commas:
                self.module.fail_json(
                    msg='replication filter values cannot contain commas: %s' % ', '.join(values_with_commas)
                )
            if FILTER_DEFINITIONS[param]['value_kind'] in ('table', 'pattern'):
                invalid_values = [value for value in values if not _uses_database_table_syntax(value)]
                if invalid_values:
                    self.module.fail_json(
                        msg='%s values must use database.table syntax: %s' % (param, ', '.join(invalid_values))
                    )

    def validate_target(self, channel, connection_name):
        check_input(self.module, channel, connection_name)

        if self.server_implementation == 'mysql' and connection_name:
            self.module.fail_json(msg='connection_name is supported only for MariaDB')

        if self.server_implementation == 'mariadb' and channel:
            self.module.fail_json(msg='channel is supported only for MySQL')


def main():
    argument_spec = mysql_common_argument_spec()
    for name in FILTER_DEFINITIONS:
        argument_spec[name] = dict(type='list', elements='str')

    argument_spec.update(
        channel=dict(type='str'),
        connection_name=dict(type='str'),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=[['channel', 'connection_name']],
        supports_check_mode=True,
    )

    if mysql_driver is None:
        module.fail_json(msg=mysql_driver_fail_msg)

    desired_filters = dict((name, module.params[name]) for name in FILTER_DEFINITIONS)
    if not any(values is not None for values in desired_filters.values()):
        module.fail_json(msg='at least one replication filter option must be provided')

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
            None,
            cursor_class='DictCursor',
            connect_timeout=connect_timeout,
            check_hostname=check_hostname,
        )
    except Exception as e:
        module.fail_json(
            msg=(
                "unable to connect to database, check login_user and "
                "login_password are correct or %s has the credentials. "
                "Exception message: %s" % (config_file, to_native(e))
            )
        )

    executor = MySQLReplicationFilter(
        module,
        cursor,
        get_server_implementation(cursor),
        get_server_version(cursor),
    )

    try:
        module.exit_json(
            **executor.apply(
                desired_filters,
                channel=module.params['channel'],
                connection_name=module.params['connection_name'],
            )
        )
    except ValueError as e:
        module.fail_json(msg='invalid replication filter request: %s' % to_native(e))


if __name__ == '__main__':
    main()
