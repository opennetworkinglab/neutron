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
Neutron plug-in for the OpenVirteX Network Virtualization Platform.
This plugin will forward authenticated REST API calls to OVX.
"""

import sys
import uuid
import time

from oslo.config import cfg

from neutron import context as ctx
from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import exceptions as q_exc
from neutron.common import rpc as q_rpc
from neutron.common import topics
from neutron.db import agents_db
from neutron.db import db_base_plugin_v2
from neutron.db import dhcp_rpc_base
from neutron.db import portbindings_base
from neutron.db import portbindings_db
from neutron.db import quota_db  # noqa
from neutron.extensions import portbindings
from neutron.extensions import topology
from neutron.openstack.common import log as logging
from neutron.openstack.common import rpc
from neutron.plugins.common import constants as svc_constants
from neutron.plugins.ovx import ovxlib
from neutron.plugins.ovx import ovxdb
from neutron.plugins.ovx.common import config
from neutron.plugins.ovx.common import constants as ovx_constants
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
        LOG.debug(_("Agent has port updates, kwargs=%s" % kwargs))

        dpid = kwargs.get('dpid')
        
        for p in kwargs.get('ports_added', []):
            port_id = p['id']
            port_no = p['port_no']
            
            with rpc_context.session.begin(subtransactions=True):
                # Lookup port
                port_db = self.plugin.get_port(rpc_context, port_id)

                # Lookup OVX tenant ID
                neutron_network_id = port_db['network_id']
                ovx_tenant_id = ovxdb.get_ovx_network(rpc_context.session, neutron_network_id).ovx_tenant_id

                # Stop port if requested (port is started by default in OVX)
                if not port_db['admin_state_up']:
                    self.plugin.ovx_client.stopPort(ovx_tenant_id, ovx_vdpid, ovx_vport)

                # Create port in OVX
                (ovx_vdpid, ovx_vport) = self.plugin.ovx_client.createPort(ovx_tenant_id, ovxlib.hexToLong(dpid), int(port_no))

                # Register host in OVX
                ovx_host_id = self.plugin.ovx_client.connectHost(ovx_tenant_id, ovx_vdpid, ovx_vport, port_db['mac_address'])
                    
                # Save mapping between Neutron port ID and OVX dpid, port number, and host ID
                ovxdb.add_ovx_port(rpc_context.session, port_db['id'], ovx_vdpid, ovx_vport, ovx_host_id)

                # Set port in active state in db
                ovxdb.set_port_status(rpc_context.session, port_db['id'], q_const.PORT_STATUS_ACTIVE)

        # Ports removed on the compute node will be marked as down in the database.
        # Use Neutron API to explicitly remove port from OVX & Neutron.
        for port_id in kwargs.get('ports_removed', []):

            with rpc_context.session.begin(subtransactions=True):
                # Lookup port
                try:
                    port_db = self.plugin.get_port(rpc_context, port_id)
                except q_exc.PortNotFound:
                    continue

                # Set port status to DOWN
                if port_db['status'] != q_const.PORT_STATUS_DOWN:
                    ovxdb.set_port_status(rpc_context.session, port_id, q_const.PORT_STATUS_DOWN)
                                
class ControllerManager():
    """Simple manager for SDN controllers. Spawns a VM running a controller for each request
    inside the control network."""
    
    def __init__(self, ctrl_network):
        self.ctrl_network_id = ctrl_network['id']
        self.ctrl_network_name = ctrl_network['name']
        # Nova config for default controllers
        self._nova = nova_client(username=cfg.CONF.NOVA.username, api_key=cfg.CONF.NOVA.password,
                                project_id=cfg.CONF.NOVA.project_id, auth_url=cfg.CONF.NOVA.auth_url,
                                service_type="compute")
        # Check if Nova config is correct
        try:
            self._image = self._nova.images.find(name=cfg.CONF.NOVA.image_name)
            self._flavor = self._nova.flavors.find(name=cfg.CONF.NOVA.flavor)
            # Check if the key name is found, don't save the ref (novaclient wants the name)
            if cfg.CONF.NOVA.key_name:
                self._nova.keypairs.find(name=cfg.CONF.NOVA.key_name)
        except Exception as e:
            LOG.error("Could not initialize Nova bindings. Check your config. (%s)" % e)
            sys.exit(1)

    def spawn(self, name):
        """Spawns SDN controller inside the control network.
        Returns the Nova server ID and IP address."""

        # Connect controller to control network
        nic_config = {'net-id': self.ctrl_network_id}
        # Can also set 'fixed_ip' if needed
        server = self._nova.servers.create(name='OVX_%s' % name,
                                           image=self._image,
                                           flavor=self._flavor,
                                           key_name=cfg.CONF.NOVA.key_name,
                                           nics=[nic_config])
        controller_id = server.id
        # TODO: need a good way to obtain IP address
        timer = 0
        while self.ctrl_network_name not in server.addresses:
            time.sleep(1)
            # If we don't keep on searching for the controller_id,
            # we may never get an IP
            server = self._nova.servers.find(id=controller_id)
            if timer > cfg.CONF.NOVA.timeout:
                raise Exception("Could not start controller in time.")
            timer += 1

        # Fetch IP address of controller instance
        controller_ip = server.addresses[self.ctrl_network_name][0]['addr']
        LOG.info("Spawned SDN controller image %s: ID %s, IP %s" %  (cfg.CONF.NOVA.image_name, controller_id, controller_ip))
        
        return (controller_id, controller_ip)

    def delete(self, controller_id):
        try:
            self._nova.servers.find(id=controller_id).delete()
        except:
            LOG.error("Could not remove VM %s" % controller_id)
                    
class OVXNeutronPlugin(db_base_plugin_v2.NeutronDbPluginV2,
                       agents_db.AgentDbMixin,
                       portbindings_db.PortBindingMixin):

    supported_extension_aliases = ['quotas', 'binding', 'agent', 'topology']

    def __init__(self):
        super(OVXNeutronPlugin, self).__init__()
        # Initialize OVX client API
        self.conf_ovx = cfg.CONF.OVX
        self.ovx_client = ovxlib.OVXClient(self.conf_ovx.api_host, self.conf_ovx.api_port,
                                           self.conf_ovx.username, self.conf_ovx.password)
        # Init port bindings
        self.base_binding_dict = {
            portbindings.VIF_TYPE: portbindings.VIF_TYPE_OVS
        }
        portbindings_base.register_port_dict_function()
        # Init RPC
        self.setup_rpc()
        # Setup empty control network
        self.ctrl_network = self._setup_db_network(ovx_constants.CTRL_NETWORK, ovx_constants.CTRL_SUBNET)
        # Controller manager
        self.ctrl_manager = ControllerManager(self.ctrl_network)

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

    def _extend_port_dict_binding(self, context, port):
        port_binding = ovxdb.get_port_profile_binding(context.session, port['id'])

        if port_binding:
            port[portbindings.PROFILE] = {'bridge': port_binding.bridge}
            
        return port

    def create_network(self, context, network):
        """Creates an OVX-based virtual network.

        The virtual network is a big switch composed out of all physical switches (this
        includes both software and hardware switches) that are connected to OVX.
        An image that is running an OpenFlow controller is spawned for the virtual network.
        """
        LOG.debug("Neutron OVX")
        with context.session.begin(subtransactions=True):
            # Save in db
            net_db = super(OVXNeutronPlugin, self).create_network(context, network)

            # Spawn controller
            (controller_id, controller_ip) = self.ctrl_manager.spawn(net_db['id'])
            
            try:
                ctrl = 'tcp:%s:%s' % (controller_ip, cfg.CONF.NOVA.image_port)
                # Subnet value is irrelevant to OVX
                subnet = '10.0.0.0/24'

                # Create virtual network with requested topology
                topology_type = network['network'].get(topology.TYPE)
                topology_type_set = attributes.is_attr_set(topology_type)

                # Default topology type is bigswitch
                if not topology_type_set:
                    topology_type = svc_constants.BIGSWITCH

                if topology_type == svc_constants.BIGSWITCH:
                    ovx_tenant_id = self._do_big_switch_network(ctrl, subnet)
                elif topology_type == svc_constants.PHYSICAL:
                    ovx_tenant_id = self._do_physical_network(ctrl, subnet)
                else:
                    raise Exception("Topology type %s not supported")

                # Start network if requested
                if net_db['admin_state_up']:
                    self.ovx_client.startNetwork(ovx_tenant_id)
            except Exception:
                self.ctrl_manager.delete(controller_id)
                raise

            # Save mapping between Neutron network ID and OVX tenant ID
            ovxdb.add_ovx_network(context.session, net_db['id'], ovx_tenant_id, controller_id)

        # Return created network
        return net_db

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
        LOG.debug("Neutron OVX")
        
        if id == self.ctrl_network['id']:
            raise Exception("Illegal request: cannot update control network")
        
        with context.session.begin(subtransactions=True):
            # Requested admin state
            req_state = network['network'].get('admin_state_up')
            # Lookup old network state
            net_db = super(OVXNeutronPlugin, self).get_network(context, id)
            db_state = net_db['admin_state_up']
            
            # Start or stop network as requested
            if (req_state != None) and (req_state != db_state):
                ovx_tenant_id = ovxdb.get_ovx_network(context.session, id).ovx_tenant_id
                if req_state:
                    self.ovx_client.startNetwork(ovx_tenant_id)
                else:
                    self.ovx_client.stopNetwork(ovx_tenant_id)

            # Save network to db
            neutron_network = super(OVXNeutronPlugin, self).update_network(context, id, network)

        return neutron_network

    def delete_network(self, context, id):
        """Delete a network.

        :param context: neutron api request context
        :param id: UUID representing the network to delete.
        """
        LOG.debug("Neutron OVX:")

        if id == self.ctrl_network['id']:
            raise Exception("Illegal request: cannot delete control network")

        with context.session.begin(subtransactions=True):
            # TODO: add check only 1 port remains
            # if you delete network in ovx, and network removal from neutron db fails,
            # then you get into an error state
            
            # Need to remove the controller before the network,
            # as Nova will also delete the port in Neutron
            ovx_controller = ovxdb.get_ovx_network(context.session, id).ovx_controller
            self.ctrl_manager.delete(ovx_controller)

            # Remove network from OVX
            ovx_tenant_id = ovxdb.get_ovx_network(context.session, id).ovx_tenant_id
            self.ovx_client.removeNetwork(ovx_tenant_id)

            # Remove network from db
            super(OVXNeutronPlugin, self).delete_network(context, id)

    def get_port(self, context, id, fields=None):
        port = super(OVXNeutronPlugin, self).get_port(context,
                                                      id,
                                                      fields)
        self._extend_port_dict_binding(context, port)
        return self._fields(port, fields)

    def get_ports(self, context, filters=None, fields=None,
                  sorts=None, limit=None, marker=None, page_reverse=False):
        res_ports = []
        ports = super(OVXNeutronPlugin, self).get_ports(context, filters, fields,
                                                        sorts, limit, marker,
                                                        page_reverse)
        for port in ports:
            port = self._extend_port_dict_binding(context, port)
            res_ports.append(self._fields(port, fields))
            
        return res_ports
    
    def create_port(self, context, port):
        LOG.debug("Neutron OVX")
        
        with context.session.begin(subtransactions=True):
            # Set default port status as down, will be updated by agent (data ports only)
            port['port']['status'] = q_const.PORT_STATUS_DOWN

            # Create port in db
            neutron_port = super(OVXNeutronPlugin, self).create_port(context, port)

            # Store the bridge to connect to in the port bindings
            if neutron_port['network_id'] == self.ctrl_network['id']:
                bridge = cfg.CONF.OVS.ctrl_bridge
                ovxdb.set_port_status(context.session, neutron_port['id'], q_const.PORT_STATUS_ACTIVE)
            else:
                bridge = cfg.CONF.OVS.data_bridge

            self._process_portbindings_create_and_update(context, port['port'], neutron_port)
            ovxdb.add_port_profile_binding(context.session, neutron_port['id'], bridge)

            # Can't create the port in OVX yet, we need the dpid & port
            # Wait for agent to tell us

        neutron_port = self._extend_port_dict_binding(context, neutron_port)
        LOG.debug("Setting port binding: %s" % neutron_port)

        return neutron_port

    def update_port(self, context, id, port):
        LOG.debug("Neutron OVX")
        
        with context.session.begin(subtransactions=True):
            # Requested admin state
            req_state = port['port'].get('admin_state_up')
            # Lookup old port state
            port_db = super(OVXNeutronPlugin, self).get_port(context, id)
            db_state = port_db['admin_state_up']
        
            # Start or stop port in OVX (data ports only!) as requested
            if self._is_data_port(context, port_db):
                if (req_state != None) and (req_state != db_state):
                    ovx_tenant_id = ovxdb.get_ovx_network(context.session, port_db['network_id']).ovx_tenant_id
                    ovx_port = ovxdb.get_ovx_port(context.session, id)
                    (ovx_vdpid, ovx_vport) = ovx_port.vdpid, ovx_port.vport
                    if req_state:
                        self.ovx_client.startPort(ovx_tenant_id, ovx_vdpid, ovx_vport)
                    else:
                        self.ovx_client.stopPort(ovx_tenant_id, ovx_vdpid, ovx_vport)

            # Save port to db
            neutron_port = super(OVXNeutronPlugin, self).update_port(context, id, port)

            self._process_portbindings_create_and_update(context, port['port'], neutron_port)

        return self._extend_port_dict_binding(context, neutron_port)

    def _is_data_port(self, context, port):
        self._extend_port_dict_binding(context, port)
        return port.get(portbindings.PROFILE, {}).get('bridge') == cfg.CONF.OVS.data_bridge
        
    def delete_port(self, context, id):
        """Delete a port.

        :param context: neutron api request context
        :param id: UUID representing the port to delete.
        """
        LOG.debug("Neutron OVX")
        
        with context.session.begin(subtransactions=True):
            port_db = super(OVXNeutronPlugin, self).get_port(context, id)
            neutron_network_id = port_db['network_id']
                        
            # Remove port in OVX only if it's a data port
            if self._is_data_port(context, port_db):
                LOG.debug("Removing port from OVX")
                # Lookup OVX tenant ID, virtual dpid and virtual port number
                ovx_tenant_id = ovxdb.get_ovx_network(context.session, neutron_network_id).ovx_tenant_id
                ovx_port = ovxdb.get_ovx_port(context.session, id)
                (ovx_vdpid, ovx_vport) = ovx_port.ovx_vdpid, ovx_port.ovx_vport
                # If OVX throws an exception, assume the virtual port was already gone in OVX
                # as the physical port removal (by nova) triggers the virtual port removal.
                # Any other exception (e.g., OVX is down) will lead to failure of this method.
                # No need to disconnect the host in OVX: when we remove the port,
                # the host goes away as well
                try:
                    self.ovx_client.removePort(ovx_tenant_id, ovx_vdpid, ovx_vport)
                except ovxlib.OVXException:
                    LOG.warn("Could not remove OVX port, most likely because physical port was already removed.")
                
                # Remove OXV mappings from db
                ovxdb.del_ovx_port(context.session, id)

            # Remove network from db
            super(OVXNeutronPlugin, self).delete_port(context, id)

    def _do_big_switch_network(self, ctrl, subnet, routing='spf', num_backup=1):
        """Create virtual network in OVX that is a single big switch.

        If any step fails during network creation, no virtual network will be created."""

        if isinstance(ctrl, list):
            ctrls = ctrl
        else:
            ctrls = [ctrl]

        # Split subnet in network address and netmask
        (net_address, net_mask) = subnet.split('/')

        # Request physical topology
        phy_topo = self.ovx_client.getPhysicalTopology()

        # Fail if there are no physical switches
        switches = phy_topo.get('switches')
        if switches == None:
            raise Exception("Cannot create virtual network without physical switches")

        # Create virtual network
        tenant_id = self.ovx_client.createNetwork(ctrls, net_address, int(net_mask))
        
        # Create big switch, remove virtual network if something went wrong
        try:
            # Create virtual switch with all physical dpids
            dpids = [ovxlib.hexToLong(dpid) for dpid in switches]
            vdpid = self.ovx_client.createSwitch(tenant_id, dpids)
            # Set routing algorithm and number of backups
            if (len(dpids) > 1):
                self.ovx_client.setInternalRouting(tenant_id, vdpid, routing, num_backup)
        except Exception:
            self.ovx_client.removeNetwork(tenant_id)
            raise

        return tenant_id

    def _do_physical_network(self, ctrl, subnet, routing='spf', num_backup=1, copy_dpid = False):
        """Create virtual network in OVX that is a duplicate of the physical topology.

        If any step fails during network creation, no virtual network will be created."""

        if isinstance(ctrl, list):
            ctrls = ctrl
        else:
            ctrls = [ctrl]

        # Split subnet in network address and netmask
        (net_address, net_mask) = subnet.split('/')

        # Request physical topology
        phy_topo = self.ovx_client.getPhysicalTopology()

        # Fail if there are no physical switches
        switches = phy_topo.get('switches')
        if switches == None:
            raise Exception("Cannot create virtual network without physical switches")

        # Create virtual network
        tenant_id = self.ovx_client.createNetwork(ctrls, net_address, int(net_mask))
        
        # Create big switch, remove virtual network if something went wrong
        try:
            # Create virtual switch for each physical dpid
            for dpid in switches:
                if copy_dpid:
                    self.ovx_client.createSwitch(tenant_id, [ovxlib.hexToLong(dpid)], dpid=hexToLong(dpid))
                else:
                    self.ovx_client.createSwitch(tenant_id, [ovxlib.hexToLong(dpid)])

            # Create virtual ports and connect virtual links
            connected = []
            for link in phy_topo['links']:
                # OVX creates reverse link automatically, so be careful no to create a link twice
                if (link['src']['dpid'], link['src']['port']) not in connected:
                    # Create virtual source port
                    # Type conversions needed because OVX JSON output is stringified
                    src_dpid = ovxlib.hexToLong(link['src']['dpid'])
                    src_port = int(link['src']['port'])
                    (src_vdpid, src_vport) = self.ovx_client.createPort(tenant_id, src_dpid, src_port)
                 
                    # Create virtual destination port
                    dst_dpid = ovxlib.hexToLong(link['dst']['dpid'])
                    dst_port = int(link['dst']['port'])
                    (dst_vdpid, dst_vport) = self.ovx_client.createPort(tenant_id, dst_dpid, dst_port)
        
                    # Create virtual link
                    self.ovx_client.connectLink(tenant_id, src_vdpid, src_vport, dst_vdpid, dst_vport, routing, num_backup)

                    # Store reverse link so we don't try to create it again
                    connected.append((link['dst']['dpid'], link['dst']['port']))
        except Exception:
            self.ovx_client.removeNetwork(tenant_id)
            raise

        return tenant_id
    
    def _setup_db_network(self, network, subnet):
        """Creates network in Neutron database, returns the network."""
        
        net_name = network['network']['name']
        LOG.debug("Setting up db network %s" % net_name)
        context = ctx.get_admin_context()
        
        # Check if network already exists in db
        filters = {'name': [net_name]}
        networks = super(OVXNeutronPlugin, self).get_networks(context, filters=filters)
        if len(networks) != 0:
            return networks[0]

        # Register network and subnet in db
        with context.session.begin(subtransactions=True):
            net = super(OVXNeutronPlugin, self).create_network(context, network)
            subnet['subnet']['network_id'] = net['id']
            super(OVXNeutronPlugin, self).create_subnet(context, subnet)

        # Return network does not reference subnet
        return net
