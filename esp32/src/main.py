import network
import espnow
import asyncio
from machine import Pin, Timer, UART, WDT
import machine
import sys
import time
import aioespnow

# Log levels
LOG_DEBUG = const(10)
LOG_INFO = const(20)
LOG_WARNING = const(30)
LOG_ERROR = const(40)
LOG_CRITICAL = const(50)

# Hardware Constants
PIN_LED = const(10)
PIN_BTN = const(37)
PIN_TX = const(26)
PIN_RX = const(25)
LED_ON = const(0)
LED_OFF = const(1)

# Protocol Constants
BROADCAST_MAC = b'\xff' * 6
HDLC_ESC = const(0x7D)
HDLC_ESC_MASK = const(0x20)
HDLC_FLAG = const(0x7E)

GROUP_ID = b'RNS1'
PING_FRAME = GROUP_ID + b'PING'
PROBE_FRAME = GROUP_ID + b'PROBE'
PROBE_RESPONSE = GROUP_ID + b'ACK'

RNS_MTU = const(500)
SCAN_ATTEMPTS = const(3)
SCAN_TIMEOUT_MS = const(500)
UART_BUFFER_SIZE = const(1024)
UART_NUM = const(1)
WIFI_CHANNEL = const(3)
SLEEP_SHORT = const(5)
SLEEP_MEDIUM = const(10)
PREFERRED_CHANNELS = (1,6,11)

class Logger:
    def __init__(self, name):
        self.name = name
        self.level = LOG_DEBUG

    def _log(self, level, msg, *args):
        if level >= self.level:
            if args:
                msg = msg % args
            print("[{:010d}] {:8s} - {} - {}".format(
                time.ticks_ms(), 
                self._level_name(level),
                self.name,
                msg
            ))

    def _level_name(self, level):
        if level == LOG_DEBUG: return "DEBUG"
        if level == LOG_INFO: return "INFO"
        if level == LOG_WARNING: return "WARNING"
        if level == LOG_ERROR: return "ERROR"
        if level == LOG_CRITICAL: return "CRITICAL"
        return "UNKNOWN"

    def debug(self, msg, *args): self._log(LOG_DEBUG, msg, *args)
    def info(self, msg, *args): self._log(LOG_INFO, msg, *args)
    def warning(self, msg, *args): self._log(LOG_WARNING, msg, *args)
    def error(self, msg, *args): self._log(LOG_ERROR, msg, *args)
    def critical(self, msg, *args): self._log(LOG_CRITICAL, msg, *args)
    def exc(self, e, msg=None):
        if msg:
            self.error(msg)
        sys.print_exception(e)

