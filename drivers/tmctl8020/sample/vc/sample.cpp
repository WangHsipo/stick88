#include "tmctl.h"
#include <stdio.h>
#include <string.h>

int ExecuteCommunicate( void )
{
	int	 wire;
	char adr[100];
	char serial_num[256];
	int  ret;
	int  id;
	char message[256];
	char buf[1000];
	int  length;
	int  endflag = 0;

	const char* gpib_adr			= "1";									// GPIB address = 1
	const char* rs232c_adr			= "1,6,0,1";							// RS232C COM1, 57600, 8-NO-1, CTS-RTS
	const char* usb_adr				= "1";									// USB ID = 1
	const char* ether_adr			= "11.22.33.44,yokogawa,abcdefgh";		// Ethernet IP = 11.22.33.44, User name = yokogawa, Password = abcdefgh
	const char* usbtmc_adr			= "27E000001";							// USBTMC Serial Number = 27E000001
	const char* usbtmc_gs610_adr	= "27E000001C";							// USBTMC (GS610) Serial Number = 27E000001 + "C"
	const char* vxi11_adr			= "11.22.33.44";						// VXI-11 IP = 11.22.33.44
	const char* visa_adr			= "27E000001";							// VISAUSB Serial Number = 27E000001
	const char* visa_gs610_adr		= "27E000001C";							// VISAUSB (GS610) Serial Number = 27E000001 + "C"
	const char* socket_adr			= "11.22.33.44,12345";					// SOCKET IP = 11.22.33.44, Port = 12345
	const char* hislip_adr			= "11.22.33.44";						// HiSLIP IP = 11.22.33.44, Port = 4880

	const char* RST_COMMAND			= "*RST";
	const char* IDN_QUERY			= "*IDN?";
	const char* SEND_WAVEFORM_QUERY	= ":WAVEFORM:FORMAT ASCII;:WAVEFORM:SEND?";

	// Example 1: GPIB address = 1
	wire = TM_CTL_GPIB;
	strcpy_s(adr, gpib_adr);

	// Example 2: RS232 COM1, 57600, 8-NO-1, CTS-RTS
	//wire = TM_CTL_RS232;
	//strcpy_s(adr, rs232c_adr);

	// Example 3: USB ID = 1
	//wire = TM_CTL_USB;
	//strcpy_s(adr, usb_adr);

	// Example 4: Ethernet IP = 11.22.33.44, User name = yokogawa, Password = abcdefgh
	//wire = TM_CTL_ETHER;
	//strcpy_s(adr, ether_adr);

	// Example 5: USBTMC (DL9000) Serial Number = 27E000001
	//wire = TM_CTL_USBTMC;
	//strcpy_s(adr, usbtmc_adr);

	// Example 6: USBTMC (GS200, GS820) Serial Number = 27E000001
	//wire = TM_CTL_USBTMC2;
	//strcpy_s(adr, usbtmc_adr);

	// Example 7: USBTMC (GS610) Serial Number = 27E000001
	//wire = TM_CTL_USBTMC2;
	//strcpy_s(adr, usbtmc_gs610_adr);

	// Example 8: USBTMC (on instruments other than the DL9000 or GS series) Serial Number = 27E000001
	//wire = TM_CTL_USBTMC2;
	//strcpy_s(serial_num, usbtmc_adr);
	//TmcEncodeSerialNumber(adr, 256, serial_num);

	// Example 9: VXI-11 IP = 11.22.33.44
	//wire = TM_CTL_VXI11;
	//strcpy_s(adr, vxi11_adr);

	// Example 10: VISAUSB (GS200, GS820, FG400) Serial Number = 27E000001
	//wire = TM_CTL_VISAUSB;
	//strcpy_s(adr, visa_adr);

	// Example 11: VISAUSB (GS610) Serial Number = 27E000001
	//wire = TM_CTL_VISAUSB;
	//strcpy_s(adr, visa_gs610_adr);

	// Example 12: VISAUSB (on instruments other than GS series or FG400) Serial Number = 27E000001
	//wire = TM_CTL_VISAUSB;
	//strcpy_s(serial_num, visa_adr);
	//TmcEncodeSerialNumber(adr, 256, serial_num);

	// Example 13: USBTMC (with YTUSB driver) Serial Number = 27E000001
	//wire = TM_CTL_USBTMC3;
	//strcpy_s(serial_num, usbtmc_adr);
	//TmcEncodeSerialNumber(adr, 256, serial_num);

	// Example 14: SOCKET IP = 11.22.33.44, Port = 12345
	//wire = TM_CTL_SOCKET;
	//strcpy_s(adr, socket_adr);

	// Example 15: HiSLIP IP = 11.22.33.44, Port = 4880(default)
	//wire = TM_CTL_HISLIP;
	//strcpy_s(adr, hislip_adr);

	ret = TmcInitialize(wire, adr, &id);
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	ret = TmcSetTerm( id, 2, 1 );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	ret = TmcSetTimeout( id, 300 );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	ret = TmcSetRen( id, 1 );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	// Send *RST
	strcpy_s(message, RST_COMMAND);
	ret = TmcSend( id, message );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	// Send *IDN? and receive query
	strcpy_s(message, IDN_QUERY);
	ret = TmcSend( id, message );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	ret = TmcReceive( id, buf, 1000, &length );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	// Receive block data
	strcpy_s(message, SEND_WAVEFORM_QUERY);
	ret = TmcSend( id, message );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
	ret = TmcReceiveBlockHeader(id, &length);
	while (endflag == 0) {	// Continue to receive data until the end flag is set.
		ret = TmcReceiveBlockData(id, buf, 1000, &length, &endflag);
	}
	ret = TmcFinish( id );
	if( ret != 0 ) {
		return TmcGetLastError( id );
	}
}
