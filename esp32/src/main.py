from micropython import const
import gc
import network
import asyncio
from machine import UART, WDT
import machine
import time
import aioespnow

from hardware import Hardware, PIN_TX, PIN_RX
from hdlc import HDLCProcessor, HDLC_FLAG
from fragment import Fragmentor
from log import Logger

# Protocol Identity
GROUP_ID = b'RNS09'
PING_FRAME = GROUP_ID + b'PING'
PROBE_FRAME = GROUP_ID + b'PROBE'
PROBE_RESPONSE = GROUP_ID + b'ACK'
BROADCAST_MAC = b'\xff' * 6

# Interface Configuration
UART_BUFFER_SIZE = const(2048)  # Generous buffer for reassembly
UART_NUM = const(1)
WIFI_CHANNEL = const(5)
SCAN_ATTEMPTS = const(3)
SCAN_TIMEOUT_MS = const(500)
SLEEP_SHORT = const(5)
SLEEP_MEDIUM = const(10)
PREFERRED_CHANNELS = (1, 6, 11)

class RNSNOW:
    """Reticulum Network Stack over ESP-NOW bridge"""
    def __init__(self, baud=115200):
        self.log = Logger("RNS-NOW")
        self.log.info("Initializing ESP-NOW interface for Reticulum")

        # Core components
        self.watchdog = WDT(timeout=8000)
        self.baud = baud
        self.uart = None
        self.uart_buffer = bytearray()

        # Protocol handlers
        self.hdlc = HDLCProcessor()
        self.fragmentor = Fragmentor()
        self.hw = Hardware(self._send_ping)

        # Network initialization
        self._init_network()
        asyncio.create_task(self._initial_channel_scan())
        
    def _init_network(self):
        """Initialize WiFi and ESP-NOW interfaces"""
        try:
            self.sta = network.WLAN(network.STA_IF)
            self.sta.active(True)
            self.log.debug("WiFi initialized in station mode")
        except Exception as e:
            self.log.exc(e, "Failed to initialize WiFi")
            machine.reset()

        try:
            self.espnow = aioespnow.AIOESPNow()
            self.espnow.active(True)
        except Exception as e:
            self.log.exc(e, "Failed to initialize ESP-NOW")
            machine.reset()

        self.current_channel = WIFI_CHANNEL
        self.sta.config(channel=self.current_channel)
        self.sta.config(protocol=network.MODE_LR)
        self.sta.config(pm=self.sta.PM_NONE)
        self.log.info("WiFi configured - channel %d", self.current_channel)

        try:
            self.espnow.add_peer(BROADCAST_MAC)
            self.log.debug("Broadcast peer configured")
        except Exception as e:
            self.log.exc(e, "Failed to add broadcast peer")
            machine.reset()

    async def process_uart(self):
        """Process UART input into ESP-NOW messages"""
        self.log.info("Starting UART processing")
        uart_index = 0

        while True:
            self.watchdog.feed() # woof!

            if not self.uart:
                await asyncio.sleep_ms(SLEEP_MEDIUM)
                continue

            if self.uart.any():
                data = self.uart.read()
                if data and len(data) > 0:
                    self.log.debug("Read %d bytes from UART", len(data))
                    for byte in data:
                        self.uart_buffer.append(byte)

                    while uart_index < len(self.uart_buffer):
                        frame = self.hdlc.process_byte(self.uart_buffer[uart_index])
                        uart_index += 1
                        if frame:
                            self.log.debug("Complete frame from UART (%d bytes)", len(frame))
                            await self.send_espnow(frame)
                    
                    if uart_index >= len(self.uart_buffer):
                        self.uart_buffer = bytearray()
                        uart_index = 0

            await asyncio.sleep_ms(SLEEP_MEDIUM)

    async def process_espnow(self):
        """Process ESP-NOW messages into UART output"""
        self.log.info("Starting ESP-NOW processing")
        
        while True:
            self.watchdog.feed()
            
            if not self.uart:
                await self._init_uart()
                continue
                
            try:
                msg = await self.espnow.arecv()
                if not msg or len(msg) != 2:
                    continue
                    
                mac, data = msg
                if not data:
                    continue

                # Handle protocol messages
                if data == PING_FRAME:
                    await self._handle_ping(mac)
                    continue
                    
                if data == PROBE_FRAME:
                    await self._handle_probe(mac)
                    continue

                # Process data frames
                if data[0] == HDLC_FLAG and data[-1] == HDLC_FLAG:
                    self.uart.write(data)
                    self.log.debug("Forwarded frame: %d bytes", len(data))
                else:
                    complete = self.fragmentor.process_fragment(data)
                    if complete:
                        self.uart.write(complete)
                        self.log.debug("Reassembled: %d bytes", len(complete))
                        
            except Exception as e:
                self.log.exc(e, "Error processing ESP-NOW message")
                
            await asyncio.sleep_ms(SLEEP_MEDIUM)

    async def _init_uart(self):
        """Initialize UART interface"""
        try:
            self.uart = UART(UART_NUM, 
                tx=PIN_TX,
                rx=PIN_RX,
                baudrate=self.baud,
                timeout=0,
                timeout_char=0,
                rxbuf=UART_BUFFER_SIZE,
                txbuf=UART_BUFFER_SIZE
            )
            self.log.info("UART%d initialized (TX:%d, RX:%d, %d baud)", 
                UART_NUM, PIN_TX, PIN_RX, self.baud)
        except Exception as e:
            self.log.exc(e, "UART initialization failed")
        await asyncio.sleep_ms(SLEEP_MEDIUM)

    async def send_espnow(self, data: bytes, raw=False) -> bool:
        """Send data over ESP-NOW with optional fragmentation"""
        try:
            if not raw:
                framed_data = self.hdlc.frame_data(data)
                if not framed_data:
                    return False

                fragments = self.fragmentor.fragment_data(framed_data)
                if not fragments:
                    return False

                # Send fragments with timing gaps
                for fragment in fragments:
                    await self.espnow.asend(BROADCAST_MAC, fragment)
                    await asyncio.sleep_ms(5)  # Inter-fragment spacing

                self.log.debug(f"Sent {len(data)} bytes in {len(fragments)} fragments")
                asyncio.create_task(self.hw.blink_led(1, 10, 0))
            else:
                await self.espnow.asend(BROADCAST_MAC, data)
                self.log.debug(f"Sent {len(data)} bytes atomically")
                asyncio.create_task(self.hw.blink_led(1, 10, 0))

            return True

        except Exception as e:
            self.log.exc(e, "Send failed")
            return False

    async def _handle_ping(self, mac):
        """Process incoming ping request"""
        mac_str = "".join(f"{b:02x}" for b in mac)
        self.log.info("Ping from %s", mac_str)
        await self.hw.blink_led(3, 50, 50)

    async def _handle_probe(self, mac):
        """Process incoming probe request"""
        mac_str = "".join(f"{b:02x}" for b in mac)
        await self.send_espnow(PROBE_RESPONSE, raw=True)
        self.log.info("Probe from %s", mac_str)

    async def _send_ping(self):
        """Send network presence ping"""
        try:
            self.log.info("Ping on channel %d", self.current_channel)
            await self.send_espnow(PING_FRAME, raw=True)
            await self.hw.blink_led(3, 50, 50)
        except Exception as e:
            self.log.exc(e, "Ping failed")

    async def _initial_channel_scan(self):
        """Perform network channel optimization"""
        self.log.info("Starting channel scan")
        best_channel = WIFI_CHANNEL
        max_responses = 0

        channels = list(PREFERRED_CHANNELS)
        channels.extend(ch for ch in range(1, 13) if ch not in PREFERRED_CHANNELS) # FIXME: region (channels)

        for channel in channels:
            # FIXME: never gets called?
            responses = await self._scan_channel(channel)
            if responses > max_responses:
                max_responses = responses
                best_channel = channel

        self.current_channel = best_channel
        self.sta.config(channel=best_channel)
        if max_responses > 0:
            self.log.info("Found %d peers on channel %d", max_responses, best_channel)
        else:
            self.log.info("No peers found, using channel %d", best_channel)

    async def _scan_channel(self, channel):
        """Scan single channel for peers"""
        self.log.debug("Scanning channel %d", channel)
        responses = 0
        self.sta.config(channel=channel)

        for _ in range(SCAN_ATTEMPTS):
            try:
                await self.send_espnow(PROBE_FRAME, raw=True)
                scan_end = time.ticks_add(time.ticks_ms(), SCAN_TIMEOUT_MS)

                while time.ticks_diff(scan_end, time.ticks_ms()) > 0:
                    try:
                        mac, msg = await self.espnow.arecv()
                        if msg == PROBE_RESPONSE:
                            responses += 1
                            self.log.debug("Response on channel %d", channel)
                    except:
                        pass
                await asyncio.sleep_ms(SLEEP_SHORT)
            except Exception as e:
                self.log.exc(e, "Scan error")
                
        return responses

async def main():
    """Network interface main entry point"""
    log = Logger("Main")
    log.info("Starting")

    try:
        gc.collect()
        reti = RNSNOW()
        uart_task = asyncio.create_task(reti.process_uart())
        espnow_task = asyncio.create_task(reti.process_espnow())
        await asyncio.gather(uart_task, espnow_task)
    except Exception as e:
        log.exc(e, "Fatal error - resetting")
        machine.reset()

try:
    gc.collect()
    asyncio.run(main())
except Exception as e:
    Logger("Startup").exc(e, "Failed to start - resetting")
    machine.reset()