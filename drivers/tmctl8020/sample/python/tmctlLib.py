#
# (c) Copyright 2023-2025 Yokogawa Test & Measurement Corporation
#
# release log :Rev1.01 2023.06.05
#             :Rev1.02 2023.10.31
#             :Rev1.03 2025.03.11
# description :Sample program using TMCTL library
# environment :Python 3.12.0(32bit/64bit)

import os
import sys
import struct
from ctypes import *
from ctypes.wintypes import *

# Define DLL name
TMCTL32 = 'tmctl.dll'
TMCTL64 = 'tmctl64.dll'

# const
TM_CTL_GPIB = 1
TM_CTL_RS232 = 2
TM_CTL_USB = 3
TM_CTL_ETHER = 4
TM_CTL_USBTMC = 5
TM_CTL_ETHERUDP = 6
TM_CTL_USBTMC2 = 7
TM_CTL_VXI11 = 8
TM_CTL_USB2 = 9
TM_CTL_VISAUSB = 10
TM_CTL_SOCKET = 11
TM_CTL_USBTMC3 = 12
TM_CTL_USB3 = 13
TM_CTL_HISLIP = 14

TM_RS_1200 = "0"
TM_RS_2400 = "1"
TM_RS_4800 = "2"
TM_RS_9600 = "3"
TM_RS_19200 = "4"
TM_RS_38400 = "5"
TM_RS_57600 = "6"
TM_RS_115200 = "7"

TM_RS_8N = "0"
TM_RS_7E = "1"
TM_RS_7O = "2"
TM_RS_8O = "3"
TM_RS_7N5 = "4"
TM_RS_8N2 = "5"

TM_RS_NO = "0"
TM_RS_XON = "1"
TM_RS_HARD = "2"

# exception
TMCTLError = {  1: "Timeout",
                2: "Target device not found",
                4: "Connection with the device failed.",
                8: "Not connected to the device",
               16: "Already connected to the device",
               32: "The PC is not compatible",
               64: "Illegal function parameter",
              256: "Send error",
              512: "Receive error",
             1024: "Received data is not block data",
             4096: "System error",
             8192: "Illegal device ID",
            16384: "Unsupported function",
            32768: "Not enough buffer",
            65536: "Library missing" }

# struct
class Devicelist:
    adr : str
    def __init__(self, adr):
        self.adr = adr

class DevicelistEx:
    adr : str
    vendorID : int
    productID : int
    def __init__(self, adr, vendorID, productID):
        self.adr = adr
        self.vendorID = vendorID
        self.productID = productID

