# Copyright 2014 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import pprint

import alembic
import alembic.autogenerate
import alembic.migration
import mock
from oslo.config import cfg
from oslo.db.sqlalchemy import test_base
from oslo.db.sqlalchemy import test_migrations
import sqlalchemy

from neutron.db.migration import cli as migration
from neutron.db.migration.models import head as head_models
from neutron.openstack.common.fixture import config

LOG = logging.getLogger(__name__)


cfg.CONF.import_opt('core_plugin', 'neutron.common.config')

CORE_PLUGIN = 'neutron.plugins.ml2.plugin.Ml2Plugin'

# These tables are still in the neutron database, but their models have moved
# to the separate advanced services repositories. We skip the migration checks
# for these tables for now. The checks will be re-instated soon in the tests
# for each separate repository.
# TODO(akamyshnikova): delete these lists when the tables are removed from
# neutron database.
EXTERNAL_VPNAAS_TABLES = ['vpnservices', 'ipsecpolicies', 'ipsecpeercidrs',
                          'ipsec_site_connections', 'cisco_csr_identifier_map',
                          'ikepolicies']

EXTERNAL_LBAAS_TABLES = ['vips', 'sessionpersistences', 'pools',
                         'healthmonitors', 'poolstatisticss', 'members',
                         'poolloadbalanceragentbindings', 'embrane_pool_port',
                         'poolmonitorassociations']

EXTERNAL_FWAAS_TABLES = ['firewall_rules', 'firewalls', 'firewall_policies']

EXTERNAL_TABLES = (EXTERNAL_FWAAS_TABLES + EXTERNAL_LBAAS_TABLES +
                   EXTERNAL_VPNAAS_TABLES)

# TODO(akamyshnikova): Temporarily skip checking FKs on these tables.
TABLES_WITH_EXTERNAL_FK = ['vcns_edge_monitor_bindings',
                           'vcns_edge_pool_bindings', 'vcns_edge_vip_bindings',
                           'vcns_firewall_rule_bindings']


