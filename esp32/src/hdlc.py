from micropython import const
from log import Logger

HDLC_ESC = const(0x7D)
HDLC_ESC_MASK = const(0x20)
HDLC_FLAG = const(0x7E)
MAX_SIZE = const(526) # TODO: some packets got discarded, think HDLC overhead

class HDLCProcessor:
    def __init__(self):
        self.log = Logger("HDLC")
        self.rx_buffer = bytearray()
        self.in_frame = False
        self.escape = False

    def _escape_hdlc(self, data: bytes) -> bytes:
        escaped = list()
        for byte in data:
            if byte == HDLC_ESC:
                escaped.extend([HDLC_ESC, HDLC_ESC ^ HDLC_ESC_MASK])
            elif byte == HDLC_FLAG:
                escaped.extend([HDLC_ESC, HDLC_FLAG ^ HDLC_ESC_MASK])
            else:
                escaped.append(byte)
        return bytes(escaped)

    def frame_data(self, data: bytes) -> bytes:
        if isinstance(data, str):
            data = data.encode()
        escaped = self._escape_hdlc(data)
        return bytes([HDLC_FLAG]) + escaped + bytes([HDLC_FLAG])

    def process_byte(self, byte: int) -> bytes:
        if byte == HDLC_FLAG:
            if self.in_frame and len(self.rx_buffer) > 0:
                frame = bytes(self.rx_buffer)
                self.rx_buffer = bytearray()
                self.in_frame = False
                self.escape = False
                return frame
            else:
                self.rx_buffer = bytearray()
                self.in_frame = True
                self.escape = False
                return None
                
        elif self.in_frame:
            if byte == HDLC_ESC:
                self.escape = True
                return None
            
            if self.escape:
                if byte == HDLC_FLAG ^ HDLC_ESC_MASK:
                    byte = HDLC_FLAG
                elif byte == HDLC_ESC ^ HDLC_ESC_MASK:
                    byte = HDLC_ESC
                self.escape = False
                
            self.rx_buffer.append(byte)
            
            if len(self.rx_buffer) > MAX_SIZE:
                self.log.error("Frame too long at %d, discarding", len(self.rx_buffer))
                self.rx_buffer = bytearray()
                self.in_frame = False
                self.escape = False
                
        return None