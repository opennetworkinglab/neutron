from sqlalchemy import func
from sqlalchemy.orm import exc

import neutron.db.api as db
from neutron.plugins.ovx import ovx_models

import opencloud_models_v2

def get_port_forwarding(session, port_id):
    session = session or db.get_session()
    try:
        forward = (session.query(opencloud_models_v2.PortForwarding).
                   filter_by(port_id=port_id).one())
        return forward['forward_ports']
    except exc.NoResultFound:
        return

def clear_port_forwarding(session, port_id):
    with session.begin(subtransactions=True):
        try:
            # Get rid of old port bindings
            forward = (session.query(opencloud_models_v2.PortForwarding).
                       filter_by(port_id=port_id).one())
            if forward:
                session.delete(forward)
        except exc.NoResultFound:
            pass

def add_port_forwarding(session, port_id, forward_ports):
    with session.begin(subtransactions=True):
        forward = opencloud_models_v2.PortForwarding(port_id, forward_ports)
        session.add(forward)

def set_port_profile_binding(session, port_id, bridge):
    """Set the port profile binding."""
    query = session.query(ovx_models.PortProfileBinding)
    result = query.filter_by(port_id=port_id).one()
    result['bridge'] = bridge
    session.merge(result)
    session.flush()
