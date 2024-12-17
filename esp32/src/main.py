from micropython import const
import gc
import network
import asyncio
from machine import UART, WDT
import machine
import time
import aioespnow
import sys
import uselect
import ubinascii

from config import Config 
from hardware import Hardware
from hdlc import HDLCProcessor, HDLC_FLAG
from fragment import Fragmentor
from log import Logger, LogManager
from stdioreader import StdioReader
from atcommands import ATCommands

# Protocol Identity
GROUP_ID = b'RNS09'
PING_FRAME = GROUP_ID + b'PING'

# Timing Constants
SLEEP_SHORT = const(5)
SLEEP_MEDIUM = const(10)
UART_NUM = const(1)
MACHINE_UID = ubinascii.hexlify(machine.unique_id()).decode("utf-8")

class RNSNOW:
    def __init__(self):
        self.config = Config()
        self.log = Logger("RNS-NOW")
        LogManager.get_instance().level = self.config.loglevel

        self.log.info("Initializing uid %s", MACHINE_UID)

        # Core components
        self.watchdog = WDT(timeout=8000)
        self.uart = None
        self.uart_buffer = bytearray()
        self.rdr = StdioReader()
        self.at = ATCommands(self.config, self.rdr)

        # Protocol handlers
        self.hdlc = HDLCProcessor()
        self.fragmentor = Fragmentor()
        self.hw = Hardware(self.config, self._send_ping)

        # Network initialization
        self._init_network()
        
    def _init_network(self):
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

        self.sta.config(channel=self.config.channel)
        if self.config.protocol == "lr":
            self.sta.config(protocol=network.MODE_LR)
        self.sta.config(pm=self.sta.PM_NONE)
        self.log.info("WiFi configured - channel %d", self.config.channel)

        try:
            self.espnow.add_peer(self.config.mac)
            self.log.debug("Broadcast peer configured")
        except Exception as e:
            self.log.exc(e, "Failed to add broadcast peer")
            machine.reset()

    async def process_uart(self):
        uart_index = 0
        self.log.info("Starting UART processing")

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
                            await self.send_espnow(frame)
                    
                    if uart_index >= len(self.uart_buffer):
                        self.uart_buffer = bytearray()
                        uart_index = 0

            await asyncio.sleep_ms(SLEEP_MEDIUM)

    async def process_console(self):
        """Process AT commands from console"""
        self.log.info("Starting console processing")

        while True:
            try:
                char = self.rdr.getchar()
                if char:
                    self.rdr.write(char) # echo
                    # Process through AT handler
                    self.at.process_byte(ord(char))
            except Exception as e:
                self.log.exc(e, "Console processing error")
            await asyncio.sleep_ms(SLEEP_SHORT)

    async def process_espnow(self):
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

                if data == PING_FRAME:
                    await self._handle_ping(mac, data)
                    continue

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
        try:
            self.uart = UART(UART_NUM,
                tx=self.config.tx_pin,
                rx=self.config.rx_pin,
                baudrate=self.config.baudrate,
                timeout=0,
                timeout_char=0
            )
            self.log.info("UART%d initialized (TX:%d, RX:%d, %d baud)", 
                UART_NUM, self.config.tx_pin, self.config.rx_pin, self.config.baudrate)
        except Exception as e:
            self.log.exc(e, "UART initialization failed")
        await asyncio.sleep_ms(SLEEP_MEDIUM)

    async def send_espnow(self, data: bytes, raw=False) -> bool:
        try:
            if not raw:
                framed_data = self.hdlc.frame_data(data)
                if not framed_data:
                    return False

                fragments = self.fragmentor.fragment_data(framed_data)
                if not fragments:
                    return False

                for fragment in fragments:
                    await self.espnow.asend(self.config.mac, fragment)
                    await asyncio.sleep_ms(5)

                self.log.debug("Sent %d bytes in %d fragments", len(data), len(fragments))
                asyncio.create_task(self.hw.blink_led(1, 10, 0))
            else:
                await self.espnow.asend(self.config.mac, data)
                self.log.debug("Sent %d bytes atomically", len(data))
                asyncio.create_task(self.hw.blink_led(1, 10, 0))

            return True

        except Exception as e:
            self.log.exc(e, "Send failed")
            return False

    async def _handle_ping(self, mac, data):
        mac_str = "".join(f"{b:02x}" for b in mac)
        self.log.info("Ping from %s with data %s", mac_str, data)
        await self.hw.blink_led(3, 50, 50)

    async def _send_ping(self):
        try:
            self.log.info("Ping on channel %d", self.config.channel)
            await self.send_espnow(PING_FRAME, raw=True)
            await self.hw.blink_led(3, 50, 50)
        except Exception as e:
            self.log.exc(e, "Ping failed")

async def main():
    log = Logger("Main")
    log.info("Starting")

    try:
        gc.collect()
        reti = RNSNOW()
        uart_task = asyncio.create_task(reti.process_uart())
        espnow_task = asyncio.create_task(reti.process_espnow())
        console_task = asyncio.create_task(reti.process_console())
        await asyncio.gather(uart_task, espnow_task, console_task)
    except Exception as e:
        log.exc(e, "Fatal error - resetting")
        machine.reset()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        Logger("Startup").exc(e, "Failed to start - resetting")
        machine.reset()