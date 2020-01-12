#!/usr/bin/python

import os
import sys
import datetime
import subprocess
import argparse

import gi

gi.require_version('Gtk', '3.0')  # noqa: E402
from gi.repository import Gtk as gtk
from gi.repository import Gdk as gdk
from gi.repository import GdkPixbuf as Pixbuf
from gi.repository import GLib as glib
import cairo

from util import get_selected_window, get_window_from_xid, daemonize, bgra2rgba
from ffmpeg import Ffmpeg
from keybinding import GrabKeyboard


__version__ = "0.2.1"

EXIT_XID_ERROR = 1
EXIT_INVALID_PIXBUF = 2
EXIT_CANT_SAVE_IMAGE = 3
EXIT_CANCEL = 4
EXIT_CANT_GRAB_MOUSE = 5
EXIT_FFMPEG_ERROR = 6


class Escrotum(gtk.Dialog):
    def __init__(self, filename=None, selection=False, xid=None, delay=None,
                 selection_delay=250, countdown=False, use_clipboard=False,
                 command=None, record=False):
        super(Escrotum, self).__init__(type=gtk.WindowType.POPUP)

        self.started = False
        gdk.event_handler_set(self.event_handler)

        self.command = command

        self.clipboard_owner = None
        self.use_clipboard = use_clipboard

        screen = self.get_screen()
        self.display = gdk.Display.get_default()
        self.visual = screen.get_rgba_visual()

        self.rgba_support = False
        if (self.visual is not None and screen.is_composited()):
            self.rgba_support = True
            self.set_visual(self.visual)

        self.filename = filename
        if not filename:
            ext = "webm" if record else "png"
            self.filename = f"%Y-%m-%d-%H%M%S_$wx$h_escrotum.{ext}"

        if record and not self.filename.endswith(".webm"):
            print("Video recording only supports webm")
            exit(EXIT_FFMPEG_ERROR)

        self.delay = delay
        self.selection_delay = selection_delay
        self.selection = selection
        self.xid = xid
        self.countdown = countdown
        self.record = record

        if not xid:
            self.root = gdk.get_default_root_window()
        else:
            self.root = get_window_from_xid(xid)
        self.root.show()

        self.x = self.y = 0
        self.start_x = self.start_y = 0
        self.height = self.width = 0

        self.set_app_paintable(True)

        self.set_keep_above(True)
        self.connect("draw", self.on_expose)

        if delay:
            if countdown:
                sys.stdout.write("Taking shot in ..%s" % delay)
                sys.stdout.flush()
            glib.timeout_add(1000, self.start)
        else:
            self.start()

        self.painted = False

    def start(self):
        if self.delay:
            self.delay -= 1
            if self.countdown:
                sys.stdout.write(" ..%s" % self.delay)
                sys.stdout.flush()
            return True
        if self.delay == 0 and self.countdown:
            print(".")

        if self.selection and not self.xid:
            self.grab()
        else:
            self.width, self.height = self.root.get_width(), self.root.get_height()
            self.capture()

    def draw(self):
        self.painted = True
        if self.rgba_support or self.width < 4 or self.height < 4:
            return

        outer = cairo.Region(cairo.RectangleInt(0, 0, self.width, self.height))
        inner = cairo.Region(
            cairo.RectangleInt(2, 2, self.width - 4, self.height - 4))

        outer.subtract(inner)
        self.shape_combine_region(outer)

    def on_expose(self, widget, cr):
        window = self.get_window()
        width, height = window.get_width(), window.get_height()

        def set_source(r, g, b, a):
            if not self.rgba_support:
                cr.set_source_rgb(r, g, b)
            else:
                cr.set_source_rgba(r, g, b, a)

        set_source(255, 255, 255, 0.1)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        set_source(255, 255, 255, 0.8)
        cr.set_line_width(1)
        cr.rectangle(0, 0, width, height)
        cr.set_line_join(cairo.LINE_JOIN_MITER)
        cr.stroke()

        set_source(0, 0, 0, 0.8)
        cr.set_line_width(1)
        cr.rectangle(1, 1, width-1, height-1)
        cr.set_line_join(cairo.LINE_JOIN_MITER)
        cr.stroke()

        self.draw()

    def grab(self):
        """
        Grab keyboard and mouse
        """

        seat = self.display.get_default_seat()

        capabilities = (gdk.SeatCapabilities.ALL_POINTING |
                        gdk.SeatCapabilities.KEYBOARD)
        owner_events = False
        cursor = gdk.Cursor(gdk.CursorType.CROSSHAIR)
        status = seat.grab(self.root, capabilities, owner_events, cursor)
        if status is not gdk.GrabStatus.SUCCESS:
            exit(EXIT_CANT_GRAB_MOUSE)

    def ungrab(self):
        """
        Ungrab the mouse and keyboard
        """

        seat = self.display.get_default_seat()
        seat.ungrab()

    @property
    def click_selection(self):
        """
        if no motion(click and release) it's a selection of a window
        """
        return self.width < 5 and self.height < 5

    def event_handler(self, event):
        """
        Handle mouse and keyboard events
        """

        if event.type == gdk.EventType.BUTTON_PRESS:
            if event.button.button != 1:
                print("Canceled by the user")
                exit(EXIT_CANCEL)

            self.started = True
            self.start_x = int(event.x)
            self.start_y = int(event.y)
            self.move(self.x, self.y)
            self.queue_draw()

        elif event.type == gdk.EventType.KEY_RELEASE:
            if gdk.keyval_name(event.keyval) == "Escape":
                print("Canceled by the user")
                exit(EXIT_CANCEL)

        elif event.type == gdk.EventType.MOTION_NOTIFY:
            if not self.started:
                return

            self.set_rect_size(event)
            self.draw()

            if self.width > 3 and self.height > 3:
                self.resize(self.width, self.height)
                self.move(self.x, self.y)
                self.show_all()
            self.queue_draw()

        elif event.type == gdk.EventType.BUTTON_RELEASE:
            if not self.started:
                return

            self.set_rect_size(event)
            self.queue_draw()

            self.ungrab()
            self.wait()
        else:
            gtk.main_do_event(event)

    def wait(self):
        """
        wait until the window is repainted, so borders/shadows
        don't appear on the image
        """

        # if it's a window selection, don't wait
        if self.click_selection:
            self.capture()
            return

        self.painted = False
        if self.rgba_support:
            self.set_opacity(0)
        self.resize(1, 1)
        self.move(-10, -10)

        def wait():
            if not self.painted:
                return True
            # a delay between hiding selection and the screenshot, looks like
            # we can't trust in sync between window repaint and composite image
            # https://github.com/Roger/escrotum/issues/15#issuecomment-85705733
            glib.timeout_add(self.selection_delay, self.capture)

        glib.timeout_add(10, wait)

    def capture(self):
        """
        Capture the image/video based on the window size or the selected window
        """

        x, y = (self.x, self.y)
        window = self.root
        width, height = self.width, self.height

        # get image/video of the selected window
        if self.click_selection:
            xid = get_selected_window()
            if not xid:
                print("Can't get the xid of the selected window")
                exit(EXIT_XID_ERROR)
            selected_window = get_window_from_xid(xid)
            x, y, width, height = selected_window.get_geometry()

        if self.record:
            self.capture_video(x, y, width, height)
        else:
            self.capture_image(x, y, width, height, window)

    def on_exit(self, width, height):
        if self.command:
            command = self.command.replace("$f", self.filename)
            command = self._expand_argument(width, height, command)
            subprocess.call(command, shell=True)
        exit()

    def capture_image(self, x, y, width, height, window):
        pb = Pixbuf.Pixbuf.new(Pixbuf.Colorspace.RGB, True, 8, width, height)
        # mask the pixbuf if we have more than one screen
        root_width, root_height = window.get_width(), window.get_height()
        pb2 = Pixbuf.Pixbuf.new(Pixbuf.Colorspace.RGB, True, 8,
                                root_width, root_height)
        pb2 = gdk.pixbuf_get_from_window(window, x, y, width, height)
        pb2 = self.mask_pixbuf(pb2, root_width, root_height)
        pb2.copy_area(x, y, width, height, pb, 0, 0)

        if not pb:
            print("Invalid Pixbuf")
            exit(EXIT_INVALID_PIXBUF)
        if self.use_clipboard:
            self.save_clipboard(pb)
        else:
            self.save_file(pb, width, height)

        if self.command:
            self.call_exec(width, height)

        # daemonize here so we don't mess with the CWD on subprocess
        if self.use_clipboard:
            daemonize()
        else:
            # exit here instead of inside save_file
            exit()
        self.on_exit(width, height)

    def capture_video(self, x, y, width, height):
        filename = self._expand_argument(width, height, self.filename)
        ffmpeg = Ffmpeg(x, y, width, height, filename)
        if not ffmpeg.start():
            print("ffmpeg can't record video")
            exit(EXIT_FFMPEG_ERROR)
        print("Recording video, stop with Ctrl-Alt-s")

        def wait():
            ffmpeg.stop()
            self.on_exit(width, height)
        GrabKeyboard(wait)

    def get_monitor_geometries(self):
        monitors = [self.display.get_monitor(m)
                    for m in range(self.display.get_n_monitors())]
        return [m.get_geometry() for m in monitors]

    def mask_pixbuf(self, pb, width, height):
        """
        Mask the pixbuf so there is no offscreen garbage on multimonitor setups
        """

        geometries = self.get_monitor_geometries()
        mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        mask_cr = cairo.Context(mask)

        # fill transparent
        mask_cr.set_source_rgba(0, 0, 0, 0)
        mask_cr.fill()
        mask_cr.paint()
        for geo in geometries:
            mask_cr.rectangle(geo.x, geo.y, geo.width, geo.height)
            mask_cr.set_source_rgba(1, 1, 1, 1)
            mask_cr.fill()

        img = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)

        cr = cairo.Context(img)

        # fill with the dafault color
        cr.set_source_rgba(0, 0, 0, 1)
        cr.fill()
        cr.paint()

        # use the mask to paint from the pixbuf
        gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
        cr.mask_surface(mask, 0, 0)
        cr.fill()

        stride = img.get_stride()
        pixels = img.get_data()
        data = bgra2rgba(pixels, width, height)

        new_pb = Pixbuf.Pixbuf.new_from_data(data, Pixbuf.Colorspace.RGB,
                                             True, 8, width, height, stride)

        return new_pb

    def save_clipboard(self, pb):
        """
        Save the pixbuf to the clipboard
        escrotum would be alive until the clipboard owner is changed
        """

        clipboard = gtk.Clipboard.get(gdk.SELECTION_CLIPBOARD)
        clipboard.set_image(pb)
        clipboard.connect("owner-change", self.on_owner_change)

    def on_owner_change(self, clipboard, event):
        """
        Handle the selection ownership change
        XXX: find a better way, i don't know if this can cause a race condition
        if other application tries to own the clipboard at the same time
        """

        if not self.clipboard_owner:
            self.clipboard_owner = event.owner
        elif self.clipboard_owner != event.owner:
            exit()

    def _expand_argument(self, width, height, string):
        string = datetime.datetime.now().strftime(string)
        string = string.replace("$w", str(width))
        string = string.replace("$h", str(height))
        string = os.path.expanduser(string)
        return string

    def save_file(self, pb, width, height):
        """
        Stores the pixbuf as a file
        """

        self.filename = self._expand_argument(width, height, self.filename)

        filetype = "png"
        if "." in self.filename:
            filetype = self.filename.rsplit(".", 1)[1]

        try:
            pb.savev(self.filename, filetype, ["quality"], ["100"])
            print(self.filename)
        except Exception as error:
            print(error)
            exit(EXIT_CANT_SAVE_IMAGE)

    def call_exec(self, width, height):
        filename = '[CLIPBOARD]' if self.use_clipboard else self.filename
        command = self.command.replace("$f", filename)
        command = self._expand_argument(width, height, command)
        subprocess.call(command, shell=True)

    def set_rect_size(self, event):
        """
        Set the window size
        """

        if event.x < self.start_x:
            x = int(event.x)
            width = self.start_x - x
        else:
            x = self.start_x
            width = int(event.x) - self.start_x

        self.x = x
        self.width = width

        if event.y < self.start_y:
            y = int(event.y)
            height = self.start_y - y
        else:
            height = int(event.y) - self.start_y
            y = self.start_y

        self.y = y
        self.height = height


