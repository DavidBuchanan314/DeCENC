import io
from io import RawIOBase
from typing import BinaryIO, Tuple


def indent(msg: str) -> str:
	ISTR = "  "
	return ISTR + msg.replace("\n", "\n"+ISTR)


def read_exact(stream: BinaryIO, length: int) -> bytes:
	res = stream.read(length)
	if len(res) != length:
		raise EOFError("Not enough bytes left in buffer (probably a truncated stream)")
	return res


def humanize(n: int) -> str:
	if n > (10*1024*1024*1024):
		return f"{n/(1024*1024*1024):.2f} GiB"
	elif n > (10*1024*1024):
		return f"{n/(1024*1024):.2f} MiB"
	elif n > (10*1024):
		return f"{n/(1024):.2f} KiB"
	else:
		return f"{n} Bytes"

# 2 decimal places, rounded down (ensures that marginally-less-than 100.00% results display as 99.99%)
def percent_fmt(numerator: int, denominator: int, dp: int=2) -> str:
	return f"{((100*(10**dp)*numerator)//denominator)/(10**dp):.{dp}f}%"


def xor_bytes(a: bytes, b: bytes) -> bytes:
	#assert(len(a) == len(b))
	return (
		int.from_bytes(a, "little") ^ int.from_bytes(b, "little")
	).to_bytes(len(a), "little")


# stdin doesn't support .tell()...
class tellable_bufferedreader(io.BufferedReader):
	def __init__(self, raw: RawIOBase, buffer_size: int=8192) -> None:
		super().__init__(raw, buffer_size)
		self.offset = 0
	
	def tell(self) -> int:
		return self.offset
	
	def read(self, __size: int|None=None) -> bytes:
		res = super().read(__size)
		self.offset += len(res)
		return res
	
	def seek(self, __offset: int, __whence: int = ...) -> int:
		raise Exception("TODO")
		return super().seek(__offset, __whence)

class tellable_bufferedwriter(io.BufferedWriter):
	def __init__(self, raw: RawIOBase, buffer_size: int=8192) -> None:
		super().__init__(raw, buffer_size)
		self.offset = 0
	
	def tell(self) -> int:
		return self.offset
	
	def write(self, __buffer) -> int:
		self.offset += len(__buffer)
		return super().write(__buffer)
	
	def seek(self, __offset: int, __whence: int = ...) -> int:
		raise Exception("TODO")
		return super().seek(__offset, __whence)

class GoodBytesIO(io.BytesIO):
	def __init__(self, initial_bytes: bytes=None, base_offset: int=0) -> None:
		super().__init__(initial_bytes)
		self.base_offset = base_offset

	def tell(self):
		return self.base_offset + super().tell()

	def read_exact(self, length: int) -> bytes:
		return read_exact(self, length)
	
	def is_eof(self):
		return self.tell() == self.base_offset + self.getbuffer().nbytes
	
	def readBEU08(self) -> int:
		return int.from_bytes(self.read_exact(1), "big")
	
	def readBEU16(self) -> int:
		return int.from_bytes(self.read_exact(2), "big")
	
	def readBEU24(self) -> int:
		return int.from_bytes(self.read_exact(3), "big")
	
	def readBEU32(self) -> int:
		return int.from_bytes(self.read_exact(4), "big")

	def readBES32(self) -> int:
		return int.from_bytes(self.read_exact(4), "big", signed=True)
	
	def readBEU64(self) -> int:
		return int.from_bytes(self.read_exact(8), "big")

	def readFP0808(self) -> Tuple[int, int]:
		return self.readBEU08(), self.readBEU08()

	def readFP1616(self) -> Tuple[int, int]:
		return self.readBEU16(), self.readBEU16()


	def writeBEU08(self, value: int) -> None:
		self.write(value.to_bytes(1, "big"))
	
	def writeBEU16(self, value: int) -> None:
		self.write(value.to_bytes(2, "big"))
	
	def writeBEU24(self, value: int) -> None:
		self.write(value.to_bytes(3, "big"))
	
	def writeBEU32(self, value: int) -> None:
		self.write(value.to_bytes(4, "big"))
	
	def writeBES32(self, value: int) -> None:
		self.write(value.to_bytes(4, "big", signed=True))
	
	def writeBEU64(self, value: int) -> None:
		self.write(value.to_bytes(8, "big"))

	def writeFP0808(self, value: Tuple[int, int]) -> None:
		self.writeBEU08(value[0])
		self.writeBEU08(value[1])

	def writeFP1616(self, value: Tuple[int, int]) -> None:
		self.writeBEU16(value[0])
		self.writeBEU16(value[1])
