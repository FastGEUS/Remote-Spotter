Feature: Translate C# file to Python

    Scenario: CSpublic
        Given I have a line "public blah blah"
        When the public is translated
        Then I see line "blah blah"

    Scenario: CSjsonIgnore
        Given I have a line "[JsonIgnore] blah blah"
        When the JsonIgnore is translated
        Then I see line "blah blah"

    Scenario: CSMarshalAsAttribute
        Given I have a line "[MarshalAsAttribute(UnmanagedType.ByValArray, SizeConst = 3)]"
        When the MarshalAsAttribute is translated
        Then I see line "3"

    Scenario: CSstructItem
        #Given I have a line "int mID;"
        #When the structItem is translated
        #Then I see line "        ('mID', ctypes.c_int),"

        Given I have a line "int mLapNumber;"
        When the structItem is translated
        Then I see line "        ('mLapNumber', ctypes.c_int),"

        Given I have a line "double mDeltaTime;"
        When the structItem is translated
        Then I see line "        ('mDeltaTime', ctypes.c_double),"

        Given I have a line "byte[] mVehicleName;"
        When the structItem is translated
        Then I see line "        ('mVehicleName', ctypes.c_ubyte*0),"

        Given I have a line "byte mScheduledStops;"
        When the structItem is translated
        Then I see line "        ('mScheduledStops', ctypes.c_ubyte),"

        Given I have a line "byte  mOverheating;"
        When the structItem is translated
        Then I see line "        ('mOverheating', ctypes.c_ubyte),"

        Given I have a line "byte[] mDentSeverity;"
        When the structItem is translated
        Then I see line "        ('mDentSeverity', ctypes.c_ubyte*0),"

        Given I have a line "byte[] mFrontTireCompoundName;"
        When the structItem is translated
        Then I see line "        ('mFrontTireCompoundName', ctypes.c_ubyte*0),"

		Given I have a line " double mBrakePressure;         // currently 0.0-1.0, depending on driver input and brake balance will convert to true brake pressure (kPa) in future"
        When the structItem is fullytranslated
        Then I see line "        ('mBrakePressure', ctypes.c_double),         # currently 0.0-1.0, depending on driver input and brake balance will convert to true brake pressure (kPa) in future"
		
		Given I have a line " byte mMechFail;         // mechanical failure setting; 0 (off), 1 (normal), 2 (timescaled)"
        When the structItem is fullytranslated
        Then I see line "        ('mMechFail', ctypes.c_ubyte),         # mechanical failure setting; 0 (off), 1 (normal), 2 (timescaled)"

		Given I have a line " byte mRepeatShifts;     // accidental repeat shift prevention (0-5; see PLR file)"
        When the structItem is fullytranslated
        Then I see line "        ('mRepeatShifts', ctypes.c_ubyte),     # accidental repeat shift prevention (0-5; see PLR file)"

        Given I have a line "    public byte[] mMessage;                  // a message for this participant to explain what is going on (untranslated; it will get run through translator on client machines)"
        When the CSstructItem is fullytranslated
        Then I see line "        ('mMessage', ctypes.c_ubyte*0),                  # a message for this participant to explain what is going on (untranslated; it will get run through translator on client machines)"

		# CS additions
		Given I have a line "[JsonIgnore] uint mServerPublicIP;"
        When the CSstructItem is fullytranslated
        Then I see line "        ('mServerPublicIP', ctypes.c_int),"

		Given I have a line "[JsonIgnore] uint mServerPublicIP;            // the public IP address of the server (if on a server)"
        When the CSstructItem is fullytranslated
        Then I see line "        ('mServerPublicIP', ctypes.c_int),            # the IP address of the server (if on a server)"

		Given I have a line "            [JsonIgnore] public uint mServerPublicIP;            // the public IP address of the server (if on a server)"
        When the CSstructItem is fullytranslated
        Then I see line "        ('mServerPublicIP', ctypes.c_int),            # the public IP address of the server (if on a server)"

		Given I have a line "[MarshalAsAttribute(UnmanagedType.ByValArray, SizeConst = 3)]"
        When the CSstructItem is fullytranslated
        Then I see line "3"

    Scenario: CSstructClose
        Given I have a line "}"
        When the structClose is translated
        Then I see line "    ]"

