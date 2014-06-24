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

from neutron.common import constants as n_const
from neutron.common import rpc as q_rpc
from neutron.common import topics
from neutron.db import agents_db
from neutron.db import db_base_plugin_v2
from neutron.db import portbindings_base
from neutron.db import quota_db  # noqa
from neutron.extensions import portbindings
from neutron.openstack.common import log as logging
from neutron.openstack.common import rpc
from neutron.plugins.common import constants as svc_constants
from neutron.plugins.ovx import ovxlib
from neutron.plugins.ovx import ovxdb
from neutron.plugins.ovx.common import config

LOG = logging.getLogger(__name__)

class OVSRpcCallbacks():

    def create_rpc_dispatcher(self):
        '''Get the rpc dispatcher for this manager.

        If a manager would like to set an rpc API version, or support more than
        one class as the target of rpc messages, override this method.
        '''
        return q_rpc.PluginRpcDispatcher([self, agents_db.AgentExtRpcCallback()])

    @classmethod
    def get_port_from_device(cls, device):
        # TODO!!
        port = ovs_db_v2.get_port_from_device(device)
        if port:
            port['device'] = device
        return port

    def update_device_up(self, rpc_context, **kwargs):
        """Device is up on agent."""
        LOG.debug(_("Call from agent received"))
        
        # neutron_network_id = neutron_port['network_id']
        # ovx_tenant_id = ovxdb.get_ovx_tenant_id(context.session, neutron_network_id)

        # # TODO: if nova is calling us: wait for agent, else assume the device_id contains the dpid & port
        # # based on nuage plugin
        # dpid = None
        # port_number = None
        # port_prefix = 'compute:'
        # if neutron_port['device_owner'].startswith(port_prefix):
        #     # This request is coming from nova
        #     dpid = '00:00:00:00:00:00:02:00'
        #     port_number = 4
        # else:
        #     # TODO: fail if no device_id given
        #     # assuming device_id is of form DPID/PORT_NUMBER
        #     (dpid, port_number) = neutron_port['device_id'].split("/")

        # (ovx_vdpid, ovx_vport) = self.ovx_client.createPort(ovx_tenant_id, ovxlib.hexToLong(dpid), int(port_number))
         
        # # Stop port if requested (port is started by default in OVX)
        # if not neutron_port['admin_state_up']:
        #     self.ovx_client.stopPort(ovx_tenant_id, ovx_vdpid, ovx_vport)

        # # Save mapping between Neutron network ID and OVX tenant ID
        # ovxdb.add_ovx_port_number(context.session, neutron_port['id'], ovx_vport)

        # # TODO: add support for non-bigswitch networks
        # self.ovx_client.connectHost(ovx_tenant_id, ovx_vdpid, ovx_vport,  neutron_port['mac_address'])
        

