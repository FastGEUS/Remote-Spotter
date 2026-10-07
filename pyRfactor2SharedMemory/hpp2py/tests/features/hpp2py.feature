Feature: Translate .hpp file to Python

    Scenario: CommmentLine
        Given I have a line "// this is a comment"
        When the comment is translated
        Then I see line "# this is a comment"
    Scenario: CommmentInline
        Given I have a line "blah // this is a comment"
        When the comment is translated
        Then I see line "blah # this is a comment"

    Scenario: struct
        Given I have a line "struct StructName"
        When the struct is translated
        Then I see line "class StructName(ctypes.Structure):\n    _pack_ = 4\n    _fields_ = ["

    Scenario: structOpen
        Given I have a line "{"
        When the structOpen is translated
        Then I see line None

    Scenario: structItem
        Given I have a line "long mID;"
        When the structItem is translated
        Then I see line "        ('mID', ctypes.c_int),"

        Given I have a line "long mLapNumber;"
        When the structItem is translated
        Then I see line "        ('mLapNumber', ctypes.c_int),"

        Given I have a line "double mDeltaTime;"
        When the structItem is translated
        Then I see line "        ('mDeltaTime', ctypes.c_double),"

        Given I have a line "char mVehicleName[64];"
        When the structItem is translated
        Then I see line "        ('mVehicleName', ctypes.c_ubyte*64),"

        Given I have a line "unsigned char mScheduledStops;"
        When the structItem is translated
        Then I see line "        ('mScheduledStops', ctypes.c_ubyte),"

        Given I have a line "bool  mOverheating;"
        When the structItem is translated
        Then I see line "        ('mOverheating', ctypes.c_ubyte),"

        Given I have a line "unsigned char mDentSeverity[8];"
        When the structItem is translated
        Then I see line "        ('mDentSeverity', ctypes.c_ubyte*8),"

        Given I have a line "char mFrontTireCompoundName[18];"
        When the structItem is translated
        Then I see line "        ('mFrontTireCompoundName', ctypes.c_ubyte*18),"

	""" () in comment screws up regex
        Given I have a line "long mRelativeLaps;                   // current formation/caution laps relative to safety car (should generally be zero except when safety car crosses s/f line); this can be decremented to implement 'wave around' or 'beneficiary rule' (a.k.a. 'lucky dog' or 'free pass')"
        When the structItem is translated
        Then I see line "        ('mRelativeLaps, ctypes.c_long),                   // current formation/caution laps relative to safety car (should generally be zero except when safety car crosses s/f line); this can be decremented to implement 'wave around' or 'beneficiary rule' (a.k.a. 'lucky dog' or 'free pass')"
        """

    Scenario: structItemCommented
        Given I have a line "  long mID;                      // slot ID (note that it can be re-used in multiplayer after someone"
        When the structItem is fullytranslated
        Then I see line "        ('mID', ctypes.c_int),                      # slot ID (note that it can be re-used in multiplayer after someone"

    Scenario: structClose
        Given I have a line "};"
        When the structClose is translated
        Then I see line "    ]"
