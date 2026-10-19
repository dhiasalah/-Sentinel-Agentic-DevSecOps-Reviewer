# System: Linux only (uses /proc).
def uptime():
    return open("/proc/uptime").read()
