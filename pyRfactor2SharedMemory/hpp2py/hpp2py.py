"""
Translate a C# file (specifically thecrewchief.org's rF2data.cs) to
something close to Python (some hand-editing may be required).
"""
# pylint: disable=bad-indentation
import re

indenting = False
indentSpaces = '        '


def translateLineComment(CPPstring):
    # whitespace then comment
    global indenting
    commentPattern = re.compile('( *)//(.*)')
    match = commentPattern.match(CPPstring)
    if match:
        if indenting:
            result = indentSpaces + '%s#%s' % (match.group(1), match.group(2))
        else:
            result = '%s#%s' % (match.group(1), match.group(2))
    else:
        result = CPPstring
    return result


def translateComment(CPPstring):
    commentPattern = re.compile('(.*)//(.*)')
    match = commentPattern.match(CPPstring)
    if match:
        result = '%s#%s' % (match.group(1), match.group(2))
    else:
        result = CPPstring
    return result


def translateCSpublic(CPPstring):
    commentPattern = re.compile('(.*?)public (.*)')
    match = commentPattern.match(CPPstring)
    if match:
        result = '%s%s' % (match.group(1), match.group(2))
        print(result)
    else:
        result = CPPstring
    return result


def translateCSjsonIgnore(CPPstring):
    commentPattern = re.compile(r'(.*)\[JsonIgnore\] (.*)')
    match = commentPattern.match(CPPstring)
    if match:
        result = '%s%s' % (match.group(1), match.group(2))
    else:
        result = CPPstring
    return result


def translateCSMarshalAsAttribute(CPPstring):
    commentPattern = re.compile(
        r'.*\[MarshalAsAttribute\(UnmanagedType.ByValArray, *SizeConst *= *(.*)\)\]')
    match = commentPattern.match(CPPstring)
    if match:
        result = '%s' % (match.group(1))
        print(result)
    else:
        result = CPPstring
    return result


def translateStruct(CPPstring):
    global indenting
    commentPattern = re.compile('struct *(.*)')
    match = commentPattern.match(CPPstring)
    if match:
        result = 'class %s(ctypes.Structure):\n    _pack_ = 4\n    _fields_ = [' % (
            match.group(1))
        indenting = True
    else:
        result = CPPstring
    return result


