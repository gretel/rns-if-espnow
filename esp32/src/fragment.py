from micropython import const
import struct
from log import Logger

ESPNOW_MTU = const(250)       # ESP-NOW physical limit
FRAGMENT_HEADER_SIZE = const(4)  # flags(1) + packet_id(2) + sequence(1)
FRAGMENT_MAX_PAYLOAD = const(100) # ESPNOW_MTU minus header and safety margin
FLAG_FIRST = const(0x80)
FLAG_LAST = const(0x40)

class Fragmentor:
    def __init__(self):
        self.log = Logger("Fragment")
        self._packet_id = 0
        self._reassembly_buffers = {}
        
    def _next_packet_id(self):
        self._packet_id = (self._packet_id + 1) & 0xFFFF
        return self._packet_id
        
    def fragment_data(self, data: bytes) -> list[bytes]:
        if len(data) <= ESPNOW_MTU:
            return [data]
            
        packet_id = self._next_packet_id()
        fragments = []
        offset = 0
        sequence = 0
        
        while offset < len(data):
            payload = data[offset:offset + FRAGMENT_MAX_PAYLOAD]
            flags = 0
            
            if offset == 0:
                flags |= FLAG_FIRST
            if offset + len(payload) >= len(data):
                flags |= FLAG_LAST
                
            header = struct.pack(">BHB", flags, packet_id, sequence)
            fragments.append(header + payload)
            
            offset += len(payload)
            sequence += 1
            
        return fragments
        
    def process_fragment(self, fragment: bytes) -> bytes | None:
        if len(fragment) < FRAGMENT_HEADER_SIZE:
            return None
            
        flags, packet_id, sequence = struct.unpack(">BHB", fragment[:FRAGMENT_HEADER_SIZE])
        payload = fragment[FRAGMENT_HEADER_SIZE:]
        
        if flags & FLAG_FIRST:
            self._reassembly_buffers[packet_id] = {
                "fragments": {sequence: payload},
                "total_fragments": None
            }
            return None
            
        if packet_id not in self._reassembly_buffers:
            return None
            
        buffer = self._reassembly_buffers[packet_id]
        buffer["fragments"][sequence] = payload
        
        if flags & FLAG_LAST:
            try:
                total_size = sum(len(f) for f in buffer["fragments"].values())
                assembled = bytearray(total_size)
                pos = 0
                
                for i in range(len(buffer["fragments"])):
                    if i not in buffer["fragments"]:
                        return None
                    fragment_data = buffer["fragments"][i]
                    assembled[pos:pos + len(fragment_data)] = fragment_data
                    pos += len(fragment_data)
                    
                del self._reassembly_buffers[packet_id]
                return bytes(assembled)
            except:
                pass
                
        return None