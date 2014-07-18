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
    def update_ports(self, context, port_id, dpid, port_number):
        """RPC to update information of ports on Neutron Server."""
        LOG.info(_("Update ports"))
        self.cast(context, self.make_msg('update_ports',
                                         topic=topics.AGENT,
                                         port_id=port_id,
                                         dpid=dpid,
                                         port_number=port_number))

class OVXNeutronAgent():
    def __init__(self, data_bridge, ctrl_bridge, data_interface, ctrl_interface, root_helper, polling_interval):
        LOG.info(_("Started OVX Neutron Agent"))

        # Lookup or create bridges for data and control network
        # Regular compute nodes will be plugged into the data bridge
        # Virtual network controllers will be plugged into the control bridge
        controller = 'tcp:%s:%s' % (cfg.CONF.of_host:cfg.CONF.of_port)
        self.data_bridge = self.setup_bridge(data_bridge, data_interface, root_helper, controller=controller)
        self.ctrl_bridge = self.setup_bridge(ctrl_bridge, ctrl_interface, root_helper)
        
        self.polling_interval = polling_interval
        self.dpid = self.data_bridge.get_datapath_id()

        self.agent_state = {
            'binary': 'neutron-ovx-agent',
            'api_server': '%s:%s' % (cfg.CONF.api_host, cfg.CONF.api_port),
            'openflow_server': '%s:%s' % (cfg.CONF.of_host, cfg.CONF.of_port),
            'topic': q_const.L2_AGENT_TOPIC,
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
    
    def setup_bridge(self, bridge_name, port_name, root_helper, controller=None):
        """Set up OVS bridge with given name and connect interface with given port name.
        If provided, point the bridge to the controller."""
        
        if ovs_lib.bridge_exists(bridge_name):
            bridge = ovx_lib.OVSBridge(bridge_name, root_helper)
        else:
            bridge = ovs_lib.OVSBridge(bridge_name, root_helper)
            bridge.create()
            bridge.add_port(port_name)

        if controller:
            try:
                bridge.run_vsctl(['set-controller', bridge_name, controller], check_error=True)
            except Exception as e:
                LOG.error("Failed to set bridge controller: %s" % e)
                sys.exit(1)

        return bridge

    def _report_state(self):
        try:
            num_devices = len(self.data_bridge.get_port_name_list() +
                              self.ctrl_bridge.get_port_name_list())
            self.agent_state['configurations']['devices'] = num_devices
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.error(_("Failed reporting state!"))
            
    def update_ports(self, registered_ports):
        # We only care about compute node ports
        ports = self.data_bridge.get_vif_port_set()
        return ports - registered_ports

    def process_ports(self, ports):
        resync = False

        for port in ports:
            LOG.debug(_("Port %s added"), port)
            
            # Inform plugin that port is up
            ovs_port = self.data_bridge.get_vif_port_by_id(port)
            port_id = ovs_port.vif_id
            port_number = ovs_port.ofport
            self.plugin_rpc.update_ports(self.context, port_id, self.dpid, port_number)

        return resync

    def daemon_loop(self):
        sync = True
        ports = set()

        LOG.info(_("OVX Agent RPC Daemon Started!"))

        while True:
            start = time.time()
            if sync:
                LOG.info(_("Agent out of sync with plugin!"))
                ports.clear()
                sync = False

            added_ports = self.update_ports(ports)
            
            # Notify plugin about port deltas
            if added_ports:
                LOG.debug(_("Agent loop has new ports!"))
                # If process ports fails, we should resync with plugin
                sync = self.process_ports(added_ports)
                ports = ports | added_ports
                    
            # Sleep till end of polling interval
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
    control_bridge = cfg.CONF.OVS.data_bridge
    data_interface = cfg.CONF.OVS.data_iface
    ctrl_interface = cfg.CONF.OVS.ctrl_iface
    root_helper = cfg.CONF.AGENT.root_helper
    polling_interval = cfg.CONF.AGENT.polling_interval
    
    agent = OVXNeutronAgent(data_bridge, control_bridge, data_interface, ctrl_interface, root_helper, polling_interval)

    LOG.info(_("Agent initialized successfully, now running... "))
    agent.daemon_loop()
    sys.exit(0)

if __name__ == "__main__":
    main()
