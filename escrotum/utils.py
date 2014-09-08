import os
import sys


def get_selected_window():
    """
    Ugly workaround to get the selected window, can't use gtk/gdk =/
    from: http://unix.stackexchange.com/a/16157
    """

    from ctypes import CDLL, c_int, c_uint32, c_uint, byref

    Xlib = CDLL("libX11.so.6")
    display = Xlib.XOpenDisplay(None)

    if display == 0:
        return None

    w = Xlib.XRootWindow(display, c_int(0))

    root_id, child_id = (c_uint32(), c_uint32())
    root_x, root_y, win_x, win_y = [c_int()] * 4

    mask = c_uint()
    ret = Xlib.XQueryPointer(display, c_uint32(w),
                             byref(root_id), byref(child_id),
                             byref(root_x), byref(root_y),
                             byref(win_x), byref(win_y),
                             byref(mask))
    if ret == 0:
        return None

    value = child_id.value
    # if 0 is root
    if value == 0:
        value = root_id.value
    return value


def daemonize():
    """
    do the UNIX double-fork magic, see Stevens' "Advanced
    Programming in the UNIX Environment" for details (ISBN 0201563177)
    http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16

    Based on https://gist.github.com/dongsheng/1075904
    """
    try:
        pid = os.fork()
        if pid > 0:
            # exit first parent
            sys.exit(0)
    except OSError, e:
        sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(1)

    # decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent
            sys.exit(0)
    except OSError, e:
        sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(1)

    # redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    si = file("/dev/null", 'r')
    so = file("/dev/null", 'a+')
    se = file("/dev/null", 'a+', 0)

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
