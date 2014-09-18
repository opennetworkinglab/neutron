from neutron.api.v2 import attributes

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
