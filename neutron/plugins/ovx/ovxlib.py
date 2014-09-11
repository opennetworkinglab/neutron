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

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import json
import urllib2

from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)

def hexToLong(h):
    """Convert dotted hex to long value."""
    return int(h.replace(':', ''), 16)

def longToHex(l, length=8):
    """Convert long value to dotted hex value with specified length in bytes."""
    h = ("%x" % l)
    if len(h) % 2 != 0:
        h = '0' + h
    result = ':'.join([h[i:i+2] for i in range(0, len(h), 2)])
    prefix = '00:' * (length - (len(h) / 2) - (len(h) % 2))
    return prefix + result

class OVXException(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg

    def __str__(self):
        return '%s (%s)' % (self.msg, self.code)

class OVXClient():
    """Implements a client for the OpenVirteX API."""
    
    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.base_url = "http://%s:%s/" % (self.host, self.port)
        self.tenant_url = self.base_url + 'tenant'
        self.status_url = self.base_url + 'status'
        
    def _build_request(self, data, url, cmd):
        j = { "id" : "ovxlib", "method" : cmd, "jsonrpc" : "2.0" }
        h = {"Content-Type" : "application/json"}
        if data is not None:
            j['params'] = data
        return urllib2.Request(url, json.dumps(j), h)

    def _parse_response(self, data):
        j = json.loads(data)
        if 'error' in j:
            raise OVXException(j['error']['code'], j['error']['message'])
        return j['result']

    def _connect(self, cmd, url, data=None):
        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, self.user, self.password)
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        opener = urllib2.build_opener(authhandler)
        req = self._build_request(data, url, cmd)
        ph = opener.open(req)
        response = self._parse_response(ph.read())
        return response

    def createNetwork(self, ctrls, net_address, net_mask):
        req = {'controllerUrls': ctrls, 
               'networkAddress': net_address, 'mask': net_mask}
        ret = self._connect("createNetwork", self.tenant_url, data=req)
        return ret.get('tenantId')

    def removeNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        ret = self._connect("removeNetwork", self.tenant_url, data=req)
        
    def createSwitch(self, tenantId, dpids, dpid=None):
        req = {'tenantId': tenantId, 'dpids': dpids}
        if dpid:
            req["vdpid"] = dpid
        ret = self._connect("createSwitch", self.tenant_url, data=req)
        return ret.get('vdpid')

    def createPort(self, tenantId, dpid, port):
        req = {'tenantId': tenantId, 'dpid': dpid, 'port': port}
        ret = self._connect("createPort", self.tenant_url, data=req)
        return (ret.get('vdpid'), ret.get('vport'))

    def removePort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        ret = self._connect("removePort", self.tenant_url, data=req)
        
    def connectLink(self, tenantId, srcDpid, srcPort, dstDpid, dstPort, algorithm, backup_num):
        req = {'tenantId': tenantId, 'srcDpid': srcDpid, 'srcPort': srcPort, 'dstDpid': dstDpid, 'dstPort': dstPort, 'algorithm': algorithm, 'backup_num': backup_num}
        ret = self._connect("connectLink", self.tenant_url, data=req)
        return ret.get('linkId')

    def setLinkPath(self, tenantId, linkId, path, priority):
        req = {'tenantId': tenantId, 'linkId': linkId, 'path': path, 'priority': priority}
        ret = self._connect("setLinkPath", self.tenant_url, data=req)

    def connectHost(self, tenantId, vdpid, vport, mac):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport, 'mac': mac}
        ret = self._connect("connectHost", self.tenant_url, data=req)
        hostId = ret.get('hostId')
        return ret.get('hostId')

    def disconnectHost(self, tenantId, hostId):
        req = {'tenantId': tenantId, 'hostId': hostId}
        ret = self._connect("disconnectHost", self.tenant_url, data=req)

    def connectRoute(self, tenantId, switchId, srcPort, dstPort, path):
        req = {'tenantId': tenantId, 'vdpid': switchId, 'srcPort': srcPort, 'dstPort': dstPort, 'path': path}
        ret = self._connect("connectRoute", self.tenant_url, data=req)
        return reg.get('routeId')

    def createSwitchRoute(self, tenantId, switchId, srcPort, dstPort, path):
        req = {'tenantId': tenantId, 'dpid': switchId, 'srcPort': srcPort, 'dstPort': dstPort, 'path': path}
        ret = self._connect("createSwitchRoute", self.tenant_url, data=req)

    def startNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        ret = self._connect("startNetwork", self.tenant_url, data=req)

    def stopNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        ret = self._connect("stopNetwork", self.tenant_url, data=req)
        
    def startPort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        ret = self._connect("startPort", self.tenant_url, data=req)

    def stopPort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        ret = self._connect("stopPort", self.tenant_url, data=req)
        
    def getPhysicalTopology(self):
        ret = self._connect("getPhysicalTopology", self.status_url)
        LOG.info("getPhysicalTopology called")
        return ret

    def setInternalRouting(self, tenantId, vdpid, algorithm, backup_num):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'algorithm': algorithm, 'backup_num': backup_num}
        ret = self._connect("setInternalRouting", self.tenant_url, data=req)
