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

import time

from oslo.config import cfg

from neutron import context
from neutron.agent import rpc as agent_rpc
from neutron.agent.linux import ovs_lib 
from neutron.common import config as logging_config
from neutron.common import utils
#from neutron.common import rpc_compat
from neutron.common import topics
from neutron.openstack.common import log
from neutron.openstack.common.rpc import dispatcher
from neutron.plugins.ovx.common import config

LOG = log.getLogger(__name__)

class OVXPluginApi(agent_rpc.PluginApi):
    def update_port(self, context, dpid, port):
        """RPC to update information of ports on Neutron Server."""
        LOG.info(_("Update port"))
        self.call(context, self.make_msg('update_port',
                                         topic=topics.AGENT,
                                         dpid=dpid,
                                         port=port))

# class OVXRpcCallback(rpc_compat.RpcCallback):
#     def __init__(self, context, agent):
#         self.context = context
#         self.agent = agent
    
class OVXNeutronAgent():
    def __init__(self, integration_bridge, root_helper, polling_interval):
        LOG.exception(_("Started OVX Neutron Agent"))
        # Lookup integration bridge
        self.int_br = ovs_lib.OVSBridge(integration_bridge, root_helper)
        
        self.root_helper = root_helper
        self.polling_interval = polling_interval
        self.datapath_id = "0x%s" % self.int_br.get_datapath_id()

        self.setup_rpc()

    def setup_rpc(self):
        self.host = utils.get_hostname()
        self.agent_id = 'ovx-q-agent.%s' % self.host
        LOG.info(_("RPC agent_id: %s"), self.agent_id)

        self.topic = topics.AGENT
        self.context = context.get_admin_context_without_session()

        self.plugin_rpc = OVXPluginApi(topics.PLUGIN)
        # not doing state_rpc for now
        #self.state_rpc = agent_rpc.PluginReportStateAPI(topics.PLUGIN)

        # # RPC network init
        # self.callback = OVXRpcCallback(self.context, self)
        # self.dispatcher = dispatcher.RpcDispatcher([self.callback])

        # consumers = [[topics.PORT, topics.UPDATE]]
        # self.connection = agent_rpc.create_consumers(self.dispatcher, self.topic, consumers)

    def update_ports(self, registered_ports):
        ports = self.int_br.get_vif_port_set()
        return ports - registered_ports

    def process_ports(self, ports):
        resync = False

        for port in ports:
            LOG.debug(_("Port %s added"), port)
            
            # TODO: port should already be connected - VERIFY!
            # get dpid / port
            # inform agent about port, also pass in device
            print '=== PROCESSING ==='
            p = self.int_br.get_vif_port_by_id(port)
            print 'HELLO', p, 'HELLO AGAIN'
            print self.int_br.get_datapath_id()
            self.plugin_rpc.update_port(self.context, self.int_br.get_datapath_id(), self.int_br.get_port_ofport(port))

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
            print '*** NEW PORTS', added_ports
            
            # notify plugin about port deltas
            if added_ports:
                LOG.debug(_("Agent loop has new ports!"))
                # If process ports fails, we should resync with plugin
                sync = self.process_ports(added_ports)
                ports = ports | added_ports
                    
            # sleep till end of polling interval
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

    integration_bridge = cfg.CONF.OVS.integration_bridge
    root_helper = cfg.CONF.AGENT.root_helper
    polling_interval = cfg.CONF.AGENT.polling_interval
    
    agent = OVXNeutronAgent(integration_bridge, root_helper, polling_interval)

    LOG.info(_("Agent initialized successfully, now running... "))
    agent.daemon_loop()
    sys.exit(0)

if __name__ == "__main__":
    main()
