#!/usr/bin/env python2

import os
import sys
import datetime
import subprocess
import argparse

import gtk
import cairo
import gobject

from utils import get_selected_window, daemonize, bgra2rgba


__version__ = "0.2.1"

EXIT_XID_ERROR = 1
EXIT_INVALID_PIXBUF = 2
EXIT_CANT_SAVE_IMAGE = 3
EXIT_CANCEL = 4
EXIT_CANT_GRAB_MOUSE = 5


class Escrotum(gtk.Window):
    def __init__(self, filename=None, selection=False, xid=None, delay=None,
                 selection_delay=250, countdown=False, use_clipboard=False,
                 command=None):
        super(Escrotum, self).__init__(gtk.WINDOW_POPUP)
        self.started = False

        self.command = command

        self.clipboard_owner = None
        self.use_clipboard = use_clipboard

        self.screen = self.get_screen()
        colormap = self.screen.get_rgba_colormap()

        self.rgba_support = False
        if (colormap is not None and self.screen.is_composited()):
            self.rgba_support = True
            self.set_opacity(0.4)

        self.filename = filename

        self.delay = delay
        self.selection_delay = selection_delay
        self.selection = selection
        self.xid = xid
        self.countdown = countdown

        if not xid:
            self.root = gtk.gdk.get_default_root_window()
        else:
            self.root = gtk.gdk.window_foreign_new(xid)

        self.x = self.y = 0
        self.start_x = self.start_y = 0
        self.height = self.width = 0

        self.area = gtk.DrawingArea()

        self.set_keep_above(True)
        self.area.connect("expose-event", self.on_expose)

        self.add(self.area)

        if delay:
            if countdown:
                sys.stdout.write("Taking shot in ..%s" % delay)
                sys.stdout.flush()
            gobject.timeout_add(1000, self.start)
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
            print "."

        if self.selection and not self.xid:
            self.grab()
        else:
            self.width, self.height = self.root.get_size()
            self.screenshot()

    def draw(self):
        self.painted = True
        if self.rgba_support:
            return
        width, height = self.get_size()

        mask = gtk.gdk.Pixmap(None, width, height, 1)

        gc = mask.new_gc()

        # draw the rectangle
        gc.foreground = gtk.gdk.Color(0, 0, 0, 1)
        mask.draw_rectangle(gc, True, 0, 0, width, height)

        # and clear the background
        gc.foreground = gtk.gdk.Color(0, 0, 0, 0)
        mask.draw_rectangle(gc, True, 2, 2, width-4, height-4)

        self.shape_combine_mask(mask, 0, 0)

    def on_expose(self, widget, event):
        width, height = self.get_size()
        white_gc = self.style.white_gc
        black_gc = self.style.black_gc

        # actualy paint the window
        self.area.window.draw_rectangle(white_gc, True, 0, 0, width, height)
        self.area.window.draw_rectangle(black_gc, True, 1, 1, width-2,
                                        height-2)
        self.draw()

    def grab(self):
        """
        Grab the mouse
        """

        mask = gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK | \
            gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK | \
            gtk.gdk.ENTER_NOTIFY_MASK | gtk.gdk.LEAVE_NOTIFY_MASK

        self.root.set_events(gtk.gdk.BUTTON_PRESS | gtk.gdk.MOTION_NOTIFY |
                             gtk.gdk.BUTTON_RELEASE)

        status = gtk.gdk.pointer_grab(self.root, event_mask=mask,
                                      cursor=gtk.gdk.Cursor(gtk.gdk.CROSSHAIR))

        if status != gtk.gdk.GRAB_SUCCESS:
            print "Can't grab the mouse"
            exit(EXIT_CANT_GRAB_MOUSE)
        gtk.gdk.event_handler_set(self.event_handler)

    def ungrab(self):
        """
        Ungrab the mouse and keyboard
        """

        self.root.set_events(())
        gtk.gdk.pointer_ungrab()
        gtk.gdk.keyboard_ungrab()

    @property
    def click_selection(self):
        """
        if no motion(click and release) it's a selection of a window
        """
        return self.width < 5 and self.height < 5

    def event_handler(self, event):
        """
        Handle mouse events
        """

        if event.type == gtk.gdk.BUTTON_PRESS:
            if event.button != 1:
                print "Canceled by the user"
                exit(EXIT_CANCEL)
            # grab the keyboard only when selection started
            gtk.gdk.keyboard_grab(self.root)
            self.started = True
            self.start_x = int(event.x)
            self.start_y = int(event.y)
            self.move(self.x, self.y)

        elif event.type == gtk.gdk.KEY_RELEASE:
            if gtk.gdk.keyval_name(event.keyval) == "Escape":
                print "Canceled by the user"
                exit(EXIT_CANCEL)

        elif event.type == gtk.gdk.MOTION_NOTIFY:
            if not self.started:
                return

            self.set_rect_size(event)
            self.draw()

            if self.width > 3 and self.height > 3:
                self.resize(self.width, self.height)
                self.move(self.x, self.y)
                self.show_all()

        elif event.type == gtk.gdk.BUTTON_RELEASE:
            if not self.started:
                return

            self.set_rect_size(event)

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
            self.screenshot()
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
            gobject.timeout_add(self.selection_delay, self.screenshot)

        gobject.timeout_add(10, wait)

    def screenshot(self):
        """
        Capture the screenshot based on the window size or the selected window
        """

        x, y = (self.x, self.y)
        window = self.root
        width, height = self.width, self.height

        # get screenshot of the selected window
        if self.click_selection:
            xid = get_selected_window()
            if not xid:
                print "Can't get the xid of the selected window"
                exit(EXIT_XID_ERROR)
            selected_window = gtk.gdk.window_foreign_new(xid)
            width, height = selected_window.get_size()
            x, y = selected_window.get_origin()

        pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, width, height)
        # mask the pixbuf if we have more than one screen
        root_width, root_height = window.get_size()
        pb2 = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8,
                             root_width, root_height)
        pb2 = pb2.get_from_drawable(window, window.get_colormap(),
                                    x, y, x, y,
                                    width, height)
        pb2 = self.mask_pixbuf(pb2, root_width, root_height)
        pb2.copy_area(x, y, width, height, pb, 0, 0)

        if not pb:
            print "Invalid Pixbuf"
            exit(EXIT_INVALID_PIXBUF)
        self.save_file(pb, width, height)
        if self.use_clipboard:
            self.save_clipboard(pb)
        if self.command:
            self.call_exec(width, height)

        # daemonize here so we don't mess with the CWD on subprocess
        if self.use_clipboard:
            daemonize()
        else:
            # exit here instead of inside save_file
            exit()

    def get_geometry(self):
        monitors = self.screen.get_n_monitors()
        return [self.screen.get_monitor_geometry(m) for m in range(monitors)]

    def mask_pixbuf(self, pb, width, height):
        """
        Mask the pixbuf so there is no offscreen garbage on multimonitor setups
        """

        geometry = self.get_geometry()
        mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        mask_cr = cairo.Context(mask)

        # fill transparent
        mask_cr.set_source_rgba(0, 0, 0, 0)
        mask_cr.fill()
        mask_cr.paint()
        for geo in geometry:
            mask_cr.rectangle(geo.x, geo.y, geo.width, geo.height)
            mask_cr.set_source_rgba(1, 1, 1, 1)
            mask_cr.fill()

        img = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)

        cr = cairo.Context(img)
        gdkcr = gtk.gdk.CairoContext(cr)

        # fill with the dafault color
        gdkcr.set_source_rgba(0, 0, 0, 1)
        gdkcr.fill()
        gdkcr.paint()

        # use the mask to paint from the pixbuf
        gdkcr.set_source_pixbuf(pb, 0, 0)
        gdkcr.mask_surface(mask, 0, 0)
        gdkcr.fill()

        stride = img.get_stride()
        pixels = img.get_data()

        data = bgra2rgba(pixels, width, height)

        new_pb = gtk.gdk.pixbuf_new_from_data(data, gtk.gdk.COLORSPACE_RGB,
                                              True, 8, width, height, stride)
        return new_pb

    def save_clipboard(self, pb):
        """
        Save the pixbuf to the clipboard
        escrotum would be alive until the clipboard owner is changed
        """

        clipboard = gtk.Clipboard()
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

        if not self.filename:
            self.filename = "%Y-%m-%d-%H%M%S_$wx$h_escrotum.png"

        self.filename = self._expand_argument(width, height, self.filename)

        filetype = "png"
        if "." in self.filename:
            filetype = self.filename.rsplit(".", 1)[1]

        try:
            pb.save(self.filename, filetype)
            print self.filename
        except Exception, error:
            print error
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
  \tescrotum '%Y-%m-%d_$wx$h_escrotum.png'
  \tCreates a file called something like 2013-06-17-082335_263x738_escrotum.png

  EXIT STATUS CODES
  1 can't get the window by xid
  2 invalid pixbuf
  3 can't save the image
  4 user canceled selection
  5 can't grab the mouse
"""

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Minimalist screenshot capture program inspired by scrot.",
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
        print "Countdown parameter requires delay"
        exit()

    Escrotum(filename=args.FILENAME, selection=args.select, xid=args.xid,
             delay=args.delay, selection_delay=args.selection_delay,
             countdown=args.countdown, use_clipboard=args.clipboard,
             command=args.command)

    try:
        gtk.main()
    except KeyboardInterrupt:
        print "Canceled by the user"
        exit(EXIT_CANCEL)

if __name__ == "__main__":
    run()
