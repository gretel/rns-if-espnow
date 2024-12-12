from micropython import const
import struct
from log import Logger

# Protocol Constraints
RNS_MTU = const(500)       # Required RNS packet size
ESPNOW_MTU = const(250)    # ESP-NOW physical limit
FRAG_HEADER = const(2)     # Control(1) + Count(1)
FRAG_PAYLOAD = const(248)  # ESPNOW_MTU - FRAG_HEADER
MAX_FRAGS = const(3)       # Ceiling(500/248) = 3

# Fragment Control
CTRL_START = const(0x80)  # First fragment flag
CTRL_END = const(0x40)    # Last fragment flag
CTRL_SEQ = const(0x3F)    # Sequence number mask

class Fragmentor:
    def __init__(self):
        self.log = Logger("Fragment")
        self._reassembly = {}

    def fragment_data(self, data: bytes) -> list[bytes]:
        if not data:
            return []

        # Fast path for small packets
        if len(data) <= ESPNOW_MTU:
            return [data]

        # Determine fragment count
        total_frags = (len(data) + FRAG_PAYLOAD - 1) // FRAG_PAYLOAD
        if total_frags > MAX_FRAGS:
            self.log.error(f"Packet requires {total_frags} fragments (max {MAX_FRAGS})")
            return []

        # Generate fragments
        fragments = []
        offset = 0
        for seq in range(total_frags):
            # Extract payload chunk
            payload = data[offset:offset + FRAG_PAYLOAD]
            
            # Build control byte
            ctrl = seq & CTRL_SEQ
            if seq == 0: ctrl |= CTRL_START
            if seq == total_frags - 1: ctrl |= CTRL_END
            
            # Construct fragment
            fragment = bytes([ctrl, total_frags]) + payload
            fragments.append(fragment)
            offset += len(payload)
            
        return fragments

    def process_fragment(self, fragment: bytes) -> bytes | None:
        if len(fragment) < FRAG_HEADER:
            return None
            
        # Extract header
        ctrl, count = fragment[0], fragment[1]
        seq = ctrl & CTRL_SEQ
        payload = fragment[FRAG_HEADER:]

        # Handle start fragment
        if ctrl & CTRL_START:
            if seq != 0:
                self.log.warning("Invalid start sequence")
                return None
            self._reassembly = {0: payload}
            return None

        # Store fragment if part of reassembly
        if seq < count:
            if seq not in self._reassembly:
                self._reassembly[seq] = payload

        # Check for completion
        if ctrl & CTRL_END:
            try:
                # Validate sequence
                if len(self._reassembly) != count:
                    return None

                # Reassemble packet
                packet = bytearray()
                for i in range(count):
                    if i not in self._reassembly:
                        return None
                    packet.extend(self._reassembly[i])
                return bytes(packet)

            except Exception as e:
                self.log.exc(e, "Reassembly failed")
            finally:
                self._reassembly.clear()
                
        return None