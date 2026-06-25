#
# (c) Copyright 2023-2025 Yokogawa Test & Measurement Corporation
#
# system      :DLM3000
# sub-system  :sample.py
# release log :Rev1.01 2023.06.05
#             :Rev1.02 2023.10.31
#             :Rev1.03 2025.04.11
# description :Sample program using TMCTL library
#              Command example
#              python.exe sample.py
# environment :Python 3.12.0(32bit/64bit)

import tmctlLib

if __name__ == '__main__':
    deviceID  = -1
    tmctl = tmctlLib.TMCTL()

    # Example 1: GPIB address = 1
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_GPIB, "1")
    # Example 2: RS232 COM1, 57600, 8-NO-1, CTS-RTS
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_RS232, "1,6,0,2")
    # Example 3: USB ID = 1
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_USB, "1")
    # Example 4: Ethernet IP = 11.22.33.44, User name = yokogawa, Password = abcdefgh
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_ETHER, "11.22.33.44,yokogawa,abcdefgh")
    # Example 5: USBTMC (DL9000) Serial Number = 27E000001
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_USBTMC, "27E000001")
    # Example 6: USBTMC (GS200, GS820) Serial Number = 27E000001
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_USBTMC2, "27E000001")
    # Example 7: USBTMC (GS610) Serial Number = 27E000001
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_USBTMC2, "27E000001C")
    # Example 8: USBTMC (on instruments other than the DL9000 or GS series) Serial Number = 27E000001
    # ret, encode = tmctl.EncodeSerialNumber(128,"27E000001")
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_USBTMC2, encode)
    # Example 9: VXI-11 IP = 11.22.33.44
    ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_VXI11, "11.22.33.44")
    # Example 10: VISAUSB (GS200, GS820, FG400) Serial Number = 27E000001
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_VISAUSB, "27E000001")
    # Example 11: VISAUSB (GS610) Serial Number = 27E000001
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_VISAUSB, "27E000001C")
    # Example 8: USBTMC (on instruments other than the DL9000 or GS series) Serial Number = 27E000001
    # ret, encode = tmctl.EncodeSerialNumber(128, "27E000001")
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_VISAUSB, encode)
    # Example 13: USBTMC (with YTUSB driver) Serial Number = 27E000001
    # ret, encode = tmctl.EncodeSerialNumber(128, "27E000001")
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_USBTMC3, encode)
    # Example 14：HiSLIP IP = 11.22.33.44
    # ret, deviceID = tmctl.Initialize(tmctlLib.TM_CTL_HISLIP, "11.22.33.44")
    
    ret = tmctl.SetTerm(deviceID, 2, 1)
    ret = tmctl.SetTimeout(deviceID, 300)
    ret = tmctl.SetRen(deviceID, 1)
    ret = tmctl.DeviceClear(deviceID)
    # Send *RST
    ret = tmctl.Send(deviceID, "*RST")
    # Send *IDN? and receive query
    ret = tmctl.Send(deviceID, "*IDN?")
    ret, buf, length = tmctl.Receive(deviceID, 1000)
    # Send STOP
    ret = tmctl.Send(deviceID, "STOP")
    # Receive block data
    ret = tmctl.Send(deviceID, ":WAVEFORM:FORMAT WORD;:WAVEFORM:SEND?")
    ret, rlen = tmctl.ReceiveBlockHeader(deviceID)
    # Continue to receive data until the end flag is set
    buf = bytearray(1000)
    endflag = 0
    while endflag != 1:
        ret, rlen, endflag = tmctl.ReceiveBlockData(deviceID, buf, 1000)
    ret = tmctl.Finish(deviceID)
