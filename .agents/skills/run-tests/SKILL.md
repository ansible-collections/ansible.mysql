---
name: run-tests
description: Runs and writes tests (sanity, unit, integration) for the ansible.mysql Ansible collection using ansible-test. Use when asked to run, check, or write tests for a module or utility. Do not use for PR reviews or questions unrelated to testing.
---

# Skill: run-tests

## Purpose

Run and write tests for the `ansible.mysql` Ansible collection. Covers sanity, unit, and integration tests using `ansible-test`.

## When to Invoke

TRIGGER when:
- A user asks to run tests, check tests, or verify changes with tests
- A user asks how to test a module or utility
- A user asks to write tests for new or modified code

DO NOT TRIGGER when:
- Reviewing a PR for overall quality (use `.agents/skills/pr-review/SKILL.md` instead)
- The question is about module logic unrelated to testing

## Test Infrastructure

All tests run inside Docker/Podman via `ansible-test --docker`. No local package installation is needed. The collection must be installed at `ansible_collections/ansible/mysql/` (relative to a directory on `ANSIBLE_COLLECTIONS_PATHS`) for imports to resolve correctly.

---

## Test Commands

### Sanity

Checks style, documentation, and imports for a changed file:

```bash
ansible-test sanity plugins/modules/mysql_db.py --docker -vvv
```

### Unit

Runs unit tests for changed files:

```bash
ansible-test units tests/unit/plugins/modules/test_mysql_info.py --docker -vvv
ansible-test units tests/unit/plugins/module_utils/test_mysql.py --docker -vvv
```

Unit tests live under `tests/unit/plugins/` and use the **PyTest** framework. Every new function or class method MUST have a corresponding unit test.

### Integration

Runs integration tests against a live MySQL/MariaDB instance (started by Docker):

```bash
ansible-test integration test_mysql_db --docker default -vvv
ansible-test integration test_mysql_user --docker default -vvv
```

Integration tests live under `tests/integration/targets/<module_name>/`. Each target declares `setup_controller` as a dependency in `tests/integration/targets/<name>/meta/main.yml` — this target installs Python dependencies and configures the test environment.

### Integration via Makefile

The project provides a Makefile (documented in `TESTING.md`) that handles spinning up a primary database and two replicas in Podman containers. This is the recommended way to run integration tests locally:

```bash
# Run all targets against MySQL 8.4.9 with pymysql 1.1.1
make ansible="stable-2.17" db_engine_name="mysql" db_engine_version="8.4.9" connector_name="pymysql" connector_version="1.1.1"

# Run a single target
make ansible="stable-2.17" db_engine_name="mysql" db_engine_version="8.4.9" connector_name="pymysql" connector_version="1.1.1" target="test_mysql_info"

# MariaDB example
make ansible="stable-2.17" db_engine_name="mariadb" db_engine_version="11.8.7" connector_name="pymysql" connector_version="1.1.1"
```

Key Makefile options: `db_engine_name` (mysql/mariadb), `db_engine_version`, `connector_name` (pymysql), `connector_version`, `target` (single test target), `keep_containers_alive=1` (for debugging), `continue_on_errors=1`. See `TESTING.md` for the full list of supported versions and options.

---

## When Tests Are Required

| Change type | Sanity | Unit | Integration |
|---|---|---|---|
| New module | yes | yes | yes |
| New parameter | yes | if logic changed | yes |
| Bug fix | yes | yes | yes |
| Refactoring | yes | yes | no |
| Documentation only | yes | no | no |

---

## Integration Test Pattern

Every integration test target must follow this sequence:

1. Call the module under test → `register: result`
2. Assert on `result` using `ansible.builtin.assert`
3. Verify the resulting database state by querying via `ansible.mysql.mysql_query` → `register: result` → `ansible.builtin.assert`
4. This must be done in `check_mode: true` as well

```yaml
- name: Create database in check mode
  check_mode: true
  ansible.mysql.mysql_db:
    name: testdb
    state: present
  register: result

- name: Assert changed
  ansible.builtin.assert:
    that:
      - result is changed

- name: Verify DB does not exist yet
  ansible.mysql.mysql_query:
    query: "SHOW DATABASES LIKE 'testdb'"
  register: result

- name: Assert DB is not present
  ansible.builtin.assert:
    that:
      - result.query_result[0] | length == 0

- name: Create database in real mode
  ansible.mysql.mysql_db:
    name: testdb
    state: present
  register: result

- name: Assert changed
  ansible.builtin.assert:
    that:
      - result is changed

- name: Verify DB exists
  ansible.mysql.mysql_query:
    query: "SHOW DATABASES LIKE 'testdb'"
  register: result

- name: Assert DB is present
  ansible.builtin.assert:
    that:
      - result.query_result[0] | length == 1
```

Tests must also cover:
- **Idempotency**: run the same task a second time and assert `result is not changed`.
- **`state: absent`**: where applicable, remove the resource and assert it is gone.
