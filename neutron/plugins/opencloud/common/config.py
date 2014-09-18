from oslo.config import cfg
from neutron.agent.common import config

nat_opts = [
    cfg.StrOpt('nat_bridge', default='br-nat', help=_("NAT network bridge"))
]

cfg.CONF.register_opts(nat_opts, "NAT")
config.register_agent_state_opts_helper(cfg.CONF)
config.register_root_helper(cfg.CONF)
