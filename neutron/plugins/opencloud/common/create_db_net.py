from neutron import context as ctx
from neutron.api.v2 import attributes
from neutron.db import db_base_plugin_v2

NAT_NETWORK = {
    'network': {
        'name': 'nat-net',
        'admin_state_up': True,
        'shared': False
    }
}

# TODO: add tenant_id? (lookup by project_id)
NAT_SUBNET = {
    'subnet': {
        'name': 'nat-subnet',
        'ip_version': 4,
        'cidr': '172.16.0.0/16',
        'gateway_ip': '172.16.0.1',
        'dns_nameservers': [],
        'allocation_pools': attributes.ATTR_NOT_SPECIFIED,
        'host_routes': [],
        'enable_dhcp': False
    }
}

def setup_network(network, subnet):
    """Creates network and subnet in Neutron database."""

    context = ctx.get_admin_context()
    db_plugin = db_base_plugin_v2.NeutronDbPluginV2()
    
    # Check if network already exists
    net_name = network['network']['name']
    filters = {'name': [net_name]}
    nets = db_plugin.get_networks(context, filters=filters)
    if len(nets) != 0:
        print "Network %s already in db" % nat_name
        return

    # Register network and subnet in db
    with context.session.begin(subtransactions=True):
        net = db_plugin.create_network(context, network)
        subnet['subnet']['network_id'] = net['id']
        db_plugin.create_subnet(context, subnet)

if __name__ == "__main__":
    setup_network(NAT_NETWORK, NAT_SUBNET)
