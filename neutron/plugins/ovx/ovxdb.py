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

from neutron.plugins.ovx import ovx_models

def add_ovx_tenant_id(session, neutron_network_id, ovx_tenant_id):
    ovx_tenant_id_mapping = ovx_models.NetworkMapping(neutron_network_id=neutron_network_id,
                                                      ovx_tenant_id=ovx_tenant_id)
    session.add(ovx_tenant_id_mapping)

def get_ovx_tenant_id(session, neutron_network_id):
    query = session.query(ovx_models.NetworkMapping)
    result = query.filter_by(neutron_network_id=neutron_network_id).first()
    if result:
        print 'RESULT'
        result.get('ovx_tenant_id')
    else:
        print 'NO RESULT'

def add_ovx_port_number(session, neutron_port_id, ovx_port_number):
    ovx_port_number_mapping = ovx_models.PortMapping(neutron_port_id=neutron_port_id,
                                                     ovx_port_number=ovx_port_number)
    session.add(ovx_port_number_mapping)

def get_ovx_port_number(session, neutron_port_id):
    query = session.query(ovx_models.PortMapping)
    result = query.filter_by(neutron_port_id=neutron_port_id).first()
    if result:
        return result.get('ovx_port_number')
