"""
CLPM OPC-UA Server  –  Simulates a real PLC/DCS tag namespace.
When connected to a real historian (Kepware, Prosys, etc.) replace
this with opcua_client.py which connects outward.
"""
from __future__ import annotations
import asyncio
import logging
import math
import random
import time
from datetime import datetime, timezone
from typing import Any

import yaml
from config import load_config
from asyncua import Server, ua
from asyncua.server.history_sql import HistorySQLite

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
# load_config expands any `${VAR:default}` placeholders so the YAML can be
# overridden via environment variables in containers / compose setups.
CFG = load_config()

OPCUA_CFG = CFG["opcua"]
TAGS: list[dict] = OPCUA_CFG["tags"]
ALARM_NS = OPCUA_CFG["alarms_events"]["namespace"]

# ─────────────────────────────────────────────────────────────────────────────
# Simulation helpers                                                            │
# ─────────────────────────────────────────────────────────────────────────────
class ControllerSimulator:
    """Simulates PID-loop dynamics for one controller."""

    def __init__(self, controller: str, ctrl_type: str):
        self.controller = controller
        self.ctrl_type = ctrl_type
        self.setpoint = self._default_sp()
        self.pv = self.setpoint + random.uniform(-0.1, 0.1)
        self.co = 50.0
        self.mode = "Auto"
        self.Kp = 0.8
        self.Ki = 0.05
        self.integral = 0.0
        self.noise_amp = 0.03
        self.drift = 0.0
        self._oscillation_phase = random.uniform(0, 2 * math.pi)

    def _default_sp(self) -> float:
        defaults = {
            "Pressure": 4.25,
            "Temperature": 120.0,
            "Flow": 50.0,
            "Level": 2.5,
        }
        return defaults.get(self.ctrl_type, 10.0)

    def step(self, dt: float = 1.0) -> tuple[float, float, float]:
        """Advance simulation one step. Returns (pv, sp, co)."""
        # Slow setpoint wander
        if random.random() < 0.001:
            self.setpoint += random.uniform(-0.2, 0.2)

        # Occasional process disturbance
        if random.random() < 0.005:
            self.drift = random.uniform(-0.5, 0.5)

        error = self.setpoint - self.pv
        self.integral += error * dt
        self.integral = max(-50, min(50, self.integral))

        if self.mode == "Auto":
            control = self.Kp * error + self.Ki * self.integral
            self.co = max(0, min(100, 50 + control * 10))

        # First-order process + noise + drift + oscillation
        oscillation = 0.15 * math.sin(
            2 * math.pi * time.time() / 120 + self._oscillation_phase
        )
        noise = random.gauss(0, self.noise_amp)
        self.pv += (0.2 * (self.co / 100 * self.setpoint * 1.5 - self.pv) + noise + oscillation + self.drift * 0.01) * dt
        self.drift *= 0.99  # decay

        return round(self.pv, 4), round(self.setpoint, 4), round(self.co, 4)