class OVXNeutronPlugin(db_base_plugin_v2.NeutronDbPluginV2,
                       portbindings_base.PortBindingBaseMixin):

    supported_extension_aliases = ['quotas', 'binding']

    def __init__(self):
        super(OVXNeutronPlugin, self).__init__()
        self.conf = cfg.CONF.OVX
        self.ovx_client = ovxlib.OVXClient(self.conf.host, self.conf.port, self.conf.username, self.conf.password)
        # TODO: add controller spawning
        self.p = 10000
        self.base_binding_dict = {
            portbindings.VIF_TYPE: portbindings.VIF_TYPE_OVS
            # portbindings.VIF_DETAILS: {
            #     # TODO(rkukura): Replace with new VIF security details
            #     portbindings.CAP_PORT_FILTER:
            #     'security-group' in self.supported_extension_aliases,
            #     portbindings.OVS_HYBRID_PLUG: True
            # }
        }
        portbindings_base.register_port_dict_function()

        self.setup_rpc()

    def setup_rpc(self):
        # RPC support
        self.service_topics = {svc_constants.CORE: topics.PLUGIN}
        self.conn = rpc.create_connection(new=True)
        self.callbacks = OVXRpcCallbacks()
        self.dispatcher = self.callbacks.create_rpc_dispatcher()
        for svc_topic in self.service_topics.values():
            self.conn.create_consumer(svc_topic, self.dispatcher, fanout=False)
        # Consume from all consumers in a thread
        self.conn.consume_in_thread()

    def create_subnet(self, context, subnet):
        LOG.debug(_("Neutron OVX: create_subnet() called"))

        with context.session.begin(subtransactions=True):
            # Plugin DB - Subnet Create
            net_db = super(OVXNeutronPlugin, self).get_network(
                context, subnet['subnet']['network_id'], fields=None)
            
            # # Reserve the last IP address for the gateway
            # # if it is not defined
            # s = subnet['subnet']
            # ipnet = netaddr.IPNetwork(s['cidr'])
            # if s['gateway_ip'] is attributes.ATTR_NOT_SPECIFIED:
            #     gw_ip = str(netaddr.IPAddress(ipnet.last - 1))
            #     subnet['subnet']['gateway_ip'] = gw_ip

            sub_db = super(OVXNeutronPlugin, self).create_subnet(context, subnet)

        return sub_db

    def create_network(self, context, network):
        """Create a network.

        Create a network, which represents an L2 network segment which
        can have a set of subnets and ports associated with it.

        :param context: neutron api request context
        :param network: dictionary describing the network, with keys
                        as listed in the  :obj:`RESOURCE_ATTRIBUTE_MAP` object
                        in :file:`neutron/api/v2/attributes.py`.  All keys will
                        be populated.

        """
        LOG.debug(_('Neutron OVX: create_network() called'))

        # Plugin DB - Network Create and validation
        with context.session.begin(subtransactions=True):
            # Save in db
            net = super(OVXNeutronPlugin, self).create_network(context, network)

            # TODO: spawn controller
            # TODO: parametrize
            ctrls = ['tcp:192.168.56.6:%s' % (self.p)]
            self.p += 10000
            subnet = '10.0.0.0/24'
            routing = 'spf'
            num_backup = 1
            
            # TODO: exception handling
            ovx_tenant_id = self._do_big_switch_network(ctrls, subnet, routing, num_backup)

            # Start network if requested
            if net['admin_state_up']:
                self.ovx_client.startNetwork(ovx_tenant_id)

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
            port['port']['status'] = n_const.PORT_STATUS_DOWN
            
            # Plugin DB - Port Create and Return port
            neutron_port = super(OVXNeutronPlugin, self).create_port(context, port)
            self._process_portbindings_create_and_update(context, port['port'], neutron_port)

            # Can't create the port in OVX yet, we need the dpid & port
            # Wait for agent to tell us
            
        # Plugin DB - Port Create and Return port
        print 'NEUTRON_PORT', neutron_port
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
            ovx_port_number = ovxdb.get_ovx_port_number(context.session, id)
            if req_state:
                self.ovx_client.startPort(ovx_tenant_id, config.VDPID, ovx_port_number)
            else:
                self.ovx_client.stopPort(ovx_tenant_id, config.VDPID, ovx_port_number)

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
            ovx_port_number = ovxdb.get_ovx_port_number(context.session, id)
            try:
                self.ovx_client.removePort(ovx_tenant_id, config.VDPID, ovx_port_number)
            except Exception as e:
                LOG.warn(_("Neutron OVX: delete vport failed: %s"), e)

            # Remove network from db
            super(OVXNeutronPlugin, self).delete_port(context, id)

    def start_rpc_listener(self):
        """Start the rpc listener.

        Most plugins start an RPC listener implicitly on initialization.  In
        order to support multiple process RPC, the plugin needs to expose
        control over when this is started.

        .. note:: this method is optional, as it was not part of the originally
                  defined plugin API.
        """
        raise NotImplementedError

    def rpc_workers_supported(self):
        """Return whether the plugin supports multiple RPC workers.

        A plugin that supports multiple RPC workers should override the
        start_rpc_listener method to ensure that this method returns True and
        that start_rpc_listener is called at the appropriate time.
        Alternately, a plugin can override this method to customize detection
        of support for multiple rpc workers

        .. note:: this method is optional, as it was not part of the originally
                  defined plugin API.
        """
        return (self.__class__.start_rpc_listener !=
                OVXNeutronPlugin.start_rpc_listener)

    def _do_big_switch_network(self, ctrls, subnet, routing, num_backup):
        """Create OVX network that is a single big switch"""
        
        # request physical topology
        phy_topo = self.ovx_client.getPhysicalTopology()
        # split subnet in netaddress and netmask
        (net_address, net_mask) = subnet.split('/')
        # create virtual network
        tenant_id = self.ovx_client.createNetwork(ctrls, net_address, int(net_mask))
        # create virtual switch with all physical dpids
        dpids = [ovxlib.hexToLong(dpid) for dpid in phy_topo['switches']]
        vdpid = self.ovx_client.createSwitch(tenant_id, dpids)
        # set routing algorithm and number of backups
        if (len(dpids) > 1):
            self.ovx_client.setInternalRouting(tenant_id, vdpid, routing, num_backup)

        return tenant_id
