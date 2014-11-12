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
        'name': 'nat-net',
        'ip_version': 4,
        'cidr': '172.16.0.0/16',
        'gateway_ip': '172.16.0.1',
        'dns_nameservers': [],
        'allocation_pools': attributes.ATTR_NOT_SPECIFIED,
        'host_routes': [],
        'enable_dhcp': False
    }
}

EXT_NETWORK = {
    'network': {
        'name': 'ext-net',
        'admin_state_up': True,
        'shared': False
    }
}

# TODO: add tenant_id? (lookup by project_id)
EXT_SUBNET = {
    'subnet': {
        'name': 'ext-net',
        'ip_version': 4,
        'cidr': '171.66.164.0/24',
        'gateway_ip': '171.66.164.1',
        'dns_nameservers': [],
        'allocation_pools': [{"start": "171.66.164.3", "end": "171.66.164.254"}],
        'host_routes': [],
        'enable_dhcp': True
    }
}