def get_options():
    epilog = """
  SPECIAL STRINGS
  Both the --exec and filename parameters can take format specifiers
  that are expanded by escrotum when encountered.

  There are two types of format specifier. Characters preceded by a '%'
  are interpreted by strftime(2). See man strftime for examples.
  These options may be used to refer to the current date and time.

  The second kind are internal to escrotum and are prefixed by '$'
  The following specifiers are recognised:
  \t$f image path/filename (ignored when used in the filename)
  \t$w image width
  \t$h image height
  Example:
  \tescrotum '%Y-%m-%d-%H%M%S_$wx$h_escrotum.png'
  \tCreates a file called something like 2013-06-17-082335_263x738_escrotum.png

  EXIT STATUS CODES
  1 can't get the window by xid
  2 invalid pixbuf
  3 can't save the image
  4 user canceled selection
  5 can't grab the mouse
  6 error with ffmpeg
"""

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Minimalist screenshot capture and screen recording program inspired by scrot.",
        epilog=epilog)

    parser.add_argument(
        '-v', '--version', default=False, action='store_true',
        help='output version information and exit')
    parser.add_argument(
        '-s', '--select', default=False, action='store_true',
        help='interactively choose a window or rectangle with '
             'the mouse, cancels with Esc or Right Click')
    parser.add_argument(
        '-x', '--xid', default=None, type=int,
        help='take a screenshot of the xid window')
    parser.add_argument(
        '-d', '--delay', default=None, type=int,
        help='wait DELAY seconds before taking a shot')
    parser.add_argument(
        '--selection-delay', default=250, type=int,
        help='delay in milliseconds between selection/screenshot')
    parser.add_argument(
        '-c', '--countdown', default=False, action="store_true",
        help='show a countdown before taking the shot (requires delay)')
    parser.add_argument(
        '-C', '--clipboard', default=False, action="store_true",
        help='store the image on the clipboard')
    parser.add_argument(
        '-e', '--exec', default=None, type=str, dest="command",
        help="run the command after the image is taken")
    parser.add_argument(
        '-r', '--record', default=False, action="store_true",
        help="screen recording. Alt+Ctrl+s to stop the recording")
    parser.add_argument(
        'FILENAME', type=str, nargs="?",
        help="image filename, default is "
             "%%Y-%%m-%%d-%%H%%M%%S_$wx$h_escrotum.png")

    return parser.parse_args()


def run():
    args = get_options()

    if args.version:
        print("escrotum %s" % __version__)
        exit()

    if args.countdown and not args.delay:
        print("Countdown parameter requires delay")
        exit()

    Escrotum(filename=args.FILENAME, selection=args.select, xid=args.xid,
             delay=args.delay, selection_delay=args.selection_delay,
             countdown=args.countdown, use_clipboard=args.clipboard,
             command=args.command, record=args.record)

    try:
        gtk.main()
    except KeyboardInterrupt:
        print("Canceled by the user")
        exit(EXIT_CANCEL)


if __name__ == "__main__":
    run()
