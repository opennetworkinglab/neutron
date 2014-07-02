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

class ERROR_CODE:
    PARSE_ERROR = -32700          # Invalid JSON was received by the server.
    INVALID_REQ = -32600          # The JSON sent is not a valid Request object.
    METHOD_NOT_FOUND = -32601     # The method does not exist / is not available.
    INVALID_PARAMS = -32602       # Invalid method parameter(s).
    INTERNAL_ERROR = -32603	      # Internal JSON-RPC error.

class OVXException(Exception):
    def __init__(self, code, msg, tenantId, rollback=False):
        self.code = code
        self.msg = msg
        self.rollback = rollback
        self.tenantId = tenantId

    def __str__(self):
        return '%s (%s)' % (self.msg, self.code)

class EmbedderException(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg

    def __str__(self):
        return '%s (%s)' % (self.msg, self.code)

# Convert dotted hex to long value
def hexToLong(h):
    return int(h.replace(':', ''), 16)

# Convert long value to dotted hex value with specified length in bytes
def longToHex(l, length=8):
    h = ("%x" % l)
    if len(h) % 2 != 0:
        h = '0' + h
    result = ':'.join([h[i:i+2] for i in range(0, len(h), 2)])
    prefix = '00:' * (length - (len(h) / 2) - (len(h) % 2))
    return prefix + result

class OVXClient():
    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.base_url = "http://%s:%s/" % (self.host, self.port)
        self.tenant_url = self.base_url + 'tenant'
        self.status_url = self.base_url + 'status'
        
    def _buildRequest(self, data, url, cmd):
        j = { "id" : "ovxlib", "method" : cmd, "jsonrpc" : "2.0" }
        h = {"Content-Type" : "application/json"}
        if data is not None:
            j['params'] = data
        return urllib2.Request(url, json.dumps(j), h)

    def _parseResponse(self, data):
        j = json.loads(data)
        if 'error' in j:
            e = OVXException(j['error']['code'], j['error']['message'], -1)
            log.error(e)
            raise e
        return j['result']

    def _connect(self, cmd, url, data=None):
        log.debug("%s: %s" % (cmd, data))
        try:
            passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(None, url, self.user, self.password)
            authhandler = urllib2.HTTPBasicAuthHandler(passman)
            opener = urllib2.build_opener(authhandler)
            req = self._buildRequest(data, url, cmd)
            ph = opener.open(req)
            return self._parseResponse(ph.read())
        except urllib2.URLError as e:
            log.error(e)
        except urllib2.HTTPError as e:
            if e.code == 401:
                log.error("Authentication failed: invalid password")
                print "Authentication failed: invalid password"
            elif e.code == 504:
                log.error("HTTP Error 504: Gateway timeout")
                print "HTTP Error 504: Gateway timeout"
            else:
                log.error(e)
        except RuntimeError as e:
            log.error(e)

    def createNetwork(self, ctrls, net_address, net_mask):
        req = {'controllerUrls': ctrls, 
               'networkAddress': net_address, 'mask': net_mask}
        try:
            ret = self._connect("createNetwork", self.tenant_url, data=req)
            tenantId = ret.get('tenantId')
            if tenantId:
                log.info("Network with tenantId %s has been created" % tenantId)
            return tenantId
        except OVXException as e:
            e.rollback = False
            raise

    def removeNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        try:
            ret = self._connect("removeNetwork", self.tenant_url, data=req)
            log.info("Network with tenantId %s has been removed" % tenantId)
        except OVXException as e:
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
                log.info("Switch with switchId %s has been created" % longToHex(switchId))
            return switchId
        except OVXException as e:
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
                log.info("Port on switch %s with port number %s has been created" % (longToHex(switchId), portId))
            return (switchId, portId)
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def removePort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        try:
            ret = self._connect("removePort", self.tenant_url, data=req)
            log.info("Virtual port for tenantId %s on virtual dpid %s and virtual port number %s has been removed" % (tenantId, vdpid, vport))
        except OVXException as e:
            e.rollback = False
            raise
        
    def connectLink(self, tenantId, srcDpid, srcPort, dstDpid, dstPort, algorithm, backup_num):
        req = {'tenantId': tenantId, 'srcDpid': srcDpid, 'srcPort': srcPort, 'dstDpid': dstDpid, 'dstPort': dstPort, 'algorithm': algorithm, 'backup_num': backup_num}
        try:
            ret = self._connect("connectLink", self.tenant_url, data=req)
            linkId = ret.get('linkId')
            if linkId:
                log.info("Link with linkId %s has been created" % linkId)
            return linkId
        except OVXException as e:
              e.rollback = True
              e.tenantId = tenantId
              raise

    def setLinkPath(self, tenantId, linkId, path, priority):
        req = {'tenantId': tenantId, 'linkId': linkId, 'path': path, 'priority': priority}
        try:
            ret = self._connect("setLinkPath", self.tenant_url, data=req)
            if ret:
                log.info("Path on link %s has been set" % linkId)
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def connectHost(self, tenantId, vdpid, vport, mac):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport, 'mac': mac}
        try:
            ret = self._connect("connectHost", self.tenant_url, data=req)
            hostId = ret.get('hostId')
            if hostId:
                log.info("Host with hostId %s connected" % hostId)
            return hostId
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
            
    def connectRoute(self, tenantId, switchId, srcPort, dstPort, path):
        req = {'tenantId': tenantId, 'vdpid': switchId, 'srcPort': srcPort, 'dstPort': dstPort, 'path': path}
        try:
            ret = self._connect("connectRoute", self.tenant_url, data=req)
            routeId = reg.get('routeId')
            if routeId:
                log.info("Route with routeId %s on switch %s between ports (%s,%s) created" % (routeId, switchId, srcPort, dstPort))
            return routeId
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def createSwitchRoute(self, tenantId, switchId, srcPort, dstPort, path):
        req = {'tenantId': tenantId, 'dpid': switchId, 'srcPort': srcPort, 'dstPort': dstPort, 'path': path}
        try:
            ret = self._connect("createSwitchRoute", self.tenant_url, data=req)
            if ret:
                log.info("Route on switch %s between ports (%s,%s) created" % (switchId, srcPort, dstPort))
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def startNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        try:
            ret = self._connect("startNetwork", self.tenant_url, data=req)
            if ret:
                log.info("Network with tenantId %s has been started" % tenantId)
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def stopNetwork(self, tenantId):
        req = {'tenantId': tenantId}
        try:
            ret = self._connect("stopNetwork", self.tenant_url, data=req)
            if ret:
                log.info("Network with tenantId %s has been stopped" % tenantId)
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def startPort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        try:
            ret = self._connect("startPort", self.tenant_url, data=req)
            if ret:
                log.info("Port on network with tenantId %s, virtual switch id %s, and virtual port number %s has been started" % (tenantId, longToHex(vdpid), vport))
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise

    def stopPort(self, tenantId, vdpid, vport):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'vport': vport}
        try:
            ret = self._connect("stopPort", self.tenant_url, data=req)
            if ret:
                log.info("Port on network with tenantId %s, virtual switch id %s, and virtual port number %s has been stopped" % (tenantId, longToHex(vdpid), vport))
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
    def getPhysicalTopology(self):
        ret = self._connect("getPhysicalTopology", self.status_url)
        try:
            if ret:
                log.info("Physical network topology received")
            return ret
        except OVXException as e:
            e.rollback = False
            raise

    def setInternalRouting(self, tenantId, vdpid, algorithm, backup_num):
        req = {'tenantId': tenantId, 'vdpid': vdpid, 'algorithm': algorithm, 'backup_num': backup_num}
        try:
            ret = self._connect("setInternalRouting", self.tenant_url, data=req)
            if ret:
                log.info("Internal routing of switch %s has been set to %s" % (longToHex(vdpid), algorithm))
            return ret
        except OVXException as e:
            e.rollback = True
            e.tenantId = tenantId
            raise
        