class RetiESPNOW:
    def __init__(self, baud=115200):
        self.log = Logger("RetiESPNOW")
        self.log.info("Initializing ESP-NOW interface")
        
        self.watchdog = WDT(timeout=8000)
        
        self.baud = baud
        self.uart = None
        
        # Initialize peripherals
        self.led = Pin(PIN_LED, Pin.OUT)
        self.btn = Pin(PIN_BTN, Pin.IN)
        self.log.debug("Peripherals initialized")
        
        # Initialize WiFi in Station mode
        try:
            self.sta = network.WLAN(network.STA_IF)
            self.sta.active(True)
            self.log.debug("WiFi initialized in station mode")
        except Exception as e:
            self.log.exc(e, "Failed to initialize WiFi")
            machine.reset()
        
        # Initialize ESP-NOW
        try:
            self.espnow = aioespnow.AIOESPNow()
            self.espnow.active(True)
        except Exception as e:
            self.log.exc(e, "Failed to initialize ESP-NOW")
            machine.reset()
        
        # Initial channel configuration
        self.current_channel = WIFI_CHANNEL
        self.sta.config(channel=self.current_channel)
        self.sta.config(protocol=network.MODE_LR)
        self.sta.config(pm=self.sta.PM_PERFORMANCE)
        self.log.info("WiFi configured - initial channel %d", self.current_channel)

        # Add broadcast peer
        try:
            self.espnow.add_peer(BROADCAST_MAC)
            self.log.debug("Broadcast peer configured")
        except Exception as e:
            self.log.exc(e, "Failed to add broadcast peer")
            machine.reset()
        
        # Initialize HDLC buffers
        self.rx_buffer = bytearray()
        self.uart_buffer = bytearray()
        self.in_frame = False
        self.escape = False
        
        # Start button polling timer
        self.btn_timer = Timer(1)
        self.btn_timer.init(period=50, mode=Timer.PERIODIC, callback=self._check_buttons)
        
        # Start channel scan
        asyncio.create_task(self._initial_channel_scan())

    async def _initial_channel_scan(self):
        """Scan all channels to find peers"""
        self.log.info("Starting channel scan")
        best_channel = WIFI_CHANNEL
        max_responses = 0

        # Scan preferred channels first, then others
        channels = list(PREFERRED_CHANNELS)
        channels.extend(ch for ch in range(1, 14) if ch not in PREFERRED_CHANNELS)

        for channel in channels:
            responses = 0
            self.sta.config(channel=channel)
            self.log.debug("Scanning channel %d", channel)

            for _ in range(SCAN_ATTEMPTS):
                try:
                    await self.send_espnow(PROBE_FRAME)
                    scan_end = time.ticks_add(time.ticks_ms(), SCAN_TIMEOUT_MS)
                    
                    while time.ticks_diff(scan_end, time.ticks_ms()) > 0:
                        try:
                            mac, msg = await self.espnow.arecv()
                            if msg == self._frame_data(PROBE_RESPONSE):
                                responses += 1
                                self.log.debug("Probe response on channel %d", channel)
                        except:
                            pass
                    await asyncio.sleep_ms(SLEEP_SHORT)
                except Exception as e:
                    self.log.exc(e, "Error during channel scan")

            if responses > max_responses:
                max_responses = responses
                best_channel = channel
                
        self.current_channel = best_channel
        self.sta.config(channel=best_channel)
        if max_responses > 0:
            self.log.info("Found %d peers on channel %d", max_responses, best_channel)
        else:
            self.log.info("No peers found, using default channel %d", best_channel)

    async def _blink_led(self, times=1, on_ms=50, off_ms=50):
        """Blink LED a number of times"""
        for _ in range(times):
            self.led.value(LED_ON)
            await asyncio.sleep_ms(on_ms)
            self.led.value(LED_OFF)
            await asyncio.sleep_ms(off_ms)

    def _check_buttons(self, _):
        """Check button states and send ping if pressed"""
        if self.btn.value() == 0:
            asyncio.create_task(self._send_ping())
    
    async def _send_ping(self):
        """Send ping frame and blink LED"""
        try:
            self.log.debug("Sending ping frame")
            await self.send_espnow(PING_FRAME)
            await self._blink_led(3, 50, 50)
        except Exception as e:
            self.log.exc(e, "Failed to send ping")
        
    def _escape_hdlc(self, data: bytes) -> bytes:
        """Escape HDLC control characters in data"""
        escaped = list()
        for byte in data:
            if byte == HDLC_ESC:
                escaped.extend([HDLC_ESC, HDLC_ESC ^ HDLC_ESC_MASK])
            elif byte == HDLC_FLAG:
                escaped.extend([HDLC_ESC, HDLC_FLAG ^ HDLC_ESC_MASK])
            else:
                escaped.append(byte)
        return bytes(escaped)

    async def send_espnow(self, data: bytes) -> bool:
        """Send framed data via ESP-NOW broadcast"""
        if not isinstance(data, (bytes, bytearray)):
            self.log.error("Data must be bytes or bytearray")
            return False
            
        if len(data) > RNS_MTU:
            self.log.error("Packet exceeds MTU: %d > %d", len(data), RNS_MTU)
            return False
            
        framed = self._frame_data(data)
        asyncio.create_task(self._blink_led(1, 10, 0))
        
        try:
            await self.espnow.asend(BROADCAST_MAC, framed)
            self.log.debug("Sent %d bytes", len(data))
            return True
        except Exception as e:
            self.log.exc(e, "Failed to send data")
            return False

    def _frame_data(self, data: bytes) -> bytes:
        """Frame data with HDLC flags and escaping"""
        if isinstance(data, str):
            data = data.encode()
        escaped = self._escape_hdlc(data)
        return bytes([HDLC_FLAG]) + escaped + bytes([HDLC_FLAG])

    def _process_byte(self, byte: int) -> bytes:
        """Process a single byte according to HDLC framing, return complete frame or None"""
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
            
            if len(self.rx_buffer) > RNS_MTU:
                self.log.error("Frame too long, discarding")
                self.rx_buffer = bytearray()
                self.in_frame = False
                self.escape = False
                
        return None

    async def process_uart(self):
        """Process UART input and broadcast via ESP-NOW"""  
        self.log.info("Starting UART processing")
        uart_index = 0
        
        while True:
            self.watchdog.feed()
            
            if not self.uart:
                await asyncio.sleep_ms(SLEEP_MEDIUM)
                continue
                
            if self.uart.any():
                data = self.uart.read()
                if data and len(data) > 0:  # Check for valid data
                    self.log.debug("Read %d bytes from UART", len(data))
                    for byte in data:
                        self.uart_buffer.append(byte)

                    while uart_index < len(self.uart_buffer):
                        frame = self._process_byte(self.uart_buffer[uart_index])
                        uart_index += 1
                        if frame:
                            self.log.debug("Complete frame from UART (%d bytes)", len(frame))
                            await self.send_espnow(frame)
                    
                    # Reset buffer after processing
                    if uart_index >= len(self.uart_buffer):
                        self.uart_buffer = bytearray()
                        uart_index = 0
                        
            await asyncio.sleep_ms(SLEEP_MEDIUM)

    async def process_espnow(self):
        """Process ESP-NOW messages and send to UART"""
        self.log.info("Starting ESP-NOW processing")
        while True:
            self.watchdog.feed()
            
            if not self.uart:
                try:
                    self.uart = machine.UART(UART_NUM, tx=PIN_TX, rx=PIN_RX, 
                        baudrate=self.baud, timeout=0, timeout_char=0, rxbuf=UART_BUFFER_SIZE)
                    self.log.info("Initialized UART%d (TX:%d, RX:%d, %d baud)", 
                        UART_NUM, PIN_TX, PIN_RX, self.baud)
                except Exception as e:
                    self.log.exc(e, "Failed to initialize UART")
                await asyncio.sleep_ms(SLEEP_MEDIUM)
                continue
                
            try:
                mac, msg = await self.espnow.arecv()
                mac_str = "".join(f"{b:02x}" for b in mac)
                self.log.debug("Received %d bytes from %s", len(msg), mac_str)
                
                asyncio.create_task(self._blink_led(1, 10, 0))
                
                if msg == self._frame_data(PING_FRAME):
                    self.log.info("Ping frame received")
                    await self._blink_led(3, 50, 50)
                elif msg == self._frame_data(PROBE_FRAME):
                    await self.send_espnow(PROBE_RESPONSE)
                    self.log.debug("Probe request received, sent response")
                elif mac != BROADCAST_MAC:
                    self.uart.write(msg)
                    self.log.debug("Forwarded %d bytes to UART", len(msg))
            except Exception as e:
                self.log.exc(e, "Error processing ESP-NOW message")
            await asyncio.sleep_ms(SLEEP_MEDIUM)

async def main():
    """Main interface loop"""
    log = Logger("Main")
    log.info("Starting interface")
    
    try:
        reti = RetiESPNOW()
        uart_task = asyncio.create_task(reti.process_uart())
        espnow_task = asyncio.create_task(reti.process_espnow())
        await asyncio.gather(uart_task, espnow_task)
    except Exception as e:
        log.exc(e, "Fatal error - resetting")
        machine.reset()

try:
    asyncio.run(main())
except Exception as e:
    Logger("Startup").exc(e, "Failed to start - resetting")
    machine.reset()
