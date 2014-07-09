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

class PortMapping(model_base.BASEV2):
    """Neutron port ID <-> OVX virtual port number mapping."""
    __tablename__ = "ovx_ports"
    neutron_port_id = sa.Column(sa.String(36),
                                sa.ForeignKey('ports.id', ondelete="CASCADE"),
                                primary_key=True)
    ovx_vdpid = sa.Column(sa.BigInteger, nullable=False)
    ovx_vport = sa.Column(sa.Integer, nullable=False)
