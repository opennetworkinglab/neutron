# Copyright 2014 Open Networking Laboratory
# All Rights Reserved.
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

"""
Neutron Plug-in for OpenVirteX Network Virtualization Platform.
This plugin will forward authenticated REST API calls to OVX.
"""

from oslo.config import cfg

from neutron.common import constants as q_const
from neutron.common import rpc as q_rpc
from neutron.common import topics
from neutron.db import agents_db
from neutron.db import db_base_plugin_v2
from neutron.db import dhcp_rpc_base
from neutron.db import portbindings_base
from neutron.db import quota_db  # noqa
from neutron.extensions import portbindings
from neutron.openstack.common import log as logging
from neutron.openstack.common import rpc
from neutron.plugins.common import constants as svc_constants
from neutron.plugins.ovx import ovxlib
from neutron.plugins.ovx import ovxdb
from neutron.plugins.ovx.common import config
from novaclient.v1_1.client import Client as nova_client

LOG = logging.getLogger(__name__)

class OVXRpcCallbacks(dhcp_rpc_base.DhcpRpcCallbackMixin):

    RPC_API_VERSION = '1.1'

    def __init__(self, plugin):
        self.plugin = plugin

    def create_rpc_dispatcher(self):
        '''Get the rpc dispatcher for this manager.

        If a manager would like to set an rpc API version, or support more than
        one class as the target of rpc messages, override this method.
        '''
        return q_rpc.PluginRpcDispatcher([self, agents_db.AgentExtRpcCallback()])

    def update_ports(self, rpc_context, **kwargs):
        LOG.debug(_("Call from agent received"))
        port_id = kwargs.get('port_id')
        dpid = kwargs.get('dpid')
        port_number = kwargs.get('port_number')

        port_db = self.plugin.get_port(rpc_context, port_id)

        neutron_network_id = port_db['network_id']
        ovx_tenant_id = ovxdb.get_ovx_tenant_id(rpc_context.session,
                                                neutron_network_id)

        with context.session.begin(subtransactions=True):
            (ovx_vdpid, ovx_vport) = self.plugin.ovx_client.createPort(ovx_tenant_id, ovxlib.hexToLong(dpid), int(port_number))

            # Stop port if requested (port is started by default in OVX)
            if not port_db['admin_state_up']:
                self.plugin.ovx_client.stopPort(ovx_tenant_id, ovx_vdpid, ovx_vport)

            # Save mapping between Neutron port ID and OVX dpid and port number
            ovxdb.add_ovx_vport(rpc_context.session, port_db['id'], ovx_vdpid, ovx_vport)

            # TODO: add support for non-bigswitch networks
            self.plugin.ovx_client.connectHost(ovx_tenant_id, ovx_vdpid, ovx_vport, port_db['mac_address'])

            # Set port in active state
            ovxdb.set_port_status(rpc_context.session, port_db['id'], q_const.PORT_STATUS_ACTIVE)

