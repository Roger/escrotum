Escrotum (`Help Wanted! <https://github.com/Roger/escrotum/issues/44>`_)
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

::

    Usage: escrotum [filename]

    Options:
      -h, --help                show this help message and exit
      -v, --version             output version information and exit
      -s, --select              interactively choose a window or rectangle with the mouse,
                                cancels with Esc or Rigth Click
      -x XID, --xid=XID         take a screenshot of the xid window

      -d DELAY, --delay=DELAY   wait DELAY seconds before taking a shot
      -c, --countdown           show a countdown before taking the shot
      -C, --clipboard           store the image on the clipboard
      SPECIAL STRINGS
      filename parameters can take format specifiers
      that are expanded by escrotum when encountered.
      There are two types of format specifier. Characters preceded by a '%'
      are interpretted by strftime(2). See man strftime for examples.
      These options may be used to refer to the current date and time.
      The second kind are internal to escrotum  and are prefixed by '$'
      The following specifiers are recognised:
            $w image width
            $h image height
      Example:
            escrotum '%Y-%m-%d_$wx$h_scrotum.png'
            Creates a file called something like 2013-06-17-082335_263x738_escrotum.png

Install
-------

* on archlinux, yaourt -S escrotum-git
* with pip, pip install escrotum