class _TestModelsMigrations(test_migrations.ModelsMigrationsSync):
    '''Test for checking of equality models state and migrations.

    For the opportunistic testing you need to set up a db named
    'openstack_citest' with user 'openstack_citest' and password
    'openstack_citest' on localhost.
    The test will then use that db and user/password combo to run the tests.

    For PostgreSQL on Ubuntu this can be done with the following commands::

        sudo -u postgres psql
        postgres=# create user openstack_citest with createdb login password
                  'openstack_citest';
        postgres=# create database openstack_citest with owner
                   openstack_citest;

    For MySQL on Ubuntu this can be done with the following commands::

        mysql -u root
        >create database openstack_citest;
        >grant all privileges on openstack_citest.* to
         openstack_citest@localhost identified by 'openstack_citest';

    Output is a list that contains information about differences between db and
    models. Output example::

       [('add_table',
         Table('bat', MetaData(bind=None),
               Column('info', String(), table=<bat>), schema=None)),
        ('remove_table',
         Table(u'bar', MetaData(bind=None),
               Column(u'data', VARCHAR(), table=<bar>), schema=None)),
        ('add_column',
         None,
         'foo',
         Column('data', Integer(), table=<foo>)),
        ('remove_column',
         None,
         'foo',
         Column(u'old_data', VARCHAR(), table=None)),
        [('modify_nullable',
          None,
          'foo',
          u'x',
          {'existing_server_default': None,
          'existing_type': INTEGER()},
          True,
          False)]]

    * ``remove_*`` means that there is extra table/column/constraint in db;

    * ``add_*`` means that it is missing in db;

    * ``modify_*`` means that on column in db is set wrong
      type/nullable/server_default. Element contains information:
        * what should be modified,
        * schema,
        * table,
        * column,
        * existing correct column parameters,
        * right value,
        * wrong value.

    '''

    def setUp(self):
        patch = mock.patch.dict('sys.modules', {
            'heleosapi': mock.MagicMock(),
            'midonetclient': mock.MagicMock(),
            'midonetclient.neutron': mock.MagicMock(),
        })
        patch.start()
        self.addCleanup(patch.stop)
        super(_TestModelsMigrations, self).setUp()
        self.cfg = self.useFixture(config.Config())
        self.cfg.config(core_plugin=CORE_PLUGIN)
        self.alembic_config = migration.get_alembic_config()
        self.alembic_config.neutron_config = cfg.CONF

    def db_sync(self, engine):
        cfg.CONF.set_override('connection', engine.url, group='database')
        migration.do_alembic_command(self.alembic_config, 'upgrade', 'head')
        cfg.CONF.clear_override('connection', group='database')

    def get_engine(self):
        return self.engine

    def get_metadata(self):
        return head_models.get_metadata()

    def include_object(self, object_, name, type_, reflected, compare_to):
        if type_ == 'table' and (name == 'alembic_version'
                                 or name in EXTERNAL_TABLES):
                return False

        return super(_TestModelsMigrations, self).include_object(
            object_, name, type_, reflected, compare_to)

    def test_models_sync(self):
        # drop all tables after a test run
        self.addCleanup(self._cleanup)

        # run migration scripts
        self.db_sync(self.get_engine())

        with self.get_engine().connect() as conn:
            opts = {
                'include_object': self.include_object,
                'compare_type': self.compare_type,
                'compare_server_default': self.compare_server_default,
            }
            mc = alembic.migration.MigrationContext.configure(conn, opts=opts)

            # compare schemas and fail with diff, if it's not empty
            diff1 = alembic.autogenerate.compare_metadata(mc,
                                                          self.get_metadata())
            insp = sqlalchemy.engine.reflection.Inspector.from_engine(
                self.get_engine())
            dialect = self.get_engine().dialect.name
            self.check_mysql_engine(dialect, insp)
            diff2 = self.check_foreign_keys(self.get_metadata(),
                                            self.get_engine())

        result = filter(self.remove_unrelated_errors, diff1 + diff2)
        if result:
            msg = pprint.pformat(result, indent=2, width=20)

            self.fail("Models and migration scripts aren't in sync:\n%s" % msg)

    def check_mysql_engine(self, dialect, insp):
        if dialect != 'mysql':
            return

        # Test that table creation on mysql only builds InnoDB tables
        tables = insp.get_table_names()
        self.assertTrue(len(tables) > 0,
                        "No tables found. Wrong schema?")
        noninnodb = [table for table in tables if
                     insp.get_table_options(table)['mysql_engine'] != 'InnoDB'
                     and table != 'alembic_version']
        self.assertEqual(0, len(noninnodb), "%s non InnoDB tables created" %
                                            noninnodb)

    # Remove some difference that are not mistakes just specific of
        # dialects, etc
    def remove_unrelated_errors(self, element):
        insp = sqlalchemy.engine.reflection.Inspector.from_engine(
            self.get_engine())
        dialect = self.get_engine().dialect.name
        if isinstance(element, tuple):
            if dialect == 'mysql' and element[0] == 'remove_index':
                table_name = element[1].table.name
                for fk in insp.get_foreign_keys(table_name):
                    if fk['name'] == element[1].name:
                        return False
                cols = [c.name for c in element[1].expressions]
                for col in cols:
                    if col in insp.get_pk_constraint(
                            table_name)['constrained_columns']:
                        return False
            # TODO(akamyshnikova): Remove this skip once the logic for
            # vcns_*_bindings is fixed. (Part of advanced services split.)
            elif ((element[0] == 'remove_fk'
                  and element[1].parent.name in TABLES_WITH_EXTERNAL_FK)
                  or (element[0] == 'drop_key'
                      and element[2] in TABLES_WITH_EXTERNAL_FK)):
                return False

        else:
            for modified, _, table, column, _, _, new in element:
                if modified == 'modify_default' and dialect == 'mysql':
                    constrained = insp.get_pk_constraint(table)
                    if column in constrained['constrained_columns']:
                        return False
        return True


class TestModelsMigrationsMysql(_TestModelsMigrations,
                                test_base.MySQLOpportunisticTestCase):
    pass


class TestModelsMigrationsPsql(_TestModelsMigrations,
                               test_base.PostgreSQLOpportunisticTestCase):
    pass
