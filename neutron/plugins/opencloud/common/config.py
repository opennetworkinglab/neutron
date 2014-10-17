from oslo.config import cfg
from neutron.agent.common import config

ovs_opts = [
    cfg.StrOpt('nat_bridge', default='br-nat', help=_("NAT network bridge")),
    cfg.StrOpt('ext_bridge', default='br-ex', help=_("External network bridge"))
]

cfg.CONF.register_opts(ovs_opts, "OVS")
config.register_agent_state_opts_helper(cfg.CONF)
config.register_root_helper(cfg.CONF)
