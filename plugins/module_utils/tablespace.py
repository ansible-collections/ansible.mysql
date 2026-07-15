# This code is part of Ansible, but is an independent component.
# This particular file snippet, and this file snippet only, is BSD licensed.
# Modules you write using this snippet, which is embedded dynamically by Ansible
# still belong to the author of the module, and may assign their own license
# to the complete work.
#
# Simplified BSD License (see simplified_bsd.txt or https://opensource.org/licenses/BSD-2-Clause)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.module_utils.common.text.converters import to_native
from ansible_collections.ansible.mysql.plugins.module_utils.mysql import (
    get_server_implementation,
    get_server_version,
)


MYSQL_TABLESPACES_MIN_VERSION = (5, 7, 6)
MYSQL_TABLESPACE_ENCRYPTION_MIN_VERSION = (8, 0, 13)
MYSQL_TABLESPACE_STATE_MIN_VERSION = (8, 0, 14)
MYSQL_80_METADATA_FAMILY_MIN_VERSION = (8, 0, 0)


def get_server_version_tuple(cursor):
    version = get_server_version(cursor).split('-', 1)[0]
    version_tuple = []

    for part in version.split('.'):
        digits = ''.join(char for char in part if char.isdigit())
        if not digits:
            break
        version_tuple.append(int(digits))

    while len(version_tuple) < 3:
        version_tuple.append(0)

    return tuple(version_tuple[:3])


def ensure_tablespaces_supported(module, cursor):
    if get_server_implementation(module, cursor) != 'mysql':
        module.fail_json(msg='Tablespace operations are supported only by MySQL.')

    server_version = get_server_version_tuple(cursor)
    if server_version < MYSQL_TABLESPACES_MIN_VERSION:
        module.fail_json(
            msg='Tablespace operations require MySQL %s or later.'
            % _format_version(MYSQL_TABLESPACES_MIN_VERSION)
        )

    return server_version


def get_mysql_tablespaces(cursor, server_version, name=None, module=None):
    if server_version < MYSQL_80_METADATA_FAMILY_MIN_VERSION:
        query = _get_mysql_57_tablespaces_query()
    else:
        query = _get_mysql_80_tablespaces_query(server_version)

    params = None
    if name is not None:
        query += ' AND f.TABLESPACE_NAME = %s'
        params = (name,)

    query += _get_mysql_tablespaces_group_by(server_version)
    return _fetch_normalized_rows(cursor, query, params, module=module)


def get_mysql_tablespace(cursor, server_version, name, module=None):
    tablespaces = get_mysql_tablespaces(cursor, server_version, name=name, module=module)
    if not tablespaces:
        return None
    return tablespaces[0]


def _normalize_mysql_tablespace_row(row):
    return {
        'server_implementation': 'mysql',
        'name': row['TABLESPACE_NAME'],
        'space_id': _to_int_or_none(row.get('FILE_ID')),
        'engine': row['ENGINE'],
        'file_type': row.get('FILE_TYPE'),
        'extent_size': _to_int_or_none(row.get('EXTENT_SIZE')),
        'autoextend_size': _to_int_or_none(row.get('AUTOEXTEND_SIZE')),
        'maximum_size': _to_int_or_none(row.get('MAXIMUM_SIZE')),
        'datafile': row.get('FILE_NAME'),
        'filesystem_block_size': _to_int_or_none(row.get('FS_BLOCK_SIZE')),
        'status': row.get('STATUS'),
        'comment': row.get('EXTRA'),
        'page_size': _to_int_or_none(row.get('PAGE_SIZE')),
        'file_size': _to_int_or_none(row.get('FILE_SIZE')),
        'allocated_size': _to_int_or_none(row.get('ALLOCATED_SIZE')),
        'zip_page_size': _to_int_or_none(row.get('ZIP_PAGE_SIZE')),
        'space_type': row.get('SPACE_TYPE'),
        'state': row.get('STATE'),
        'encryption': row.get('ENCRYPTION'),
        'attached_tables': _to_list_or_empty(row.get('ATTACHED_TABLES')),
    }


def _fetch_normalized_rows(cursor, query, params, module=None):
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
    except Exception as e:
        if module is not None:
            module.fail_json(msg="Cannot execute SQL '%s': %s" % (query, to_native(e)))
        raise

    return [
        _normalize_mysql_tablespace_row(row)
        for row in rows
    ]


