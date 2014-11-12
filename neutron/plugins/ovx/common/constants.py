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
        'allocation_pools': [{'start': '192.168.83.20', 'end': '192.168.83.254'}],
        'host_routes': [],
        'enable_dhcp': True
    }
}