def translateStructItem(CPPstring, arraySize=0):
    dict = {
        'long': 'ctypes.c_int',
        'double': 'ctypes.c_double',
        'char': 'ctypes.c_ubyte',
        'short': 'ctypes.c_short',
        'char': 'ctypes.c_ubyte',
        'signed': 'ctypes.c_ubyte',
        'unsigned char': 'ctypes.c_ubyte',
        'signed char': 'ctypes.c_ubyte',
        'const char': 'ctypes.c_ubyte',
        'bool': 'ctypes.c_ubyte',
        'float': 'ctypes.c_float',
        # user-defined structs
        'TelemVect3': 'TelemVect3',
        'VehicleScoringInfoV01': 'VehicleScoringInfoV01',
        'TelemWheelV01': 'TelemWheelV01',
        'MultiSessionParticipantV01': 'MultiSessionParticipantV01',
        'TrackRulesColumnV01': 'TrackRulesColumnV01',
        'TrackRulesStageV01': 'TrackRulesStageV01',
        'TrackRulesActionV01': 'TrackRulesActionV01',
        'TrackRulesParticipantV01': 'TrackRulesParticipantV01',
        # CS
        'rF2Vec3': 'rF2Vec3',
        'rF2Wheel': 'rF2Wheel',
        'rF2VehicleTelemetry': 'rF2VehicleTelemetry',
        'rF2VehicleScoring': 'rF2VehicleScoring',
        'rF2VehicleScoringInfo': 'rF2VehicleScoringInfo',
        'rF2TrackRules': 'rF2TrackRules',
        'rF2TrackRulesAction': 'rF2TrackRulesAction',
        'rF2TrackRulesParticipant': 'rF2TrackRulesParticipant',
        'rF2VehScoringCapture': 'rF2VehScoringCapture',
        'rF2VehScoringInfo': 'rF2VehScoringInfo',
        'VehicleScoringInfoV01': 'VehicleScoringInfoV01',
        'rF2TrackedDamage': 'rF2TrackedDamage',
        'rF2PhysicsOptions': 'rF2PhysicsOptions',
        'rF2SessionTransitionCapture': 'rF2SessionTransitionCapture',
        # enums
        'rF2TrackRulesCommand': 'ctypes.c_int',
        'rF2TrackRulesColumn': 'ctypes.c_int',
        'int': 'ctypes.c_int',
        'uint': 'ctypes.c_int',
        'byte': 'ctypes.c_ubyte',
        'sbyte': 'ctypes.c_ubyte',
        'Int64': 'ctypes.c_double',
        'ushort': 'ctypes.c_short',
    }

    commentPattern = re.compile('(.*?)( *#.*)')
    match = commentPattern.match(CPPstring)
    if match:
        comment = match.group(2)
        CPPstring = match.group(1)
    else:
        comment = ''
    arrayPattern = re.compile(r' *(.*) +(.*) *\[ *(.*) *\] *?;(.*)')
    CSarrayPattern = re.compile(r' *(.*) *\[ *\] +(.*) *?;(.*)')
    match = arrayPattern.match(CPPstring)
    CSmatch = CSarrayPattern.match(CPPstring)
    if match:
        try:
            pythonType = dict[match.group(1).strip()]
            result = "        ('%s', %s*%s),%s%s" % (match.group(2),
                                                     pythonType, match.group(3), match.group(4), comment)
        except KeyError:
            print(
                'bad C array type "%s" in "%s"' %
                (match.group(1), CPPstring))
            result = CPPstring
    elif CSmatch:
        try:
            pythonType = dict[CSmatch.group(1).strip()]
            result = "        ('%s', %s*%s),%s%s" % (CSmatch.group(2),
                                                     pythonType, arraySize, CSmatch.group(3), comment)
        except KeyError:
            print(
                'bad CS array type "%s" in "%s"' %
                (CSmatch.group(1), CPPstring))
            result = CPPstring
    else:
        commentPattern = re.compile(' *(.*) +(.*) *?;(.*)')
        match = commentPattern.match(CPPstring)
        if match:
            try:
                pythonType = dict[match.group(1).strip()]
                result = indentSpaces + "('%s', %s),%s%s" \
                    % (match.group(2), pythonType, match.group(3), comment)
            except KeyError:
                print('bad C type "%s" in "%s"' % (match.group(1), CPPstring))
                result = CPPstring
        else:
            result = CPPstring
    return result


def translateStructOpen(CPPstring):
    commentPattern = re.compile('{')
    match = commentPattern.match(CPPstring)
    if match:
        result = None
    else:
        result = CPPstring
    return result


def translateStructClose(CPPstring):
    global indenting
    commentPattern = re.compile(' *}')
    match = commentPattern.match(CPPstring)
    if match:
        result = '    ]'
        indenting = False
    else:
        result = CPPstring
    return result


def translateEnum(CPPstring):
    global indenting
    print(CPPstring)
    commentPattern = re.compile(' *enum *(.*)')
    match = commentPattern.match(CPPstring)
    if match:
        result = 'class %s(Enum):' % (match.group(1))
        indenting = True
    else:
        result = CPPstring
    return result


def translateEnumOpen(CPPstring):
    return translateStructOpen(CPPstring)


def translateEnumItem(CPPstring):
    commentPattern = re.compile('(.*?)( *#.*)')
    match = commentPattern.match(CPPstring)
    if match:
        comment = match.group(2)
        CPPstring = match.group(1)
    else:
        comment = ''

    commentPattern = re.compile(r' *([^\[]*) *= *([^,]*)')
    match = commentPattern.match(CPPstring)
    if match:
        result = indentSpaces + "%s = %s%s" \
            % (match.group(1).strip(), match.group(2), comment)
    else:
        result = CPPstring
    return result


