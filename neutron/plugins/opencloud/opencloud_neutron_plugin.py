from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import exceptions as q_exc
from neutron.openstack.common import log as logging
from neutron.plugins.opencloud.common import config
from neutron.plugins.opencloud.common import constants as opencloud_constants
from neutron.plugins.ovx import ovxdb
from neutron.plugins.ovx.plugin import *
from neutron.extensions import nat
from neutron.extensions import portbindings

import opencloud_db_v2

LOG = logging.getLogger(__name__)


class OpenCloudPluginV2(OVXNeutronPlugin):
    """Neutron plugin for OpenCloud deployments based on OVX.
    Original code by Scott Baker:
    http://git.planet-lab.org/?p=opencloud-plugin.git;a=summary"""
    
    supported_extension_aliases = OVXNeutronPlugin.supported_extension_aliases + ["nat"]

    def __init__(self):
        super(OpenCloudPluginV2, self).__init__()
        # Setup NAT network
        self.nat_network = self._setup_db_network(opencloud_constants.NAT_NETWORK, opencloud_constants.NAT_SUBNET)
        # Setup external network
        self.ext_network = self._setup_db_network(opencloud_constants.EXT_NETWORK, opencloud_constants.EXT_SUBNET)
    
    def _extend_port_dict_nat(self, context, port):
        forward = opencloud_db_v2.get_port_forwarding(context.session, port['id'])
        if forward:
            port[nat.FORWARD_PORTS] = forward
        else:
            port[nat.FORWARD_PORTS] = None

    def _process_nat_update(self, context, attrs, id):
        forward_ports = attrs.get(nat.FORWARD_PORTS)
        forward_ports_set = attributes.is_attr_set(forward_ports)

        if not forward_ports_set:
            return None

        # LOG.info("forward ports %s" % forward_ports)
        valid_protocols = ["tcp", "udp"]
        for entry in forward_ports:
            if not isinstance(entry, dict):
                msg = _("nat:forward_ports: must specify a list of dicts (ex: 'l4_protocol=tcp,l4_port=80')")
                raise q_exc.InvalidInput(error_message=msg)
            if not ("l4_protocol" in entry and "l4_port" in entry):
                msg = _("nat:forward_ports: dict is missing l4_protocol and l4_port (ex: 'l4_protocol=tcp,l4_port=80')")
                raise q_exc.InvalidInput(error_message=msg)
            if entry['l4_protocol'] not in valid_protocols:
                msg = _("nat:forward_ports: invalid protocol (only tcp and udp allowed)")
                raise q_exc.InvalidInput(error_message=msg)

            l4_port = entry['l4_port']
            if ":" in l4_port:
                try:
                    (first, last) = l4_port.split(":")
                    first = int(first)
                    last = int(last)
                except:
                    msg = _("nat:forward_ports: l4_port range must be integer:integer")
                    raise q_exc.InvalidInput(error_message=msg)
            else:
                try:
                    l4_port = int(l4_port)
                except:
                    msg = _("nat:forward_ports: l4_port must be an integer")
                    raise q_exc.InvalidInput(error_message=msg)

        return forward_ports

    def delete_network(self, context, id):
        LOG.debug("Neutron OpenCloud:")

        if id == self.nat_network['id']:
            raise Exception("Illegal request: cannot delete NAT network")
        elif id == self.ext_network['id']:
            raise Exception("Illegal request: cannot delete external network")
        else:
            return super(OpenCloudPluginV2, self).delete_network(context, id)
        
    def get_port(self, context, id, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            port = super(OpenCloudPluginV2, self).get_port(context, id, None)
            self._extend_port_dict_nat(context, port)
        return self._fields(port, fields)

    def get_ports(self, context, filters=None, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            ports = super(OpenCloudPluginV2, self).get_ports(context, filters,
                                                          None)
            for port in ports:
                self._extend_port_dict_nat(context, port)

        return [self._fields(port, fields) for port in ports]

    def create_port(self, context, port):
        neutron_port = super(OpenCloudPluginV2, self).create_port(context, port)
        
        # Set port binding to NAT bridge
        if neutron_port['network_id'] == self.nat_network['id']:
            opencloud_db_v2.set_port_profile_binding(context.session, neutron_port['id'], cfg.CONF.OVS.nat_bridge)
            ovxdb.set_port_status(context.session, neutron_port['id'], q_const.PORT_STATUS_ACTIVE)
        # Set port binding to external bridge
        if neutron_port['network_id'] == self.ext_network['id']:
            opencloud_db_v2.set_port_profile_binding(context.session, neutron_port['id'], cfg.CONF.OVS.ext_bridge)
            ovxdb.set_port_status(context.session, neutron_port['id'], q_const.PORT_STATUS_ACTIVE)

        neutron_port = self._extend_port_dict_binding(context, neutron_port)
        LOG.debug("Setting port binding: %s" % neutron_port)

        return neutron_port
        
    def update_port(self, context, id, port):
        forward_ports = self._process_nat_update(context, port['port'], id)
        session = context.session
        with session.begin(subtransactions=True):
            updated_port = super(OpenCloudPluginV2, self).update_port(context, id, port)
            if forward_ports:
                opencloud_db_v2.clear_port_forwarding(session, updated_port['id'])
                opencloud_db_v2.add_port_forwarding(session, updated_port['id'], forward_ports)
                self._extend_port_dict_nat(context, updated_port)

        return self._extend_port_dict_binding(context, updated_port)
