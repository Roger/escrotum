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
