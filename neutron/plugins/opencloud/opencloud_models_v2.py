from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, PickleType
from sqlalchemy.schema import UniqueConstraint

from neutron.db.models_v2 import model_base

class PortForwarding(model_base.BASEV2):
    """Ports to be forwarded through NAT """
    __tablename__ = 'opencloud_port_forwarding'

    port_id = Column(String(36),
                     ForeignKey('ports.id', ondelete="CASCADE"),
                     primary_key=True)
    forward_ports = Column(PickleType)

    def __init__(self, port_id, forward_ports):
        self.port_id = port_id
        self.forward_ports = forward_ports

    def __repr__(self):
        return "<PortForwarding(%s,%s)>" % (self.port_id, self.forward_ports)

