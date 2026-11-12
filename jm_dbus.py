"""Handles BlueZ D-Bus access for JoustMania processes. Each process uses a
private system-bus connection because inherited connections can fail after
multiprocessing forks or BlueZ restarts during controller pairing.
"""
import logging
import os
import subprocess
import dbus
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

BUS = None
BUS_PID = None
ORG_BLUEZ = 'org.bluez'
ORG_BLUEZ_PATH = '/org/bluez'


def ensure_process_bus():
    """Returns a connected private system-bus connection owned by current
    process. PID and connection checks prevent forked workers from reusing
    inherited D-Bus state.
    """
    global BUS, BUS_PID
    if (
        BUS is None
        or BUS_PID != os.getpid()
        or not BUS.get_is_connected()
    ):
        BUS = dbus.SystemBus(private=True)
        BUS_PID = os.getpid()
    return BUS


def reconnect_bus():
    """Discards cached D-Bus state and creates a private connection for current
    process. Pairing can restart BlueZ and invalidate an existing connection.
    """
    global BUS, BUS_PID
    BUS = None
    BUS_PID = None
    return ensure_process_bus()

def get_hci_dict():
    """Returns HCI adapter names mapped to Bluetooth addresses through BlueZ
    ObjectManager. A disconnected bus triggers one replacement and retry so
    adapter discovery can recover after a BlueZ restart.
    """
    for attempt in range(2):
        try:
            bus = ensure_process_bus()
            # Do not auto-start absent BlueZ: activation can block for 25 seconds.
            if not bus.name_has_owner(ORG_BLUEZ):
                return {}
            root = bus.get_object(ORG_BLUEZ, '/', introspect=False)
            manager = dbus.Interface(root, 'org.freedesktop.DBus.ObjectManager')
            objects = manager.GetManagedObjects(timeout=1)
            return {
                str(path).rsplit('/', 1)[-1]: str(properties['Address'])
                for path, interfaces in objects.items()
                for properties in [interfaces.get('org.bluez.Adapter1')]
                if properties is not None and 'Address' in properties
            }
        except dbus.DBusException:
            if attempt == 0:
                reconnect_bus()
                continue
            raise

def get_attached_addresses(hci):
    """Get the addresses of devices known by hci"""
    proxy = get_adapter_proxy(hci)
    devices = get_node_child_names(proxy)

    known_devices = []
    for dev in devices:
        proxy2 = get_device_proxy(hci, dev)

        dev_addr = str(get_device_attrib(proxy2, 'Address'))
        known_devices.append(dev_addr)

    return known_devices

def get_bus():
    """Get DBus hook"""
    return ensure_process_bus()

def get_root_proxy():
    """Get root Bluez DBus node"""
    return ensure_process_bus().get_object(ORG_BLUEZ, ORG_BLUEZ_PATH)

def enable_pairable(hci):
    """Allow devices to pair with the HCI"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if not iface.Get('org.bluez.Adapter1', 'Pairable'):
        iface.Set('org.bluez.Adapter1', 'Pairable', True)

def disable_pairable(hci):
    """Prevent devices from pairing with the HCI"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if iface.Get('org.bluez.Adapter1', 'Pairable'):
        iface.Set('org.bluez.Adapter1', 'Pairable', False)

def get_discovery_filters(hci):
    """Get information about discovery options"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    return iface.GetDiscoveryFilters()

def start_discovery(hci):
    """Start scanning for devices"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    if not get_adapter_attrib(proxy, 'Discovering').real:
        try:
            return iface.StartDiscovery()
        except dbus.exceptions.DBusException as e:
            if "InProgress" in str(e) or "NotReady" in str(e):
                pass
            else:
                raise e

def stop_discovery(hci):
    """Stop scanning for devices"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.bluez.Adapter1')
    if get_adapter_attrib(proxy, 'Discovering').real:
        try:
            return iface.StopDiscovery()
        except dbus.exceptions.DBusException as e:
            if "InProgress" in str(e) or "NotReady" in str(e):
                pass
            else:
                raise e

def remove_device(hci, dev):
    hci_proxy = get_adapter_proxy(hci)
    dev_proxy = get_device_proxy(hci, dev)
    iface = dbus.Interface(hci_proxy, 'org.bluez.Adapter1')
    return iface.RemoveDevice(dev_proxy)

def enable_adapter(hci):
    """Set the HCI's Powered attribute to true"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if iface.Get('org.bluez.Adapter1', 'Powered').real:
        return False
    else:
        try:
            print('Enabling adapter')
            iface.Set('org.bluez.Adapter1', 'Powered', True)
            return True
        except dbus.exceptions.DBusException as e:
            if "rfkill" not in str(e) or not rfkill_unblock(hci):
                raise
            # One retry only: if the adapter is still blocked, the caller's reset handles it.
            iface.Set('org.bluez.Adapter1', 'Powered', True)
            return True

