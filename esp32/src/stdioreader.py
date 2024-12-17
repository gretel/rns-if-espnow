# https://github.com/orgs/micropython/discussions/11448#discussioncomment-7565038
import sys
import select

class StdioReader:

    def __init__(self):
        self._selpoll = select.poll()
        self._selpoll.register(sys.stdin, select.POLLIN)
        self._bytes, self._index, self._expecting = bytearray(4), 0, 0

    def __enter__(self):
        return self

    def __exit__(self, _type, value, traceback):
        return _type, value, traceback

    def write(self, str):
        sys.stdin.buffer.write(str)

    def getchar(self):
        if not len(self._selpoll.poll(0)):
            return None

        charval = sys.stdin.buffer.read(1)  # get a single byte (of a possible UTF-8 sequence)
        charval = charval[0]  # turn bytes array into an integer
        if charval & 0x80 == 0:  # is a single byte
            character = chr(charval)
            self._index = 0
            self._expecting = 0
            return character
        else:
            if charval & 0xe0 == 0xc0:  # is first of two bytes
                self._bytes[0], self._index, self._expecting = charval, 1, 1
            elif charval & 0xf0 == 0xe0:  # is first of three bytes
                self._bytes[0], self._index, self._expecting = charval, 1, 2
            elif charval & 0xf8 == 0xf0:  # is first of four bytes
                self._bytes[0], self._index, self._expecting = charval, 1, 3
            elif charval & 0xc0 == 0x80:  # is a sequence byte
                self._bytes[self._index] = charval
                self._index += 1
                if self._index > self._expecting:
                    character = self._bytes[0:self._expecting+1].decode()
                    self._index, self._expecting = 0, 0
                    return character
            else:
                raise UnicodeError
        return None
