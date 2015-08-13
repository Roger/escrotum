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

# selection states
SEL_STATE_FREE = 0
SEL_STATE_DRAWING = 1
SEL_STATE_MOVING = 2
SEL_STATE_RESIZING_TOP_RIGHT = 3
SEL_STATE_RESIZING_BOTTOM_RIGHT = 4
SEL_STATE_RESIZING_BOTTOM_LEFT = 5
SEL_STATE_RESIZING_TOP_LEFT = 6

class Escrotum(gtk.Window):
    def __init__(self, filename=None, selection=False,
                 selection_resize=False, xid=None, delay=None,
                 selection_delay=250, countdown=False, use_clipboard=False,
                 command=None):
        super(Escrotum, self).__init__(gtk.WINDOW_POPUP)
        self.selection_state = SEL_STATE_FREE

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
        self.selection_resize = selection_resize
        self.cur_cursor = None
        self.resize_threshold_px = 10
        self.sel_state_to_handle_func = {
            SEL_STATE_FREE: self.handle_ss_free,
            SEL_STATE_DRAWING: self.handle_ss_drawing,
            SEL_STATE_MOVING: self.handle_ss_moving,
            SEL_STATE_RESIZING_TOP_RIGHT: self.handle_ss_rz_top_right,
            SEL_STATE_RESIZING_BOTTOM_RIGHT: self.handle_ss_rz_bottom_right,
            SEL_STATE_RESIZING_BOTTOM_LEFT: self.handle_ss_rz_bottom_left,
            SEL_STATE_RESIZING_TOP_LEFT: self.handle_ss_rz_top_left,
        }
        self.sel_state_to_cursor = {
            SEL_STATE_FREE: gtk.gdk.CROSSHAIR,
            SEL_STATE_DRAWING: gtk.gdk.CROSSHAIR,
            SEL_STATE_MOVING: gtk.gdk.FLEUR,
            SEL_STATE_RESIZING_TOP_RIGHT: gtk.gdk.TOP_RIGHT_CORNER,
            SEL_STATE_RESIZING_BOTTOM_RIGHT: gtk.gdk.BOTTOM_RIGHT_CORNER,
            SEL_STATE_RESIZING_BOTTOM_LEFT: gtk.gdk.BOTTOM_LEFT_CORNER,
            SEL_STATE_RESIZING_TOP_LEFT: gtk.gdk.TOP_LEFT_CORNER,
        }
        self.xid = xid
        self.countdown = countdown

        if not xid:
            self.root = gtk.gdk.get_default_root_window()
        else:
            self.root = gtk.gdk.window_foreign_new(xid)

        self.x = self.y = 0
        self.click_x = self.click_y = 0
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

    def grab_pointer(self, cursor):
        """
        Grag pointer with a given cursor.
        """

        if gtk.gdk.pointer_is_grabbed():
            if cursor == self.cur_cursor:
                # same cursor: no need to grab again
                return

            self.ungrab_pointer()

        gtk.gdk.pointer_grab(self.root, event_mask=self.mask,
                             cursor=gtk.gdk.Cursor(cursor))
        self.cur_cursor = cursor

    def ungrab_pointer(self):
        """
        Ungrab pointer.
        """

        gtk.gdk.pointer_ungrab()

    def grab(self):
        """
        Grab the mouse
        """

        self.mask = gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK | \
            gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK | \
            gtk.gdk.ENTER_NOTIFY_MASK | gtk.gdk.LEAVE_NOTIFY_MASK

        self.root.set_events(gtk.gdk.BUTTON_PRESS | gtk.gdk.MOTION_NOTIFY |
                             gtk.gdk.BUTTON_RELEASE)
        self.grab_pointer(gtk.gdk.CROSSHAIR)
        gtk.gdk.event_handler_set(self.event_handler)

    def ungrab(self):
        """
        Ungrab the mouse and keyboard
        """

        self.root.set_events(())
        self.ungrab_pointer()
        gtk.gdk.keyboard_ungrab()

    @property
    def click_selection(self):
        """
        if no motion(click and release) it's a selection of a window
        """
        return self.width < 5 and self.height < 5

    @property
    def right_pos(self):
        """
        Horizontal position of the rectangle's right side.
        """

        return self.x + self.width

    @property
    def bottom_pos(self):
        """
        Vertical position of the rectangle's bottom side.
        """

        return self.y + self.height

    def pos_to_rect_is_moving(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to move the rectangle.
        """

        x_cond = x >= self.x and x < self.right_pos
        y_cond = y >= self.y and y < self.bottom_pos

        return x_cond and y_cond

    def pos_to_rect_is_resizing_right(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the right side.
        """

        rt = self.resize_threshold_px
        cond = x >= max(self.right_pos - rt, 0) and x < self.right_pos

        return cond

    def pos_to_rect_is_resizing_left(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the left side.
        """

        rt = self.resize_threshold_px
        cond = x >= max(self.x, 0) and x < self.x + rt

        return cond

    def pos_to_rect_is_resizing_top(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the top side.
        """

        rt = self.resize_threshold_px
        cond = y >= max(self.y, 0) and y < self.y + rt

        return cond

    def pos_to_rect_is_resizing_bottom(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the bottom side.
        """

        rt = self.resize_threshold_px
        cond = y >= max(self.bottom_pos - rt, 0) and y < self.bottom_pos

        return cond

    def pos_to_rect_is_resizing_top_right(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the top-right corner.
        """

        t = self.pos_to_rect_is_resizing_top(x, y)
        r = self.pos_to_rect_is_resizing_right(x, y)

        return t and r

    def pos_to_rect_is_resizing_bottom_right(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the bottom-right corner.
        """

        b = self.pos_to_rect_is_resizing_bottom(x, y)
        r = self.pos_to_rect_is_resizing_right(x, y)

        return b and r

    def pos_to_rect_is_resizing_bottom_left(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the bottom-left corner.
        """

        b = self.pos_to_rect_is_resizing_bottom(x, y)
        l = self.pos_to_rect_is_resizing_left(x, y)

        return b and l

    def pos_to_rect_is_resizing_top_left(self, x, y):
        """
        Returns True if, given a cursor position, the action to be
        performed when grabbing should be to resize the rectangle
        using the top-left corner.
        """

        t = self.pos_to_rect_is_resizing_top(x, y)
        l = self.pos_to_rect_is_resizing_left(x, y)

        return t and l

    def pos_to_sel_state(self, x, y):
        """
        Returns a selection state in function of a cursor position.
        """

        if self.pos_to_rect_is_resizing_top_right(x, y):
            return SEL_STATE_RESIZING_TOP_RIGHT
        elif self.pos_to_rect_is_resizing_bottom_right(x, y):
            return SEL_STATE_RESIZING_BOTTOM_RIGHT
        elif self.pos_to_rect_is_resizing_bottom_left(x, y):
            return SEL_STATE_RESIZING_BOTTOM_LEFT
        elif self.pos_to_rect_is_resizing_top_left(x, y):
            return SEL_STATE_RESIZING_TOP_LEFT
        elif self.pos_to_rect_is_moving(x, y):
            return SEL_STATE_MOVING

        # fallback to redraw
        return SEL_STATE_DRAWING

    def update_cursor(self, x, y):
        """
        Update the cursor in selection with resize mode. This function
        sets the cursor to:

          * a fleur (move)
          * a corner (resize)
          * a crosshair (redraw)
        """

        cursor = self.sel_state_to_cursor[self.pos_to_sel_state(x, y)]
        self.grab_pointer(cursor)

    def set_sel_state_from_pos(self, x, y):
        """
        Sets the current selection state according to the
        cursor position.
        """

        self.selection_state = self.pos_to_sel_state(x, y)

    def get_xy_click_diffs(self, x, y):
        """
        Returns the X and Y differences from the last clicked point.
        """

        return x - self.click_x, y - self.click_y

    def rect_resize_top(self, y):
        """
        Resizes the rectangle's top side.
        """

        dist_x, dist_y = self.get_xy_click_diffs(0, y)
        new_y = self.start_rect_y + dist_y

        # avoid:
        #
        #              #########
        # .............#########.......
        # .............#########.......
        # .............................
        # .............................
        # .............................
        if new_y < 0:
            dist_y = -self.start_rect_y
            new_y = self.start_rect_y + dist_y

        new_height = self.start_rect_height - dist_y

        # make sure the rectangle does not become too small
        if new_height < self.resize_threshold_px:
            new_height = self.resize_threshold_px
            new_y = self.start_rect_bottom - self.resize_threshold_px

        self.height = new_height
        self.y = new_y

    def rect_resize_bottom(self, y):
        """
        Resizes the rectangle's bottom side.
        """

        root_size = self.root.get_size()
        dist_x, dist_y = self.get_xy_click_diffs(0, y)

        # avoid:
        #
        # .............................
        # .............................
        # .............................
        # ........######...............
        # ........######...............
        #         ######
        if self.start_rect_bottom + dist_y > root_size[1]:
            new_height = root_size[1] - self.start_rect_y
        else:
            new_height = self.start_rect_height + dist_y

        # make sure the rectangle does not become too small
        if new_height < self.resize_threshold_px:
            new_height = self.resize_threshold_px

        self.height = new_height

    def rect_resize_right(self, x):
        """
        Resizes the rectangle's right side.
        """

        root_size = self.root.get_size()
        dist_x, dist_y = self.get_xy_click_diffs(x, 0)

        # avoid:
        #
        # .............................
        # ..........................######
        # ..........................######
        # .............................
        # .............................
        if self.start_rect_right + dist_x > root_size[0]:
            new_width = root_size[0] - self.start_rect_x
        else:
            new_width = self.start_rect_width + dist_x

        # make sure the rectangle does not become too small
        if new_width < self.resize_threshold_px:
            new_width = self.resize_threshold_px

        self.width = new_width

    def rect_resize_left(self, x):
        """
        Resizes the rectangle's left side.
        """

        dist_x, dist_y = self.get_xy_click_diffs(x, 0)
        new_x = self.start_rect_x + dist_x

        # avoid:
        #
        #     .............................
        #     .............................
        #   #####..........................
        #   #####..........................
        #     .............................
        if new_x < 0:
            dist_x = -self.start_rect_x
            new_x = self.start_rect_x + dist_x

        new_width = self.start_rect_width - dist_x

        # make sure the rectangle does not become too small
        if new_width < self.resize_threshold_px:
            new_width = self.resize_threshold_px
            new_x = self.start_rect_right - self.resize_threshold_px

        self.width = new_width
        self.x = new_x

    def handle_ss_free(self, x, y):
        """
        Handles the free selection state.
        """

        # only update cursor in free state: cursor is
        # "locked" to its initial value when "grabbing"
        # since the selection state won't change until
        # the mouse button is released
        self.update_cursor(x, y)

    def handle_ss_drawing(self, x, y):
        """
        Handles the drawing selection state.
        """

        self.set_rect_size(x, y)

    def handle_ss_moving(self, x, y):
        """
        Handles the moving selection state.
        """

        root_size = self.root.get_size()
        dist_x, dist_y = self.get_xy_click_diffs(x, y)
        new_x = self.start_rect_x + dist_x
        new_y = self.start_rect_y + dist_y

        # avoid:
        #
        #     .............................
        #     .............................
        #   #####..........................
        #   #####..........................
        #     .............................
        if new_x < 0:
            new_x = 0

        # avoid:
        #
        # .............................
        # ..........................######
        # ..........................######
        # .............................
        # .............................
        if new_x + self.width > root_size[0]:
            new_x = root_size[0] - self.width

        # avoid:
        #
        #              #########
        # .............#########.......
        # .............#########.......
        # .............................
        # .............................
        # .............................
        if new_y < 0:
            new_y = 0

        # avoid:
        #
        # .............................
        # .............................
        # .............................
        # ........######...............
        # ........######...............
        #         ######
        if new_y + self.height > root_size[1]:
            new_y = root_size[1] - self.height

        self.x = new_x
        self.y = new_y

    def handle_ss_rz_top_right(self, x, y):
        """
        Handles the top-right resizing selection state.
        """

        self.rect_resize_top(y)
        self.rect_resize_right(x)

    def handle_ss_rz_bottom_right(self, x, y):
        """
        Handles the bottom-right resizing selection state.
        """

        self.rect_resize_bottom(y)
        self.rect_resize_right(x)

    def handle_ss_rz_bottom_left(self, x, y):
        """
        Handles the bottom-left resizing selection state.
        """

        self.rect_resize_bottom(y)
        self.rect_resize_left(x)

    def handle_ss_rz_top_left(self, x, y):
        """
        Handles the top-left resizing selection state.
        """

        self.rect_resize_top(y)
        self.rect_resize_left(x)

    def event_handler(self, event):
        """
        Handle mouse/keyboard events
        """
        if event.type == gtk.gdk.BUTTON_PRESS:
            x = int(event.x)
            y = int(event.y)

            if event.button != 1:
                print "Canceled by the user"
                exit(EXIT_CANCEL)

            # grab the keyboard only when selection started
            gtk.gdk.keyboard_grab(self.root)

            # keep initial click point
            self.click_x = x
            self.click_y = y

            if self.selection_resize:
                # set selection state depending on click position
                self.set_sel_state_from_pos(x, y)

                # keep initial settings needed for resizing/moving
                self.start_rect_x = self.x
                self.start_rect_right = self.right_pos
                self.start_rect_y = self.y
                self.start_rect_bottom = self.bottom_pos
                self.start_rect_width = self.width
                self.start_rect_height = self.height

                if self.selection_state == SEL_STATE_DRAWING:
                    # draw/redraw
                    self.height = 0
                    self.width = 0
                    self.x = x
                    self.y = y
            else:
                self.move(self.x, self.y)
                self.selection_state = SEL_STATE_DRAWING

        elif event.type == gtk.gdk.KEY_RELEASE:
            if gtk.gdk.keyval_name(event.keyval) == "Escape":
                print "Canceled by the user"
                exit(EXIT_CANCEL)

            if self.selection_resize:
                if gtk.gdk.keyval_name(event.keyval) == "Return":
                    # capture
                    self.ungrab()
                    self.wait()

        elif event.type == gtk.gdk.MOTION_NOTIFY:
            x = int(event.x)
            y = int(event.y)

            if self.selection_resize:
                self.sel_state_to_handle_func[self.selection_state](x, y)
            else:
                if self.selection_state == SEL_STATE_FREE:
                    return

                self.set_rect_size(x, y)

            self.draw()

            if self.width > 3 and self.height > 3:
                self.resize(self.width, self.height)
                self.move(self.x, self.y)
                self.show_all()

        elif event.type == gtk.gdk.BUTTON_RELEASE:
            x = int(event.x)
            y = int(event.y)

            if self.selection_state == SEL_STATE_FREE:
                return

            if self.selection_resize:
                if self.selection_state == SEL_STATE_DRAWING:
                    if self.click_selection:
                        # not possible to move/resize when clicking
                        self.set_rect_size(x, y)
                        self.ungrab()
                        self.wait()

                # mouse button released: back to free state
                self.selection_state = SEL_STATE_FREE
            else:
                self.set_rect_size(x, y)
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
            window = gtk.gdk.window_foreign_new(xid)
            width, height = window.get_size()
            x = y = 0

        pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8, width, height)
        # mask the pixbuf if we have more than one screen
        if window == self.root and len(self.get_geometry()) > 1:
            root_width, root_height = window.get_size()
            pb2 = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, True, 8,
                                 root_width, root_height)
            pb2 = pb2.get_from_drawable(window, window.get_colormap(),
                                        x, y, x, y,
                                        width, height)
            pb2 = self.mask_pixbuf(pb2, root_width, root_height)
            pb2.copy_area(x, y, width, height, pb, 0, 0)
        else:
            pb = pb.get_from_drawable(window, window.get_colormap(),
                                      x, y, 0, 0,
                                      width, height)

        if not pb:
            print "Invalid Pixbuf"
            exit(EXIT_INVALID_PIXBUF)
        if self.use_clipboard:
            self.save_clipboard(pb)
        else:
            self.save_file(pb, width, height)

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

        if self.command:
            command = self.command.replace("$f", self.filename)
            command = self._expand_argument(width, height, command)
            subprocess.call(command, shell=True)
        exit()

    def set_rect_size(self, ev_x, ev_y):
        """
        Set the window size when drawing
        """

        if ev_x < self.click_x:
            x = ev_x
            width = self.click_x - x
        else:
            x = self.click_x
            width = ev_x - self.click_x

        self.x = x
        self.width = width

        if ev_y < self.click_y:
            y = ev_y
            height = self.click_y - y
        else:
            height = ev_y - self.click_y
            y = self.click_y

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
        '-S', '--select-and-resize', default=False, action='store_true',
        help='interactively choose a window or rectangle with '
             'the mouse, move/resize the rectangle if needed, then '
             'press Enter to accept, or press Esc/Right Click to cancel')
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

    if args.select and args.select_and_resize:
        print "Options -s and -S cannot be enabled at the same time"
        exit()

    selection = args.select or args.select_and_resize

    Escrotum(filename=args.FILENAME, selection=selection,
             selection_resize=args.select_and_resize, xid=args.xid,
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
