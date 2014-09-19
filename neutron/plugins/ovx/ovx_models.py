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

import sqlalchemy as sa
from neutron.db import model_base

class NetworkMapping(model_base.BASEV2):
    """Neutron network ID <-> OVX tenant ID & controller server ID.

    Supports only a single controller."""
    __tablename__ = 'ovx_networks'
    neutron_network_id = sa.Column(sa.String(36),
                                   sa.ForeignKey('networks.id', ondelete="CASCADE"),
                                   primary_key=True)
    ovx_tenant_id = sa.Column(sa.Integer, nullable=False)
    ovx_controller = sa.Column(sa.String(36), nullable=False)

    def __repr__(self):
        return "<NetworkMapping(%s,%d,%s)>" % (self.neutron_network_id,
                                               self.ovx_tenant_id,
                                               self.ovx_controller)
    
class PortMapping(model_base.BASEV2):
    """Neutron port ID <-> OVX virtual dpid, virtual port number, and host id mapping."""
    __tablename__ = "ovx_ports"
    neutron_port_id = sa.Column(sa.String(36),
                                sa.ForeignKey('ports.id', ondelete="CASCADE"),
                                primary_key=True)
    ovx_vdpid = sa.Column(sa.BigInteger, nullable=False)
    ovx_vport = sa.Column(sa.Integer, nullable=False)
    ovx_host_id = sa.Column(sa.Integer, nullable=False)

    def __repr__(self):
        return "<PortMapping(%s,%d,%d,%d)>" % (self.neutron_port_id,
                                               self.ovx_vdpid,
                                               self.ovx_vport,
                                               self.ovx_host_id)
    
class PortProfileBinding(model_base.BASEV2):
    """Represents port profile binding to the port on virtual network."""
    __tablename__ = 'port_profile'

    port_id = sa.Column(sa.String(36),
                        sa.ForeignKey('ports.id', ondelete="CASCADE"),
                        primary_key=True)
    bridge = sa.Column(sa.String(20), nullable=False)

    def __init__(self, port_id, bridge):
        self.port_id = port_id
        self.bridge = bridge

    def __repr__(self):
        return "<PortProfileBinding(%s,%s)>" % (self.port_id, self.bridge)
