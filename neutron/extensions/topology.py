from neutron.api.v2 import attributes

FORWARD_PORTS = 'nat:forward_ports'

EXTENDED_ATTRIBUTES_2_0 = {
    'topology': {
        TYPE: {'allow_post': True, 'allow_put': True,
               'default': attributes.ATTR_NOT_SPECIFIED,
               'validate': {'type:values': ['bigswitch', 'physical', 'custom']},
               'is_visible': True},
    }
}

class Topology(object):
    @classmethod
    def get_name(cls):
        return "Topology Networking Extension"

    @classmethod
    def get_alias(cls):
        return "topo"

    @classmethod
    def get_description(cls):
        return "Specify virtual network topology"

    @classmethod
    def get_namespace(cls):
        # return "http://docs.openstack.org/ext/provider/api/v1.0"
        # Nothing there right now
        return "http://www.vicci.org/ext/opencloud/topology/api/v0.1"

    @classmethod
    def get_updated(cls):
        return "2014-11-04T10:00:00-00:00"

    def get_extended_resources(self, version):
        if version == "2.0":
            return EXTENDED_ATTRIBUTES_2_0
        else:
            return {}
