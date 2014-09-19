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

from neutron.db import models_v2
from neutron.plugins.ovx import ovx_models

def add_ovx_network(session, neutron_network_id, ovx_tenant_id, ovx_controller):
    ovx_network_mapping = ovx_models.NetworkMapping(neutron_network_id=neutron_network_id,
                                                    ovx_tenant_id=ovx_tenant_id,
                                                    ovx_controller=ovx_controller)
    session.add(ovx_network_mapping)

def get_ovx_network(session, neutron_network_id):
    query = session.query(ovx_models.NetworkMapping)
    return query.filter_by(neutron_network_id=neutron_network_id).one()

def add_port_profile_binding(session, port_id, bridge):
    port_profile_binding = ovx_models.PortProfileBinding(port_id=port_id,
                                                         bridge=bridge)
    session.add(port_profile_binding)

def get_port_profile_binding(session, port_id):
    query = session.query(ovx_models.PortProfileBinding)
    return query.filter_by(port_id=port_id).one()

def add_ovx_port(session, neutron_port_id, ovx_vdpid, ovx_vport, ovx_host_id):
    ovx_vport_mapping = ovx_models.PortMapping(neutron_port_id=neutron_port_id,
                                               ovx_vdpid=ovx_vdpid,
                                               ovx_vport=ovx_vport,
                                               ovx_host_id=ovx_host_id)
    session.add(ovx_vport_mapping)

def get_ovx_port(session, neutron_port_id):
    query = session.query(ovx_models.PortMapping)
    return query.filter_by(neutron_port_id=neutron_port_id).one()

def del_ovx_port(session, neutron_port_id):
    query = session.query(ovx_models.PortMapping)
    result = query.filter_by(neutron_port_id=neutron_port_id).one()
    if result:
        session.delete(result)
    
def set_port_status(session, port_id, status):
    """Set the port status."""
    query = session.query(models_v2.Port)
    result = query.filter_by(id=port_id).one()
    result['status'] = status
    session.merge(result)
    session.flush()