class OVXEmbedderHandler(BaseHTTPRequestHandler):
    """
    Implementation of JSON-RPC API, defines all API handler methods.
    """
  
    def _buildResponse(self, json_id, result=None, error=None):
        """Returns JSON 2.0 compliant response"""
        res = {}
        res['jsonrpc'] = '2.0'
        # result and error are mutually exclusive
        if result is not None:
            res['result'] = result
        elif error is not None:
            res['error'] = error
        res['id'] = json_id
        return res

    def _buildError(self, code, message, data=None):
        """Returns JSON RPC 2.0 error object"""
        res = {}
        res['code'] = code
        res['message'] = message
        if data:
            res['data'] = data
        return res

    def doBigSwitchNetwork(self, controller, routing, subnet, hosts):
        """Create OVX network that is a single big switch"""
        
        client = self.server.client
        # request physical topology
        phyTopo = client.getPhysicalTopology()
        # spawn controller if necessary
        # TODO: do proper string comparison
        if controller['type'] == 'default':
            proto = self.server.ctrlProto
            host = self.server._spawnController()
            port = self.server.ctrlPort
            ctrls = ["%s:%s:%s" % (proto, host, port)]
        elif controller['type'] == 'custom':
            ctrls = controller['ctrls']
        else:
            raise EmbedderException(ERROR_CODE.INVALID_REQ, 'Unsupported controller type')
        # split subnet in netaddress and netmask
        (net_address, net_mask) = subnet.split('/')
        # create virtual network
        tenantId = client.createNetwork(ctrls, net_address, int(net_mask))
        # create virtual switch with all physical dpids
        dpids = [hexToLong(dpid) for dpid in phyTopo['switches']]
        switchId = client.createSwitch(tenantId, dpids)
        # set routing algorithm and number of backups
        client.setInternalRouting(tenantId, switchId, routing['algorithm'], routing['backup_num'])
        # create virtual ports and connect hosts
        for host in hosts:
            (vdpid, vport) = client.createPort(tenantId, hexToLong(host['dpid']), host['port'])
            client.connectHost(tenantId, vdpid, vport, host['mac'])
        # Start virtual network
        client.startNetwork(tenantId)

        return tenantId

    def doPhysicalNetwork(self, controller, routing, subnet, hosts, copyDpid = False):
        """Create OVX network that is clone of physical network"""
        
        client = self.server.client
        # request physical topology
        phyTopo = client.getPhysicalTopology()
        # spawn controller if necessary
        if controller['type'] == 'default':
            proto = self.server.ctrlProto
            host = self.server._spawnController()
            port = self.server.ctrlPort
            ctrls = ["%s:%s:%s" % (proto, host, port)]
        elif controller['type'] == 'custom':
            ctrls = controller['ctrls']
        else:
            raise EmbedderException(ERROR_CODE.INVALID_REQ, 'Unsupported controller type')
        # split subnet in netaddress and netmask
        (net_address, net_mask) = subnet.split('/')
        # create virtual network
        tenantId = client.createNetwork(ctrls, net_address, int(net_mask))
        # create virtual switch per physical dpid
        for dpid in phyTopo['switches']:
            if copyDpid:
                client.createSwitch(tenantId, [hexToLong(dpid)], dpid=hexToLong(dpid))
            else:
                client.createSwitch(tenantId, [hexToLong(dpid)])
        # create virtual ports and connect hosts
        for host in hosts:
            (vdpid, vport) = client.createPort(tenantId, hexToLong(host['dpid']), host['port'])
            client.connectHost(tenantId, vdpid, vport, host['mac'])
        # create virtual ports and connect virtual links
        connected = []
        for link in phyTopo['links']:
            if (link['src']['dpid'], link['src']['port']) not in connected:
                srcDpid = hexToLong(link['src']['dpid'])
                # Type conversions needed because OVX JSON output is stringified
                srcPort = int(link['src']['port'])
                (srcVDpid, srcVPort) = client.createPort(tenantId, srcDpid, srcPort)
                 
                dstDpid = hexToLong(link['dst']['dpid'])
                dstPort = int(link['dst']['port'])
                (dstVDpid, dstVPort) = client.createPort(tenantId, dstDpid, dstPort)
        
                src = "%s/%s" % (srcDpid, srcPort)
                dst = "%s/%s" % (dstDpid, dstPort)
        
                path = "%s-%s" % (src, dst)
                client.connectLink(tenantId, srcVDpid, srcVPort, dstVDpid, dstVPort, routing['algorithm'], routing['backup_num'])
                connected.append((link['dst']['dpid'], link['dst']['port']))
      
        # boot network
        client.startNetwork(tenantId)

        return tenantId

    def _exec_createNetwork(self, json_id, params):
        """Handler for automated network creation"""

        try:
            p = params.get('network')
            if p == None:
                raise EmbedderException(ERROR_CODE.INVALID_REQ, 'Missing network section')

            tenantId = -1

            networkType = p.get('type')
            if networkType == None:
                raise EmbedderException(ERROR_CODE.INVALID_REQ, 'Missing network type')
            elif networkType == 'bigswitch':
                tenantId = self.doBigSwitchNetwork(p['controller'], p['routing'], p['subnet'], p['hosts'])
            elif networkType == 'physical':
                tenantId = self.doPhysicalNetwork(p['controller'], p['routing'], p['subnet'], p['hosts'], copyDpid=p.get('copy-dpid', False))
            else:
                raise EmbedderException(ERROR_CODE.INVALID_REQ, 'Unsupported network type')
            response = self._buildResponse(json_id, result={ 'tenantId' : tenantId })
        except OVXException as e:
            if e.rollback:
                client = self.server.client
                client.removeNetwork(e.tenantId)
            err = self._buildError(e.code, e.msg)
            response = self._buildResponse(json_id, error=err)
        except EmbedderException as e:
            log.error(e)
            err = self._buildError(e.code, e.msg)
            response = self._buildResponse(json_id, error=err)
    
        return response

    def do_POST(self):
        """Handle HTTP POST calls"""

        def reply(response):
            response = json.dumps(response) + '\n'
            self.send_response(200, "OK")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.end_headers()
            self.wfile.write(response)
    
        # Put JSON message in data dict
        l = self.headers.get("Content-Length", "")
        data = ''
        if l == "":
            data = self.rfile.read()
        else:
            data = self.rfile.read(int(l))
        try:
            data = json.loads(data)
        except:
            msg = "Error parsing JSON request"
            log.error(msg)
            err = self._buildError(ERROR_CODE.PARSE_ERROR, msg)
            result = self._buildResponse(None, error=err)
        # Check if JSONRPC 2.0 compliant (correct version and json_id given)
        json_id = data.get('id', None)
        # Setup method to call
        try:
            methodName = "_exec_" + data.get('method')
            method = getattr(self, methodName)
            log.info(methodName)
        except:
            msg = "Method not found"
            log.info(msg)
            err = self._buildError(ERROR_CODE.METHOD_NOT_FOUND, msg)
            result = self._buildResponse(json_id, error=err)
        # Get method parameters
        params = data.get('params', {})
        # Call method
        result = method(json_id, params)

        reply(result)