def translateEnumClose(CPPstring):
    return translateStructClose(CPPstring)


def do1line(python, line, arraySize):
    line = line.strip()
    pythonLine = translateLineComment(line)
    pythonLine = translateCSpublic(pythonLine)
    pythonLine = translateCSjsonIgnore(pythonLine)
    pythonLine = translateStruct(pythonLine)
    pythonLine = translateStructOpen(pythonLine)
    if pythonLine:
        pythonLine = translateEnum(pythonLine)
        #pythonLine = translateEnumOpen(pythonLine)
        pythonLine = translateEnumItem(pythonLine)
        #pythonLine = translateEnumClose(pythonLine)
        if pythonLine:
            pythonLine = translateStructItem(pythonLine, arraySize)
            pythonLine = translateStructClose(pythonLine)
            if pythonLine == line:
                # for CS only
                _marshall = translateCSMarshalAsAttribute(line)
                if _marshall == line:
                    pythonLine = '#untranslated ' + pythonLine
                    python.append(pythonLine + '\n')
                # else skip it
            else:
                pythonLine = translateComment(pythonLine)
                python.append(pythonLine + '\n')


if __name__ == '__main__':
    #hppFile = 'InternalsPlugin.hpp'
    #pyFile =  'InternalsPlugin.py'
    hppFile = 'rF2data.cs'
    pyFile = 'rF2data.py'
    python = []
    arraySize = ''
    with open(hppFile, "r") as cpp:
        src = cpp.readlines()
        for line in src:
            do1line(python, line, arraySize)
            arraySize = translateCSMarshalAsAttribute(line)

    with open(pyFile, "w") as p:
        p.writelines('''\
"""
Python mapping of The Iron Wolf's rF2 Shared Memory Tools
Auto-generated from %s
"""
# pylint: disable=C,R,W

from enum import Enum
import ctypes
import mmap

class rFactor2Constants:
  MAX_MAPPED_VEHICLES = 128
  MAX_MAPPED_IDS = 512
  MAX_RULES_INSTRUCTION_MSG_LEN = 96
  MAX_STATUS_MSG_LEN = 128

''' % hppFile)
        p.writelines(python)
        p.writelines("""
class SimInfo:
    def __init__(self):


        self._rf2_tele = mmap.mmap(0, ctypes.sizeof(rF2Telemetry), "$rFactor2SMMP_Telemetry$")
        self.Rf2Tele = rF2Telemetry.from_buffer(self._rf2_tele)
        self._rf2_scor = mmap.mmap(0, ctypes.sizeof(rF2Scoring), "$rFactor2SMMP_Scoring$")
        self.Rf2Scor = rF2Scoring.from_buffer(self._rf2_scor)
        self._rf2_ext = mmap.mmap(0, ctypes.sizeof(rF2Extended), "$rFactor2SMMP_Extended$")
        self.Rf2Ext = rF2Extended.from_buffer(self._rf2_ext)

    def close(self):
      # This didn't help with the errors
      try:
        self._rf2_tele.close()
        self._rf2_scor.close()
        self._rf2_ext.close()
      except BufferError: # "cannot close exported pointers exist"
        pass

    def __del__(self):
        self.close()

if __name__ == '__main__':
    # Example usage
    info = SimInfo()
    version = info.Rf2Ext.mVersion
    v = bytes(version).partition(b'\0')[0].decode().rstrip()
    clutch = info.Rf2Tele.mVehicles[0].mUnfilteredClutch # 1.0 clutch down, 0 clutch up
    gear   = info.Rf2Tele.mVehicles[0].mGear  # -1 to 6
    print('Map version: %s\\n'
          'Gear: %d, Clutch position: %d' % (v, gear, clutch))

""")
