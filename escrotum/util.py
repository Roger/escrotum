import os
import sys

from gi.repository import GdkX11


def get_selected_window():
    """
    Ugly workaround to get the selected window, can't use gtk/gdk =/
    from: http://unix.stackexchange.com/a/16157
    """

    from ctypes import CDLL, c_int, c_uint32, c_uint, byref, c_void_p

    Xlib = CDLL("libX11.so.6")
    Xlib.XOpenDisplay.restype = c_void_p

    display = c_void_p(Xlib.XOpenDisplay(None))

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


def get_window_from_xid(xid):
    display = GdkX11.X11Display.get_default()
    return GdkX11.X11Window.foreign_new_for_display(display, xid)


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
    except OSError as e:
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
    except OSError as e:
        sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
        sys.exit(1)

    # redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    si = open("/dev/null", 'r')
    so = open("/dev/null", 'a+')
    se = open("/dev/null", 'a+')

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def bgra2rgba(pixels, width, height):
    try:
        # import here because numpy is slow to import
        # and not always needed
        import numpy as np
        HAS_NUMPY = True
    except ImportError:
        import array
        HAS_NUMPY = False
        print("No numpy support, saving would be slower")

    # GDK wants RGBA but we currently have BGRA, so let's flip R and B
    if(HAS_NUMPY):
        arr = np.frombuffer(pixels, dtype=np.uint8)
        arr.shape = (-1, 4)
        data = arr[:,[2,1,0,3]]
    else:
        data = array.array ("c", pixels)
        for x in range (width):
            for y in range (height):
                i = (width * y + x) * 4
                data[i + 0], data[i + 2] = data[i + 2], data[i + 0]
    return data.tostring()


def cmd_exists(cmd):
    """
    Check if command exists on PATH
    from: http://stackoverflow.com/a/28909933/4437679
    """
    return any(
        os.access(os.path.join(path, cmd), os.X_OK)
        for path in os.environ["PATH"].split(os.pathsep)
    )