class TMCTL:
    def __init__(self):
        _DIRNAME = os.path.dirname(__file__)
        if (struct.calcsize(str('P')) == 4):
            self.dll = windll.LoadLibrary(os.path.join(_DIRNAME, TMCTL32))
        else:
            self.dll = windll.LoadLibrary(os.path.join(_DIRNAME, TMCTL64))
    def Initialize(self, wire, adr):
        tmp_id = c_int()
        ret = self.dll.TmcInitialize(c_int(wire), c_char_p(adr.encode()), byref(tmp_id))
        if ret != 0:
            raise Exception("Initialize failed.")
        return ret, tmp_id.value
    def InitializeEx(self, wire, adr, deviceID, tmo):
        tmp_id = c_int()
        ret = self.dll.TmcInitializeEx(c_int(wire), c_char_p(adr.encode()), byref(tmp_id), c_int(tmo))
        deviceID = tmp_id.value
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def Finish(self, deviceID):
        ret = self.dll.TmcFinish(c_int(deviceID))
        return ret
    def SearchDevices(self, wire, deviceList, maxList, option):
        buf = create_string_buffer(64 * maxList)
        num = c_int()
        ret = self.dll.TmcSearchDevices(c_int(wire), byref(buf), maxList, byref(num), c_char_p(option.encode()))
        for i in range(num.value):
            idx1 = 64 * i
            idx2 = buf[:].find(b'\x00', idx1)
            address = buf[idx1:idx2].decode()
            dev = Devicelist(address)
            deviceList.append(dev)
        if ret != 0:
            raise Exception("Device not found.")
        return ret, num.value
    def SearchDevicesEx(self, wire, deviceList, maxList, option):
        buf = create_string_buffer(256 * maxList)
        num = c_int()
        ret = self.dll.TmcSearchDevicesEx(c_int(wire), byref(buf), maxList, byref(num), c_char_p(option.encode()))
        for i in range(num):
            idx1 = 256 * i
            idx2 = idx1
            idx2 = buf[:].find(b'\x00', idx1)
            idx3 = idx2
            while buf[idx3] == b'\x00':
                idx3 += 1
            idx4 = idx3+1
            idx5 = idx4+1
            idx6 = idx5+1
            address = buf[idx1:idx2].decode()
            vendorID = int.from_bytes(buf[idx3:idx4+1], 'little')
            productID = int.from_bytes(buf[idx5:idx6+1], 'little')
            dev = DevicelistEx(address, vendorID, productID)
            deviceList.append(dev)
        if ret != 0:
            raise Exception("Device not found.")
        return ret, num.value
    def EncodeSerialNumber(self, length, src):
        buf = create_string_buffer(length * 2)
        ret = self.dll.TmcEncodeSerialNumber(byref(buf), c_size_t(length), c_char_p(src.encode()))
        if ret != 0:
            raise Exception("Encode failed.")
        return ret, buf.value.decode('ascii')
    def DecodeSerialNumber(self, length, src):
        buf = create_string_buffer(length * 2)
        ret = self.dll.TmcDecodeSerialNumber(byref(buf), c_size_t(length), c_char_p(src.encode()))
        if ret != 0:
            raise Exception("Decode failed.")
        return ret, buf.value.decode('ascii')
    def SetTimeout(self, deviceID, tmo):
        ret = self.dll.TmcSetTimeout(c_int(deviceID), c_int(tmo))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def SetTerm(self, deviceID, eos, eot):
        ret = self.dll.TmcSetTerm(c_int(deviceID), c_int(eos), c_int(eot))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def Send(self, deviceID, msg):
        ret = self.dll.TmcSend(c_int(deviceID), c_char_p(msg.encode())) 
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def SendByLength(self, deviceID, msg, length):
        ret = self.dll.TmcSendByLength(c_int(deviceID), c_char_p(msg.encode()), c_int(length))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def SendSetup(self, deviceID):
        ret = self.dll.TmcSendSetup(c_int(deviceID))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def SendOnly(self, deviceID, msg, length, end):
        ret = self.dll.TmcSendOnly(c_int(deviceID), c_char_p(msg.encode()), c_int(length), c_int(end))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def Receive(self, deviceID, blen):
        buf = create_string_buffer(blen)
        rlen = c_int()
        ret = self.dll.TmcReceive(c_int(deviceID), byref(buf), c_int(blen), byref(rlen))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret, buf.value.decode('ascii'), rlen.value
    def ReceiveSetup(self, deviceID):
        ret = self.dll.TmcReceiveSetup(c_int(deviceID))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def ReceiveOnly(self, deviceID, blen):
        buf = create_string_buffer(blen)
        rlen = c_int()
        ret = self.dll.TmcReceiveOnly(c_int(deviceID), byref(buf), c_int(blen), byref(rlen))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret, buf.value.decode('ascii'), rlen.value
    def ReceiveBlockHeader(self, deviceID):
        length = c_int()
        ret = self.dll.TmcReceiveBlockHeader(c_int(deviceID), byref(length))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret, length.value
    def ReceiveBlockData(self, deviceID, buff, blen):
        char_array = c_char * blen
        rlen = c_int()
        end = c_int()
        ret = self.dll.TmcReceiveBlockData(c_int(deviceID), char_array.from_buffer(buff), blen, byref(rlen), byref(end))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret, rlen.value, end.value
    def GetLastError(self, deviceID):
        ret = self.dll.TmcGetLastError(c_int(deviceID))
        if ret != 0:
            raise Exception(TMCTLError[ret])
        return ret
    def SetRen(self, deviceID, flag):
        ret = self.dll.TmcSetRen(c_int(deviceID), c_int(flag))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def CheckEnd(self, deviceID):
        ret = self.dll.TmcCheckEnd(c_int(deviceID))
        return ret
    def DeviceClear(self, deviceID):
        ret = self.dll.TmcDeviceClear(c_int(deviceID))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
    def DeviceTrigger(self, deviceID):
        ret = self.dll.TmcDeviceTrigger(c_int(deviceID))
        if ret != 0:
            raise Exception(TMCTLError[self.GetLastError(deviceID)])
        return ret
