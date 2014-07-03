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
            msg = '%s (%s)' % (j['error']['message'], j['error']['code'])
            raise Exception(msg)
        return j['result']

    def _connect(self, cmd, url, data=None):
        try:
            passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(None, url, self.user, self.password)
            authhandler = urllib2.HTTPBasicAuthHandler(passman)
            opener = urllib2.build_opener(authhandler)
            req = self._build_request(data, url, cmd)
            ph = opener.open(req)
            return self._parse_response(ph.read())
        except Exception:
            raise Exception("OVX connection error")
        # except urllib2.URLError as e:
        #     raise
        # except urllib2.HTTPError as e:
        #     if e.code == 401:
        #         LOG.error("Authentication failed: invalid password")
        #     elif e.code == 504:
        #         LOG.error("HTTP Error 504: Gateway timeout")
        #     else:
        #         LOG.error(e)
        #     raise e
        # except RuntimeError as e:
        #     LOG.error(e)
        #     raise e

    def createNetwork(self, ctrls, net_address, net_mask):
        req = {'controllerUrls': ctrls, 
               'networkAddress': net_address, 'mask': net_mask}
        ret = self._connect("createNetwork", self.tenant_url, data=req)
        tenantId = ret.get('tenantId')
        if tenantId:
            LOG.info("Network with tenantId %s has been created" % tenantId)
        return tenantId

    def removeNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        try:
            ret = self._connect("removeNetwork", self.tenant_url, data=req)
            LOG.info("Network with tenantId %s has been removed" % tenantId)
        except Exception as e:
            e.rollback = False
            raise
        
    def createSwitch(self, tenantId, dpids, dpid=None):
        req = {'tenantId': tenantId, 'dpids': dpids}
        if dpid:
            req["vdpid"] = dpid
        try:
            ret = self._connect("createSwitch", self.tenant_url, data=req)
            switchId = ret.get('vdpid')
            if switchId:
                LOG.info("Switch with switchId %s has been created" % longToHex(switchId))
            return switchId
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def createPort(self, tenantId, dpid, port):
        req = {'tenantId': tenantId, 'dpid': dpid, 'port': port}
        try:
            ret = self._connect("createPort", self.tenant_url, data=req)
            switchId = ret.get('vdpid')
            portId = ret.get('vport')
            if switchId and portId:
                LOG.info("Port on switch %s with port number %s has been created" % (longToHex(switchId), portId))
            return (switchId, portId)
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def removePort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        try:
            ret = self._connect("removePort", self.tenant_url, data=req)
            LOG.info("Virtual port for tenantId %s on virtual dpid %s and virtual port number %s has been removed" % (tenantId, vdpid, vport))
        except Exception as e:
            e.rollback = False
            raise
        
    def connectLink(self, tenantId, srcDpid, srcPort, dstDpid, dstPort, algorithm, backup_num):
        req = {'tenantId': tenantId, 'srcDpid': srcDpid, 'srcPort': srcPort, 'dstDpid': dstDpid, 'dstPort': dstPort, 'algorithm': algorithm, 'backup_num': backup_num}
        try:
            ret = self._connect("connectLink", self.tenant_url, data=req)
            linkId = ret.get('linkId')
            if linkId:
                LOG.info("Link with linkId %s has been created" % linkId)
            return linkId
        except Exception as e:
              e.rollback = True
              e.tenantId = tenantId
              raise

    def setLinkPath(self, tenantId, linkId, path, priority):
        req = {'tenantId': tenantId, 'linkId': linkId, 'path': path, 'priority': priority}
        try:
            ret = self._connect("setLinkPath", self.tenant_url, data=req)
            if ret:
                LOG.info("Path on link %s has been set" % linkId)
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def connectHost(self, tenantId, vdpid, vport, mac):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport, 'mac': mac}
        try:
            ret = self._connect("connectHost", self.tenant_url, data=req)
            hostId = ret.get('hostId')
            if hostId:
                LOG.info("Host with hostId %s connected" % hostId)
            return hostId
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
            
    def connectRoute(self, tenantId, switchId, srcPort, dstPort, path):
        req = {'tenantId': tenantId, 'vdpid': switchId, 'srcPort': srcPort, 'dstPort': dstPort, 'path': path}
        try:
            ret = self._connect("connectRoute", self.tenant_url, data=req)
            routeId = reg.get('routeId')
            if routeId:
                LOG.info("Route with routeId %s on switch %s between ports (%s,%s) created" % (routeId, switchId, srcPort, dstPort))
            return routeId
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def createSwitchRoute(self, tenantId, switchId, srcPort, dstPort, path):
        req = {'tenantId': tenantId, 'dpid': switchId, 'srcPort': srcPort, 'dstPort': dstPort, 'path': path}
        try:
            ret = self._connect("createSwitchRoute", self.tenant_url, data=req)
            if ret:
                LOG.info("Route on switch %s between ports (%s,%s) created" % (switchId, srcPort, dstPort))
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def startNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        try:
            ret = self._connect("startNetwork", self.tenant_url, data=req)
            if ret:
                LOG.info("Network with tenantId %s has been started" % tenantId)
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def stopNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        try:
            ret = self._connect("stopNetwork", self.tenant_url, data=req)
            if ret:
                LOG.info("Network with tenantId %s has been stopped" % tenantId)
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def startPort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        try:
            ret = self._connect("startPort", self.tenant_url, data=req)
            if ret:
                LOG.info("Port on network with tenantId %s, virtual switch id %s, and virtual port number %s has been started" % (tenantId, longToHex(vdpid), vport))
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def stopPort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        try:
            ret = self._connect("stopPort", self.tenant_url, data=req)
            if ret:
                LOG.info("Port on network with tenantId %s, virtual switch id %s, and virtual port number %s has been stopped" % (tenantId, longToHex(vdpid), vport))
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def getPhysicalTopology(self):
        ret = self._connect("getPhysicalTopology", self.status_url)
        try:
            if ret:
                LOG.info("Physical network topology received")
            return ret
        except Exception as e:
            e.rollback = False
            raise

    def setInternalRouting(self, tenantId, vdpid, algorithm, backup_num):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'algorithm': algorithm, 'backup_num': backup_num}
        try:
            ret = self._connect("setInternalRouting", self.tenant_url, data=req)
            if ret:
                LOG.info("Internal routing of switch %s has been set to %s" % (longToHex(vdpid), algorithm))
            return ret
        except Exception as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
