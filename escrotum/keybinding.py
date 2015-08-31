import gtk
import gobject

import xcffib
import xcffib.xproto

TRIVIAL_MODS = [
    0,
    xcffib.xproto.ModMask.Lock,
    xcffib.xproto.ModMask._2,
    xcffib.xproto.ModMask.Lock | xcffib.xproto.ModMask._2
]


class GrabKeyboard(object):
    def __init__(self, callback, key="<Ctrl><Alt>s"):
        self.conn = xcffib.connect(display=":0")

        self.setup = self.conn.get_setup()
        self.screen = self.setup.roots[0]

        keymap = gtk.gdk.keymap_get_default()

        keyval, modifiers = gtk.accelerator_parse(key)
        self.modifiers = int(modifiers)
        self.keycode = keymap.get_entries_for_keyval(keyval)[0][0]

        self.callback = callback

        self.grab_keys()
        self.poll()

    def grab_key(self, key, modifiers):
        self.conn.core.GrabKey(
            False,
            self.screen.root,
            modifiers,
            key,
            xcffib.xproto.GrabMode.Async,
            xcffib.xproto.GrabMode.Async
        )
        self.conn.flush()

    def grab_keys(self):
        for mod in TRIVIAL_MODS:
            self.grab_key(self.keycode, self.modifiers | mod)

    def poll(self):
        ev = self.conn.poll_for_event()
        if type(ev) is xcffib.xproto.KeyReleaseEvent:
            self.callback()
            return
        gobject.timeout_add(100, self.poll)
