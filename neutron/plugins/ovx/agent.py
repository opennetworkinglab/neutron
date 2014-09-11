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

import sys
import time

from oslo.config import cfg

from neutron import context
from neutron.agent import rpc as agent_rpc
from neutron.agent.linux import ovs_lib 
from neutron.common import config as logging_config
from neutron.common import constants as q_const
from neutron.common import utils
from neutron.common import topics
from neutron.openstack.common import log
from neutron.openstack.common import loopingcall
from neutron.openstack.common.rpc import dispatcher
from neutron.plugins.ovx.common import config

LOG = log.getLogger(__name__)

class OVXPluginApi(agent_rpc.PluginApi):
    def update_ports(self, context, agent_id, dpid, ports_added, ports_removed):
        """RPC to update information of ports on Neutron plugin."""
        
        LOG.info(_("Update ports: added=%(added)s, removed=%(removed)s"),
                 {'added': ports_added, 'removed': ports_removed})
        self.cast(context, self.make_msg('update_ports',
                                         topic=topics.AGENT,
                                         agent_id=agent_id,
                                         dpid=dpid,
                                         ports_added=ports_added,
                                         ports_removed=ports_removed))

class OVXNeutronAgent():
    def __init__(self, data_bridge, ctrl_bridge, root_helper, polling_interval):
        LOG.info(_("Started OVX Neutron Agent"))

        # Lookup bridges for data and control network
        # Regular compute nodes will be plugged into the data bridge
        # Virtual network controllers will be plugged into the control bridge
        controller = 'tcp:%s:%s' % (cfg.CONF.OVX.of_host, cfg.CONF.OVX.of_port)
        self.data_bridge = ovs_lib.OVSBridge(data_bridge, root_helper)
        self.ctrl_bridge = ovs_lib.OVSBridge(ctrl_bridge, root_helper)
        
        self.polling_interval = polling_interval
        self.dpid = self.data_bridge.get_datapath_id()
        self.need_sync = True

        self.agent_state = {
            'binary': 'neutron-ovx-agent',
            'api_server': '%s:%s' % (cfg.CONF.OVX.api_host, cfg.CONF.OVX.api_port),
            'openflow_server': 'tcp:%s:%s' % (cfg.CONF.OVX.of_host, cfg.CONF.OVX.of_port),
            'topic': q_const.L2_AGENT_TOPIC,
            'host': cfg.CONF.host,
            'configurations': {},
            'agent_type': "OpenVirteX agent",
            'start_flag': True}
        
        self.setup_rpc()

    def setup_rpc(self):
        self.host = utils.get_hostname()
        self.agent_id = 'ovx-q-agent.%s' % self.host
        LOG.info(_("RPC agent_id: %s"), self.agent_id)

        self.context = context.get_admin_context_without_session()

        self.plugin_rpc = OVXPluginApi(topics.PLUGIN)
        self.state_rpc = agent_rpc.PluginReportStateAPI(topics.PLUGIN)

        report_interval = cfg.CONF.AGENT.report_interval
        if report_interval:
            heartbeat = loopingcall.FixedIntervalLoopingCall(self._report_state)
            heartbeat.start(interval=report_interval)
    
    def _report_state(self):
        try:
            num_devices = len(self.data_bridge.get_port_name_list() +
                              self.ctrl_bridge.get_port_name_list())
            self.agent_state['configurations']['devices'] = num_devices
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.error(_("Failed reporting state!"))

    def _vif_port_to_port_info(self, vif_port):
        """Converts VIF port object into dict."""
        
        return dict(id=vif_port.vif_id, port_no=vif_port.ofport,
                    port_name=vif_port.port_name)
    
    def daemon_loop(self):
        """Runs an infinite loop where each iteration:
        (a) checks if ports were added or removed,
        (b) if port changes are observed, an RPC call on the plugin is triggered, and
        (c) sleeps for the polling interval."""
        
        while True:
            start = time.time()
            try:
                # List of port IDs
                cur_ports = [] if self.need_sync else self.cur_ports
                new_ports = []

                # List of port dicts
                ports_added = []
                for vif_port in self.data_bridge.get_vif_ports():
                    port_info = self._vif_port_to_port_info(vif_port)
                    port_id = port_info['id']
                    new_ports.append(port_id)

                    if port_id not in cur_ports:
                        ports_added.append(port_info)
                        # Hack for Stanford OpenCloud deployment
                        self.data_bridge.run_vsctl(["--", "set", "port", vif_port.port_name, "tag=418"])

                # List of port IDs
                ports_removed = []
                for port_id in cur_ports:
                    if port_id not in new_ports:
                        ports_removed.append(port_id)

                if ports_added or ports_removed:
                    self.plugin_rpc.update_ports(self.context,
                                                 self.agent_id, self.dpid,
                                                 ports_added, ports_removed)
                else:
                    LOG.debug(_("No ports changed."))

                self.cur_ports = new_ports
                self.need_sync = False
            
            except Exception:
                LOG.exception(_("Error in agent event loop"))
                self.need_sync = True

            # Sleep until end of polling interval
            elapsed = (time.time() - start)
            if (elapsed < self.polling_interval):
                time.sleep(self.polling_interval - elapsed)
            else:
                LOG.debug(_("Loop iteration exceeded interval "
                            "(%(polling_interval)s vs. %(elapsed)s)!"),
                          {'polling_interval': self.polling_interval,
                           'elapsed': elapsed})

def main():
    cfg.CONF(project='neutron')

    logging_config.setup_logging(cfg.CONF)

    data_bridge = cfg.CONF.OVS.data_bridge
    control_bridge = cfg.CONF.OVS.ctrl_bridge
    root_helper = cfg.CONF.AGENT.root_helper
    polling_interval = cfg.CONF.AGENT.polling_interval
    
    agent = OVXNeutronAgent(data_bridge, control_bridge, root_helper, polling_interval)

    LOG.info(_("OVX agent initialized successfully, now running... "))
    agent.daemon_loop()
    sys.exit(0)

if __name__ == "__main__":
    main()
