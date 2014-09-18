from oslo.config import cfg
from neutron.agent.common import config

ovs_opts = [
    cfg.StrOpt('ovs_bridge', default='br-nat', help=_("NAT network bridge"))
]

cfg.CONF.register_opts(nat_opts, "OVS")
config.register_agent_state_opts_helper(cfg.CONF)
config.register_root_helper(cfg.CONF)