def rfkill_unblock(hci):
    """Unblocks the radio rfkill lists for the HCI. Returns False, after logging why,
    if that didn't work."""
    listing = subprocess.run(["rfkill", "list"], capture_output=True, text=True)
    if listing.returncode != 0:
        logger.warning("Couldn't list rfkill radios: %s", listing.stderr.strip())
        return False
    rfkill_id = _rfkill_id(listing.stdout, hci)
    if rfkill_id is None:
        logger.warning("rfkill lists no radio for %s", hci)
        return False
    unblock = subprocess.run(["rfkill", "unblock", rfkill_id], capture_output=True, text=True)
    if unblock.returncode != 0:
        logger.warning("Couldn't unblock %s: %s", hci, unblock.stderr.strip())
        return False
    return True

def _rfkill_id(listing, hci):
    """Finds the id on a line such as "0: hci0: Bluetooth"."""
    for line in listing.splitlines():
        fields = line.split(":")
        if len(fields) >= 2 and fields[1].strip() == hci:
            return fields[0].strip()
    return None

def disable_adapter(hci):
    """Set the HCI's Powered attribute to false"""
    proxy = get_adapter_proxy(hci)
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    if iface.Get('org.bluez.Adapter1', 'Powered').real:
        iface.Set('org.bluez.Adapter1', 'Powered', False)
        return True
    else:
        return False

def get_adapter_proxy(hci):
    """Abstract getting Bluez DBus adapter nodes"""
    hci_path = os.path.join(ORG_BLUEZ_PATH, hci)
    return ensure_process_bus().get_object(ORG_BLUEZ, hci_path)

def get_device_proxy(hci, dev):
    """Abstract getting Bluez DBus device nodes"""
    device_path = os.path.join(ORG_BLUEZ_PATH, hci, dev)
    return ensure_process_bus().get_object(ORG_BLUEZ, device_path)

def get_bluez_attrib(proxy, kind, attrib):
    """Abstract getting attributes from Bluez DBus Interfaces"""
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    return iface.Get('org.bluez.{0}'.format(kind), attrib)

def get_adapter_attrib(proxy, attrib):
    """Abstract getting attributes from Bluez Adapter1 Interfaces"""
    return get_bluez_attrib(proxy, 'Adapter1', attrib)

def get_device_attrib(proxy, attrib):
    """Abstract getting attributes from Bluez Device1 Interfaces"""
    return get_bluez_attrib(proxy, 'Device1', attrib)

def get_device_properties(proxy):
    """Returns properties exposed by a BlueZ Device1 object so controller reset
    tools can identify PS Move devices without removing unrelated devices.
    """
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Properties')
    return iface.GetAll('org.bluez.Device1')

def _introspect_tree(proxy):
    """Return parsed introspection tree for a DBus node"""
    iface = dbus.Interface(proxy, 'org.freedesktop.DBus.Introspectable')
    return ElementTree.fromstring(iface.Introspect())


def get_node_child_names(proxy):
    """Abstract finding child nodes of a DBus Node"""
    tree = _introspect_tree(proxy)
    return [child.attrib['name'] for child in tree if child.tag == 'node']


def get_node_interfaces(proxy):
    """List interface names exposed by a DBus node"""
    tree = _introspect_tree(proxy)
    return [child.attrib['name'] for child in tree if child.tag == 'interface']


def get_connected_device_addresses():
    """Return current BlueZ links; propagate failure instead of reporting none."""
    bus = ensure_process_bus()
    if not bus.name_has_owner(ORG_BLUEZ):
        raise dbus.DBusException('BlueZ is temporarily unavailable')
    root = bus.get_object(ORG_BLUEZ, '/')
    objects = dbus.Interface(root, 'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=1)
    return {
        str(properties['Address']).upper()
        for interfaces in objects.values()
        for properties in [interfaces.get('org.bluez.Device1', {})]
        if properties.get('Connected') and properties.get('Address')
    }
