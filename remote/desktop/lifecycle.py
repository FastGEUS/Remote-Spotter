"""Track only child processes created by this desktop instance."""
import os
import signal
import threading

_lock = threading.Lock()
_children = {}
_instance_job = None


def protect_process_tree():
    """Windows closes this private job on process exit, including Chromium.

    The handle is deliberately kept until OS teardown, never closed while the
    GUI is alive. Other desktop roles and already running user tunnels are not
    members. Windows 10/11 support Chromium's nested sandbox jobs.
    """
    global _instance_job
    if os.name != 'nt' or _instance_job:
        return
    import ctypes
    import logging
    from ctypes import wintypes
    class BasicLimit(ctypes.Structure):
        _fields_ = [('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),
                    ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),
                    ('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),
                    ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),
                    ('scheduling',wintypes.DWORD)]
    class Limits(ctypes.Structure):
        _fields_ = [('basic',BasicLimit),('io',ctypes.c_uint64*6),
                    ('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                    ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
    api.CreateJobObjectW.restype=wintypes.HANDLE
    api.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    api.SetInformationJobObject.restype=wintypes.BOOL
    api.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    api.AssignProcessToJobObject.restype=wintypes.BOOL
    api.GetCurrentProcess.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    job=api.CreateJobObjectW(None,None);limits=Limits();limits.basic.flags=0x2000
    if job and api.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)) and api.AssignProcessToJobObject(job,api.GetCurrentProcess()):
        _instance_job=job
    else:
        error=ctypes.get_last_error()
        if job:api.CloseHandle(job)
        logging.warning('Windows job unavailable (%s); owned SSH handle cleanup remains enabled',error)


def own(process):
    handle = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        handle = api.OpenProcess(0x00100001, False, process.pid)  # SYNCHRONIZE | TERMINATE
    with _lock:
        _children[process.pid] = (process, handle)


def release(process):
    with _lock:
        value = _children.pop(process.pid, None)
        if value and value[1]:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(value[1]))


def kill_owned():
    # Last-resort application exit. No process-name matching, no unrelated SSH
    # tunnels, and Windows handles pin identity even if a PID has been reused.
    with _lock:
        for process, handle in _children.values():
            if process.returncode is not None:
                continue
            if os.name == 'nt':
                if handle:
                    import ctypes
                    api = ctypes.windll.kernel32
                    api.TerminateProcess(ctypes.c_void_p(handle), 0)
                    api.WaitForSingleObject(ctypes.c_void_p(handle), 1000)
            else:
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
