from gi.repository import Gtk as gtk
from gi.repository import Gdk as gdk
from gi.repository import GLib as glib

import xcffib
import xcffib.xproto

TRIVIAL_MODS = [
    0,
    xcffib.xproto.ModMask.Lock,
    xcffib.xproto.ModMask._2,
    xcffib.xproto.ModMask.Lock | xcffib.xproto.ModMask._2
]


class GrabKeyboard:
    def __init__(self, callback, key="<Ctrl><Alt>s"):
        self.conn = xcffib.connect(display=":0")

        self.setup = self.conn.get_setup()
        self.screen = self.setup.roots[0]

        keymap = gdk.Keymap.get_default()

        keyval, modifiers = gtk.accelerator_parse(key)
        self.modifiers = int(modifiers)
        self.keycode = keymap.get_entries_for_keyval(keyval)[1][0].keycode

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
        glib.timeout_add(100, self.poll)
