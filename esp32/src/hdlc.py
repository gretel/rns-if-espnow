from micropython import const
from log import Logger

# Protocol Constants
HDLC_FLAG = const(0x7E)  # Frame boundary marker
HDLC_ESC = const(0x7D)   # Escape sequence identifier
HDLC_ESC_MASK = const(0x20)  # Escape bit modification

class HDLCProcessor:
    """High-level Data Link Control protocol implementation"""
    def __init__(self):
        self.log = Logger("HDLC")
        self.rx_buffer = bytearray()
        self.in_frame = False
        self.escape = False
        
    def frame_data(self, data: bytes) -> bytes:
        """Wrap data in HDLC frame with escape sequences"""
        if isinstance(data, str):
            data = data.encode()
        escaped = self._escape_hdlc(data)
        return bytes([HDLC_FLAG]) + escaped + bytes([HDLC_FLAG])
        
    def process_byte(self, byte: int) -> bytes:
        """Process byte stream into HDLC frames"""
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

        return None

    def _escape_hdlc(self, data: bytes) -> bytes:
        """Apply HDLC escape sequences to data"""
        escaped = list()
        for byte in data:
            if byte == HDLC_ESC:
                escaped.extend([HDLC_ESC, HDLC_ESC ^ HDLC_ESC_MASK])
            elif byte == HDLC_FLAG:
                escaped.extend([HDLC_ESC, HDLC_FLAG ^ HDLC_ESC_MASK])
            else:
                escaped.append(byte)
        return bytes(escaped)