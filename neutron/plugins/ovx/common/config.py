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

from oslo.config import cfg
from neutron.agent.common import config

agent_opts = [
    cfg.IntOpt('polling_interval', default=2,
               help=_("The number of seconds the agent will wait between "
                      "polling for local device changes."))
]

nova_opts = [
    cfg.StrOpt('username', default='admin', help=_('Nova username.')),
    cfg.StrOpt('password', default='', help=_('Nova password.')),
    cfg.StrOpt('project_id', default='admin', help=_('Nova project ID (name, not the tenant ID given by a UUID).')),
    cfg.StrOpt('auth_url', default='http://localhost:5000/v2.0/', help=_('Nova authentication URL.')),
    cfg.StrOpt('image_name', default='cirros-0.3.1-x86_64-uec', help=_('SDN controller image name.')),
    cfg.IntOpt('image_port', default=10000, help=_('OpenFlow port of SDN controller image.')),
    cfg.StrOpt('flavor', default='m1.tiny', help=_('Machine flavor on which to run SDN controller.')),
]

ovs_opts = [
    cfg.StrOpt('integration_bridge', default='br-int', help=_("Integration bridge to use")),
]

ovx_opts = [
    cfg.StrOpt('host', default='localhost', help=_('OVX server address.')),
    cfg.IntOpt('port', default=8080, help=_('OVX server port.')),
    cfg.StrOpt('username', default='admin', help=_('OVX admin user.')),
    cfg.StrOpt('password', default='', help=_('OVX admin passord.')),
]

cfg.CONF.register_opts(agent_opts, 'AGENT')
cfg.CONF.register_opts(nova_opts, 'NOVA')
cfg.CONF.register_opts(ovs_opts, "OVS")
cfg.CONF.register_opts(ovx_opts, 'OVX')
config.register_agent_state_opts_helper(cfg.CONF)
config.register_root_helper(cfg.CONF)
