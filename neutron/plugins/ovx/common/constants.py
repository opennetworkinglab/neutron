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

from neutron.api.v2 import attributes

CTRL_NETWORK = {
    'network': {
        'name': 'OVX_ctrl_network',
        'admin_state_up': True,
        'shared': False
    }
}

# TODO: add tenant_id? (lookup by project_id)
CTRL_SUBNET = {
    'subnet': {
        'name': 'OVX_ctrl_subnet',
        'ip_version': 4,
        'cidr': '192.168.83.0/24',
        'gateway_ip': None,
        'dns_nameservers': [],
        'allocation_pools': [{'start': '192.168.83.100', 'end': '192.168.83.254'}],
        'host_routes': [],
        'enable_dhcp': True
    }
}

NAT_NETWORK = {
    'network': {
        'name': 'OpenCloud_nat_network',
        'admin_state_up': True,
        'shared': False
    }
}

# TODO: add tenant_id? (lookup by project_id)
NAT_SUBNET = {
    'subnet': {
        'name': 'OpenCloud_nat_subnet',
        'ip_version': 4,
        'cidr': '172.16.0.0/16',
        'gateway_ip': '172.16.0.1',
        'dns_nameservers': [],
        'allocation_pools': attributes.ATTR_NOT_SPECIFIED,
        'host_routes': [],
        'enable_dhcp': False
    }
}