def _get_mysql_57_tablespaces_query():
    return (
        'SELECT f.FILE_ID, f.TABLESPACE_NAME, COALESCE(df.PATH, f.FILE_NAME) AS FILE_NAME, '
        'f.FILE_TYPE, f.ENGINE, f.EXTENT_SIZE, f.AUTOEXTEND_SIZE, f.MAXIMUM_SIZE, '
        'f.STATUS, f.EXTRA, ts.FS_BLOCK_SIZE, ts.FILE_SIZE, ts.ALLOCATED_SIZE, '
        'ts.PAGE_SIZE, ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, '
        "NULL AS ENCRYPTION, NULL AS STATE, GROUP_CONCAT(t.NAME ORDER BY t.NAME SEPARATOR ',') "
        'AS ATTACHED_TABLES '
        'FROM INFORMATION_SCHEMA.FILES AS f '
        'LEFT JOIN INFORMATION_SCHEMA.INNODB_SYS_TABLESPACES AS ts ON ts.SPACE = f.FILE_ID '
        'LEFT JOIN INFORMATION_SCHEMA.INNODB_SYS_DATAFILES AS df ON df.SPACE = ts.SPACE '
        'LEFT JOIN INFORMATION_SCHEMA.INNODB_SYS_TABLES AS t ON t.SPACE = ts.SPACE '
        "WHERE f.ENGINE = 'InnoDB' AND f.FILE_TYPE = 'TABLESPACE' AND ts.SPACE_TYPE = 'General'"
    )


def _get_mysql_80_tablespaces_query(server_version):
    return (
        'SELECT f.FILE_ID, f.TABLESPACE_NAME, COALESCE(df.PATH, f.FILE_NAME) AS FILE_NAME, '
        'f.FILE_TYPE, f.ENGINE, f.EXTENT_SIZE, f.AUTOEXTEND_SIZE, f.MAXIMUM_SIZE, '
        'f.STATUS, f.EXTRA, ts.FS_BLOCK_SIZE, ts.FILE_SIZE, '
        'ts.ALLOCATED_SIZE, ts.PAGE_SIZE, '
        '%s'
        "GROUP_CONCAT(t.NAME ORDER BY t.NAME SEPARATOR ',') AS ATTACHED_TABLES "
        'FROM INFORMATION_SCHEMA.FILES AS f '
        'LEFT JOIN INFORMATION_SCHEMA.INNODB_TABLESPACES AS ts ON ts.SPACE = f.FILE_ID '
        'LEFT JOIN INFORMATION_SCHEMA.INNODB_DATAFILES AS df ON df.SPACE = ts.SPACE '
        'LEFT JOIN INFORMATION_SCHEMA.INNODB_TABLES AS t ON t.SPACE = ts.SPACE '
        "WHERE f.ENGINE = 'InnoDB' AND f.FILE_TYPE = 'TABLESPACE' AND ts.SPACE_TYPE = 'General'"
    ) % _get_mysql_80_tablespaces_metadata_columns(server_version)


def _get_mysql_tablespaces_group_by(server_version):
    if server_version < MYSQL_80_METADATA_FAMILY_MIN_VERSION:
        return (
            ' GROUP BY f.FILE_ID, f.TABLESPACE_NAME, df.PATH, f.FILE_NAME, f.FILE_TYPE, '
            'f.ENGINE, f.EXTENT_SIZE, f.AUTOEXTEND_SIZE, f.MAXIMUM_SIZE, '
            'f.STATUS, f.EXTRA, ts.FS_BLOCK_SIZE, ts.FILE_SIZE, ts.ALLOCATED_SIZE, '
            'ts.PAGE_SIZE, ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE ORDER BY f.TABLESPACE_NAME'
        )

    query = (
        ' GROUP BY f.FILE_ID, f.TABLESPACE_NAME, df.PATH, f.FILE_NAME, f.FILE_TYPE, '
        'f.ENGINE, f.EXTENT_SIZE, f.AUTOEXTEND_SIZE, f.MAXIMUM_SIZE, '
        'f.STATUS, f.EXTRA, ts.FS_BLOCK_SIZE, ts.FILE_SIZE, '
        'ts.ALLOCATED_SIZE, ts.PAGE_SIZE, ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE'
    )

    if server_version >= MYSQL_TABLESPACE_ENCRYPTION_MIN_VERSION:
        query += ', ts.ENCRYPTION'

    if server_version >= MYSQL_TABLESPACE_STATE_MIN_VERSION:
        query += ', ts.STATE'

    return query + ' ORDER BY f.TABLESPACE_NAME'


def _get_mysql_80_tablespaces_metadata_columns(server_version):
    if server_version < MYSQL_TABLESPACE_ENCRYPTION_MIN_VERSION:
        return 'ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, NULL AS ENCRYPTION, NULL AS STATE, '

    if server_version < MYSQL_TABLESPACE_STATE_MIN_VERSION:
        return 'ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, ts.ENCRYPTION, NULL AS STATE, '

    return 'ts.ZIP_PAGE_SIZE, ts.SPACE_TYPE, ts.ENCRYPTION, ts.STATE, '


def _first_defined(row, *keys):
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _to_int_or_none(value):
    if value is None:
        return None
    return int(value)


def _to_list_or_empty(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [item.strip() for item in value.split(',') if item.strip()]


def _format_version(version):
    return '.'.join(str(part) for part in version)