# ─────────────────────────────────────────────────────────────────────────────
# OPC-UA Server
# ─────────────────────────────────────────────────────────────────────────────
class CLPMOpcuaServer:
    def __init__(self):
        self.server = Server()
        self.simulators: dict[str, ControllerSimulator] = {}
        self.nodes: dict[str, Any] = {}  # node_id_str -> asyncua Variable
        self.alarm_nodes: dict[str, Any] = {}
        self.ns_idx: int = 2

    async def setup(self):
        await self.server.init()
        self.server.set_endpoint(OPCUA_CFG["server"]["endpoint"])
        self.server.set_server_name(OPCUA_CFG["server"]["name"])

        # Set up history (SQLite-backed) – we will enable it on each
        # variable after they are created. The previous attempt to
        # historize the root Objects folder (NodeId 85) raised
        # BadAttributeIdInvalid since that node does not support the
        # Historizing attribute. See asyncua docs: support is per-variable.
        # A few seconds later, after variables are added, we'll iterate and
        # invoke historize_node_data_change on each one.

        # Register namespace
        self.ns_idx = await self.server.register_namespace(
            OPCUA_CFG["server"]["namespace"]
        )
        alarm_ns_idx = await self.server.register_namespace(ALARM_NS)

        # Build folder structure
        root = self.server.get_objects_node()
        plant_folder = await root.add_folder(self.ns_idx, "PlantFloor")
        alarm_folder = await root.add_folder(alarm_ns_idx, "AlarmsAndEvents")

        # Group tags by controller
        controllers: dict[str, list[dict]] = {}
        for tag in TAGS:
            cid = tag["controller"]
            controllers.setdefault(cid, []).append(tag)

        for controller_id, ctags in controllers.items():
            ctype = ctags[0]["type"]
            ctrl_folder = await plant_folder.add_folder(
                self.ns_idx, controller_id
            )
            sim = ControllerSimulator(controller_id, ctype)
            self.simulators[controller_id] = sim

            for tag in ctags:
                # the configuration node_id strings include a namespace prefix
                # (e.g. "ns=2;s=PIC-001.PV").  asyncua's NodeId constructor
                # does not parse that format when passed a namespace index as
                # the second argument, which results in malformed identifiers
                # and subsequent 'parent node does not exist' errors.  Use
                # from_string() and then force our freshly-registered namespace
                # index (self.ns_idx) so we don't rely on a hardcoded value.
                signal = tag["node_id"].split(".")[-1]  # PV / SP / CO
                try:
                    parsed = ua.NodeId.from_string(tag["node_id"])
                    # construct a new NodeId with our registered namespace index
                    nodeid = ua.NodeId(parsed.Identifier, self.ns_idx, parsed.NodeIdType)
                except Exception:
                    # fallback parsing in case the string is badly formed
                    # (shouldn't happen in normal config).
                    parts = tag["node_id"].split(";")
                    identifier = parts[-1]
                    if identifier.startswith("s="):
                        identifier = identifier[2:]
                    elif identifier.startswith("i="):
                        try:
                            identifier = int(identifier[2:])
                        except ValueError:
                            pass
                    nodeid = ua.NodeId(identifier, self.ns_idx)
                log.debug("adding variable %s under controller %s with nodeid %s", signal, controller_id, nodeid)
                var = await ctrl_folder.add_variable(
                    nodeid,
                    signal,
                    0.0,
                )
                await var.set_writable()
                self.nodes[tag["node_id"]] = var

        # enable history after all variables have been created
        for node_key, var in self.nodes.items():
            try:
                # historize_node_data_change can raise BadAttributeIdInvalid if
                # the target node is not a variable or otherwise does not
                # support the Historizing attribute.  We already catch
                # exceptions here, but log the node class for diagnostics.
                await self.server.historize_node_data_change(var, period=None, count=86400)
            except Exception as exc:  # pragma: no cover - rarely happens
                try:
                    nclass = await var.read_node_class()
                except Exception:
                    nclass = "<unknown>"
                log.warning("could not historize %s (class=%s): %s", node_key, nclass, exc)

        # create alarm folders/objects once per controller (not once per variable)
        for controller_id in controllers.keys():
            alarm_obj = await alarm_folder.add_object(
                alarm_ns_idx, f"{controller_id}_Alarms"
            )
            self.alarm_nodes[controller_id] = alarm_obj

        log.info("OPC-UA server namespace built. %d tags registered.", len(self.nodes))

    async def _publish_alarms(self, controller_id: str, pv: float, sp: float):
        """Emit an OPC-UA Alarm & Event condition when deviation is large."""
        deviation = abs(pv - sp)
        deviation_pct = (deviation / abs(sp)) * 100 if sp != 0 else 0

        if deviation_pct > 30:
            severity = 900 if deviation_pct > 50 else 700
            msg = (
                f"{controller_id}: HIGH deviation {deviation_pct:.1f}% "
                f"(PV={pv:.3f}, SP={sp:.3f})"
            )
            log.warning("ALARM [%s] %s", controller_id, msg)
            # In a production server, you would fire a ConditionType event here
            # using server.get_event_generator() with the appropriate alarm class

    async def _simulation_loop(self):
        """Update all simulated tags at 1 Hz."""
        while True:
            ts = datetime.now(timezone.utc)
            for ctrl_id, sim in self.simulators.items():
                pv, sp, co = sim.step(dt=1.0)
                base = f"ns=2;s={ctrl_id}"
                for sig, val in [("PV", pv), ("SP", sp), ("CO", co)]:
                    node_key = f"{base}.{sig}"
                    if node_key in self.nodes:
                        # construct DataValue explicitly to avoid incompatible
                        # constructor kwargs (asyncua v0.31+ dropped `Status`)
                        dv = ua.DataValue(
                            Value=ua.Variant(val, ua.VariantType.Double),
                            StatusCode_=ua.StatusCode(ua.StatusCodes.Good),
                            SourceTimestamp=ts,
                            ServerTimestamp=ts,
                        )
                        await self.nodes[node_key].write_value(dv)
                await self._publish_alarms(ctrl_id, pv, sp)
            await asyncio.sleep(1.0)

    async def run(self):
        await self.setup()
        async with self.server:
            log.info(
                "OPC-UA server running at %s",
                OPCUA_CFG["server"]["endpoint"],
            )
            await self._simulation_loop()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(CLPMOpcuaServer().run())
