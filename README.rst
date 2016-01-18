Escrotum
========

Linux screen capture using pygtk, inspired by scrot

Why?
----

Because scrot has glitches when selection is used in refreshing windows

Features
--------

* fullscreen screenshots
* partial(selection) screenshots
* window screenshot(click to select)
* screenshot by xid
* store the image to the clipboard
* make multiple screenshots

  - every x seconds
  - on every key press (Linux only)

::

  usage: escrotum [-h] [-v] [-s] [-x XID] [-d DELAY]
                  [--selection-delay SELECTION_DELAY] [-c] [-r REPEAT] [-k] [-C]
                  [-e COMMAND]
                  [FILENAME]

  Minimalist screenshot capture program inspired by scrot.

  positional arguments:
    FILENAME              image filename, default is
                          %Y-%m-%d-%H%M%S_$wx$h_escrotum.png

  optional arguments:
    -h, --help            show this help message and exit
    -v, --version         output version information and exit
    -s, --select          interactively choose a window or rectangle with the
                          mouse, cancels with Esc or Right Click
    -x XID, --xid XID     take a screenshot of the xid window
    -d DELAY, --delay DELAY
                          wait DELAY seconds before taking a shot
    --selection-delay SELECTION_DELAY
                          delay in milliseconds between selection/screenshot
    -c, --countdown       show a countdown before taking the shot (requires
                          delay)
    -r REPEAT, --repeat REPEAT
                          number of screenshots to take, waiting DELAY each time
    -k, --on-key-press    make screenshot on every (visible) key press (only
                          Linux)
    -C, --clipboard       store the image on the clipboard
    -e COMMAND, --exec COMMAND
                          run the command after the image is taken

    SPECIAL STRINGS
    Both the --exec and filename parameters can take format specifiers
    that are expanded by escrotum when encountered.

    There are two types of format specifier. Characters preceded by a '%'
    are interpreted by strftime(2). See man strftime for examples.
    These options may be used to refer to the current date and time.

    The second kind are internal to escrotum and are prefixed by '$'
    The following specifiers are recognised:
          $f image path/filename (ignored when used in the filename)
          $w image width
          $h image height
    Example:
          escrotum '%Y-%m-%d_$wx$h_escrotum.png'
          Creates a file called something like 2013-06-17-082335_263x738_escrotum.png

    EXIT STATUS CODES
    1 can't get the window by xid
    2 invalid pixbuf
    3 can't save the image
    4 user canceled selection

Install
-------

* on archlinux, yaourt -S escrotum-git
* with pip, pip install escrotum

To get the option --on-key-press to work you need to install from git:

::

  git clone https://github.com/Roger/escrotum.git
  cd escrotum
  git submodule init
  git submodule update

or simple:

::

  git clone --recursive https://github.com/Roger/escrotum.git

And, until Andrew Moffat update his repository, you need to:

::

  touch escrotum/pykeylogger/__init__.py

Credits
-------

* Roger Duran
* Andrew Moffat (pykeylogger, used for screenshots on every key press)
* Adriano Grieb (multiple screenshots options)
