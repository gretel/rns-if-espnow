from micropython import const
from machine import Pin, Timer
import asyncio
import time
from eventbus import EventBus

LED_ON = const(0)
LED_OFF = const(1)
BUTTON_COOLDOWN_MS = const(1000)

class Hardware:
    def __init__(self, config, button_callback=None):
        self.config = config
        self.led = Pin(config.led_pin, Pin.OUT)
        self.btn = Pin(config.button1_pin, Pin.IN)
        self.last_button_press = 0
        self.button_callback = button_callback
        
        self.btn_timer = Timer(1)
        self.btn_timer.init(period=50, mode=Timer.PERIODIC, callback=self._check_buttons)

    def _check_buttons(self, _):
        if self.btn.value() == 0:
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, self.last_button_press) > BUTTON_COOLDOWN_MS:
                if self.button_callback:
                    asyncio.create_task(self.button_callback())
                self.last_button_press = current_time

    async def blink_led(self, times=1, on_ms=30, off_ms=30):
        for _ in range(times):
            self.led.value(LED_ON)
            await asyncio.sleep_ms(on_ms)
            self.led.value(LED_OFF)
            await asyncio.sleep_ms(off_ms)