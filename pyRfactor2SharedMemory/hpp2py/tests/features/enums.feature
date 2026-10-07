Feature: Translate C# enum file to Python
"""
public enum rF2GamePhase
{
    Garage = 0,
    WarmUp = 1,
    GridWalk = 2,
    Formation = 3,
    Countdown = 4,
    GreenFlag = 5,
    FullCourseYellow = 6,
    SessionStopped = 7,
    SessionOver = 8,
    PausedOrHeartbeat = 9
}
"""
    Scenario: enum
        Given I have a line "enum enumName"
        When the enum is translated
        Then I see line "class enumName(Enum):"

    Scenario: enumOpen
        Given I have a line "{"
        When the enumOpen is translated
        Then I see line None

    Scenario: enumItem
        Given I have a line "   Garage = 0,"
        When the enumItem is translated
        Then I see line "        Garage = 0"

		Given I have a line "  ddFromTrack = 0,             # crossed s/f line for first time after full-course yellow was called"
        When the enumItem is translated
        Then I see line "        ddFromTrack = 0             # crossed s/f line for first time after full-course yellow was called"

    Scenario: enumClose
        Given I have a line "}"
        When the enumClose is translated
        Then I see line "    ]"

	# Do no harm
	Scenario: CSMarshalAsAttribute
        Given I have a line "[MarshalAsAttribute(UnmanagedType.ByValArray, SizeConst = 3)]"
        When the enum is translated
        Then I see line "[MarshalAsAttribute(UnmanagedType.ByValArray, SizeConst = 3)]"
	Scenario: CSMarshalAsAttribute
        Given I have a line "[MarshalAsAttribute(UnmanagedType.ByValArray, SizeConst = 3)]"
        When the enumItem is translated
        Then I see line "[MarshalAsAttribute(UnmanagedType.ByValArray, SizeConst = 3)]"
