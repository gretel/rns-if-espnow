from micropython import const
import gc
import network
import espnow
import asyncio
from machine import UART, WDT
import machine
import time
import aioespnow

from hardware import Hardware, PIN_TX, PIN_RX
from hdlc import HDLCProcessor, HDLC_FLAG
from fragment import Fragmentor
from log import Logger

GROUP_ID = b'RNS09'
PING_FRAME = GROUP_ID + b'PING'
PROBE_FRAME = GROUP_ID + b'PROBE'
PROBE_RESPONSE = GROUP_ID + b'ACK'
BROADCAST_MAC = b'\xff' * 6

UART_BUFFER_SIZE = const(1536)
UART_NUM = const(1)
WIFI_CHANNEL = const(3)
SCAN_ATTEMPTS = const(3)
SCAN_TIMEOUT_MS = const(500)
SLEEP_SHORT = const(5)
SLEEP_MEDIUM = const(10)
PREFERRED_CHANNELS = (1,6,11)

class RNSNOW:
    def __init__(self, baud=115200):
        self.log = Logger("RNS-NOW")
        self.log.info("Initializing ESP-NOW interface for Reticulum")
        
        self.watchdog = WDT(timeout=8000)
        self.baud = baud
        self.uart = None
        self.uart_buffer = bytearray()
        
        self.hdlc = HDLCProcessor()
        self.fragmentor = Fragmentor()
        
        self.hw = Hardware(self._send_ping)
        self.log.debug("Peripherals initialized")
        
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
        self.log.info("WiFi configured - initial channel %d", self.current_channel)

        try:
            self.espnow.add_peer(BROADCAST_MAC)
            self.log.debug("Broadcast peer configured")
        except Exception as e:
            self.log.exc(e, "Failed to add broadcast peer")
            machine.reset()
        
        asyncio.create_task(self._initial_channel_scan())

    async def _initial_channel_scan(self):
        self.log.info("Starting channel scan")
        best_channel = WIFI_CHANNEL
        max_responses = 0

        channels = list(PREFERRED_CHANNELS)
        channels.extend(ch for ch in range(1, 13) if ch not in PREFERRED_CHANNELS) # FIXME: region vs. channels

        for channel in channels:
            responses = 0
            self.sta.config(channel=channel)
            self.log.debug("Scanning channel %d", channel)

            for _ in range(SCAN_ATTEMPTS):
                try:
                    await self.send_espnow(PROBE_FRAME, raw=True)
                    scan_end = time.ticks_add(time.ticks_ms(), SCAN_TIMEOUT_MS)
                    
                    while time.ticks_diff(scan_end, time.ticks_ms()) > 0:
                        try:
                            mac, msg = await self.espnow.arecv()
                            if msg == PROBE_RESPONSE:
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
        # FIXME: for some reason this log output didnt occur to me?
        if max_responses > 0:
            self.log.info("Found %d peers on channel %d", max_responses, best_channel)
        else:
            self.log.info("No peers found, using default channel %d", best_channel)
    
    async def _send_ping(self):
        try:
            self.log.info("Sending ping frame on channel %d", self.current_channel)
            await self.send_espnow(PING_FRAME, raw=True)
            await self.hw.blink_led(3, 50, 50)
        except Exception as e:
            self.log.exc(e, "Failed to send ping")

    async def send_espnow(self, data: bytes, raw=False) -> bool:
        try:
            if not raw:
                framed_data = self.hdlc.frame_data(data)
                fragments = self.fragmentor.fragment_data(framed_data)
                
                success = True
                for fragment in fragments:
                    await self.espnow.asend(BROADCAST_MAC, fragment)
                    await asyncio.sleep_ms(2)  # Small delay between fragments
                    
                if success:
                    self.log.debug(f"Sent {len(data)} bytes in {len(fragments)} fragments")
                    asyncio.create_task(self.hw.blink_led(1, 10, 0))
            else:
                await self.espnow.asend(BROADCAST_MAC, data)
                self.log.debug(f"Sent {len(data)} bytes raw")
                asyncio.create_task(self.hw.blink_led(1, 10, 0))
                
            return True
            
        except Exception as e:
            self.log.exc(e, f"Failed to send data")
            return False

    async def process_uart(self):
        self.log.info("Starting UART processing")
        uart_index = 0
        
        while True:
            self.watchdog.feed()
            
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
        self.log.info("Starting ESP-NOW processing")
        
        while True:
            self.watchdog.feed()
            
            if not self.uart:
                try:
                    self.uart = machine.UART(UART_NUM, tx=PIN_TX, rx=PIN_RX, 
                        baudrate=self.baud, timeout=0, timeout_char=0, rxbuf=UART_BUFFER_SIZE, txbuf=UART_BUFFER_SIZE)
                    self.log.info("Initialized UART%d (TX:%d, RX:%d, %d baud)", 
                        UART_NUM, PIN_TX, PIN_RX, self.baud)
                except Exception as e:
                    self.log.exc(e, "Failed to initialize UART")
                await asyncio.sleep_ms(SLEEP_MEDIUM)
                continue
                
            try:
                mac, msg = await self.espnow.arecv()
                mac_str = "".join(f"{b:02x}" for b in mac)

                if msg == PING_FRAME:
                    self.log.info("Ping frame received from %s", mac_str)
                    await self.hw.blink_led(3, 50, 50)
                    continue
                    
                if msg == PROBE_FRAME:
                    await self.send_espnow(PROBE_RESPONSE, raw=True)
                    self.log.info("Probe request received, sent response to %s", mac_str)
                    continue

                if msg and len(msg) > 0:
                    if msg[0] == HDLC_FLAG and msg[-1] == HDLC_FLAG:
                        if mac != BROADCAST_MAC:
                            self.uart.write(msg)
                            self.log.debug("Forwarded framed packet of %d bytes", len(msg))
                    else:
                        complete_packet = self.fragmentor.process_fragment(msg)
                        if complete_packet:
                            self.log.debug("Reassembled packet of %d bytes from %s", 
                                len(complete_packet), mac_str)
                            self.uart.write(complete_packet)
                        
            except Exception as e:
                self.log.exc(e, "Error processing ESP-NOW message")
                
            await asyncio.sleep_ms(SLEEP_MEDIUM)

async def main():
    log = Logger("Main")
    log.info("Starting interface")
    
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