class OVXNeutronPlugin(db_base_plugin_v2.NeutronDbPluginV2,
                       portbindings_base.PortBindingBaseMixin):

    supported_extension_aliases = ['quotas', 'binding', 'agent']

    def __init__(self):
        super(OVXNeutronPlugin, self).__init__()
        self.conf = cfg.CONF.OVX
        self.ovx_client = ovxlib.OVXClient(self.conf.host, self.conf.port,
                                           self.conf.username, self.conf.password)
        # TODO: add controller spawning
        self.p = 10000
        self.base_binding_dict = {
            portbindings.VIF_TYPE: portbindings.VIF_TYPE_OVS
        }
        portbindings_base.register_port_dict_function()

        self.setup_rpc()

        nt = nova_client('admin', '2b7e61250b87c7eaed03',
                         'admin', 'http://172.16.212.128:5000/v2.0/',
                         service_type="compute")

    def setup_rpc(self):
        # RPC support
        self.service_topics = {svc_constants.CORE: topics.PLUGIN}
        self.conn = rpc.create_connection(new=True)
        self.callbacks = OVXRpcCallbacks(self)
        self.dispatcher = self.callbacks.create_rpc_dispatcher()
        for svc_topic in self.service_topics.values():
            self.conn.create_consumer(svc_topic, self.dispatcher, fanout=False)
        # Consume from all consumers in a thread
        self.conn.consume_in_thread()

    def create_network(self, context, network):
        """Creates an OVX-based virtual network.

        The virtual network is a big switch composed out of all physical switches (this
        includes both software and hardware switches) that are connected to OVX.
        An image that is running an OpenFlow controller is spawned for the virtual network.
        """
        LOG.debug(_('Neutron OVX: create_network() called'))

        with context.session.begin(subtransactions=True):
            # Save in db
            net = super(OVXNeutronPlugin, self).create_network(context, network)

            # TODO: spawn controller
            ctrls = ['tcp:192.168.56.6:%s' % (self.p)]
            self.p += 10000
            subnet = '10.0.0.0/24'
            
            # TODO: exception handling
            try:
                ovx_tenant_id = self._do_big_switch_network(ctrls, subnet)
                # Start network if requested
                if net['admin_state_up']:
                    self.ovx_client.startNetwork(ovx_tenant_id)
            except Exception as exc:
                raise

            # Save mapping between Neutron network ID and OVX tenant ID
            ovxdb.add_ovx_tenant_id(context.session, net['id'], ovx_tenant_id)

        # Return created network
        return net

    def update_network(self, context, id, network):
        """Update values of a network.

        :param context: neutron api request context
        :param id: UUID representing the network to update.
        :param network: dictionary with keys indicating fields to update.
                        valid keys are those that have a value of True for
                        'allow_put' as listed in the
                        :obj:`RESOURCE_ATTRIBUTE_MAP` object in
                        :file:`neutron/api/v2/attributes.py`.
        """
        # requested admin state
        req_state = network['network']['admin_state_up']
        # lookup old network state
        net_db = super(OVXNeutronPlugin, self).get_network(context, id)
        db_state = net_db['admin_state_up']
        # Start or stop network as needed
        if req_state != db_state:
            ovx_tenant_id = ovxdb.get_ovx_tenant_id(context.session, id)
            if req_state:
                self.ovx_client.startNetwork(ovx_tenant_id)
            else:
                self.ovx_client.stopNetwork(ovx_tenant_id)

        # Save network to db
        return super(OVXNeutronPlugin, self).update_network(context, id, network)

    def delete_network(self, context, id):
        """Delete a network.

        :param context: neutron api request context
        :param id: UUID representing the network to delete.
        """
        LOG.debug(_("Neutron OVX: delete_network() called"))

        with context.session.begin(subtransactions=True):
            # Lookup OVX tenant ID
            ovx_tenant_id = ovxdb.get_ovx_tenant_id(context.session, id)
            self.ovx_client.removeNetwork(ovx_tenant_id)

            # Remove network from db
            super(OVXNeutronPlugin, self).delete_network(context, id)

    def create_port(self, context, port):
        """Create a port.

        Create a port, which is a connection point of a device (e.g., a VM
        NIC) to attach to a L2 neutron network.

        :param context: neutron api request context
        :param port: dictionary describing the port, with keys as listed in the
                     :obj:`RESOURCE_ATTRIBUTE_MAP` object in
                     :file:`neutron/api/v2/attributes.py`.  All keys will be
                     populated.
        """
        LOG.debug(_("Neutron OVX: create_port() called"))

        with context.session.begin(subtransactions=True):
            # Set port status as 'DOWN' - will be updated by agent
            port['port']['status'] = q_const.PORT_STATUS_DOWN
            
            # Plugin DB - Port Create and Return port
            neutron_port = super(OVXNeutronPlugin, self).create_port(context, port)
            self._process_portbindings_create_and_update(context, port['port'], neutron_port)

            # Can't create the port in OVX yet, we need the dpid & port
            # Wait for agent to tell us
            
        # Plugin DB - Port Create and Return port
        return neutron_port

    def update_port(self, context, id, port):
        """Update values of a port.

        :param context: neutron api request context
        :param id: UUID representing the port to update.
        :param port: dictionary with keys indicating fields to update.
                     valid keys are those that have a value of True for
                     'allow_put' as listed in the :obj:`RESOURCE_ATTRIBUTE_MAP`
                     object in :file:`neutron/api/v2/attributes.py`.
        """
        # TODO: log error when trying to change network_id or mac_address
        # requested admin state
        req_state = port['port']['admin_state_up']
        # lookup old port state
        port_db = super(OVXNeutronPlugin, self).get_port(context, id)
        db_state = port_db['admin_state_up']
        # Start or stop port as needed
        if req_state != db_state:
            ovx_tenant_id = ovxdb.get_ovx_tenant_id(context.session, port_db['network_id'])
            (ovx_vdpid, ovx_vport) = ovxdb.get_ovx_vport(context.session, id)
            if req_state:
                self.ovx_client.startPort(ovx_tenant_id, ovx_vdpid, ovx_vport)
            else:
                self.ovx_client.stopPort(ovx_tenant_id, ovx_vdpid, ovx_vport)

        # Save port to db
        neutron_port = super(OVXNeutronPlugin, self).update_port(context, id, port)

        self._process_portbindings_create_and_update(context, port['port'], neutron_port)

        return neutron_port
    
    def delete_port(self, context, id):
        """Delete a port.

        :param context: neutron api request context
        :param id: UUID representing the port to delete.
        """
        LOG.debug(_("Neutron OVX: delete_port() called"))

        with context.session.begin(subtransactions=True):
            # Lookup OVX tenant ID and virtual port number to remove port
            neutron_network_id = super(OVXNeutronPlugin, self).get_port(context, id)['network_id']
            ovx_tenant_id = ovxdb.get_ovx_tenant_id(context.session, neutron_network_id)
            (ovx_vdpid, ovx_vport) = ovxdb.get_ovx_vport(context.session, id)
            try:
                self.ovx_client.removePort(ovx_tenant_id, ovx_vdpid, ovx_vport)
            except Exception as e:
                LOG.warn(_("Neutron OVX: delete vport failed: %s"), e)

            # Remove network from db
            super(OVXNeutronPlugin, self).delete_port(context, id)

    def create_subnet(self, context, subnet):
        LOG.debug(_("Neutron OVX: create_subnet() called"))

        with context.session.begin(subtransactions=True):
            # Plugin DB - Subnet Create
            net_db = super(OVXNeutronPlugin, self).get_network(
                context, subnet['subnet']['network_id'], fields=None)
            
            sub_db = super(OVXNeutronPlugin, self).create_subnet(context, subnet)

        return sub_db

    def _do_big_switch_network(self, ctrls, subnet, routing='spf', num_backup=1):
        """Create virtual network in OVX that is a single big switch.

        If any steps faill during network creation, no virtual network will be created."""
        
        # Split subnet in network address and netmask
        (net_address, net_mask) = subnet.split('/')

        # Request physical topology and create virtual network
        try:
            phy_topo = self.ovx_client.getPhysicalTopology()
            tenant_id = self.ovx_client.createNetwork(ctrls, net_address, int(net_mask))
        except Exception:
            raise

        # Fail if there are no physical switches
        switches = phy_topo.get('switches')
        if switches == None:
            raise Exception("Cannot create virtual network without physical switches")

        # Create big switch, remote virtual network if something went wrong
        try:
            # create virtual switch with all physical dpids
            dpids = [ovxlib.hexToLong(dpid) for dpid in switches]
            vdpid = self.ovx_client.createSwitch(tenant_id, dpids)
            # set routing algorithm and number of backups
            if (len(dpids) > 1):
                self.ovx_client.setInternalRouting(tenant_id, vdpid, routing, num_backup)
        except Exception:
            self.ovx_client.removeNetwork(tenant_id)
            raise

        return tenant_id
