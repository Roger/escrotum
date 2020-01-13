import os
import subprocess
from .util import cmd_exists


class Ffmpeg:
    def __init__(self, x, y, w, h, output):
        self.x, self.y = x, y
        self.w, self.h = w, h

        self.output = output

        self.display = os.environ["DISPLAY"]
        if cmd_exists("avconv"):
            self.binary = "avconv"
        elif cmd_exists("ffmpeg"):
            self.binary = "ffmpeg"
        else:
            raise Exception("ffmpeg or avconv not found")

    def start(self):
        video_input = "%s+%s,%s" % (self.display, self.x, self.y)
        video_size = "%sx%s" % (self.w, self.h)
        # Based on presets from
        # EasyScreenCast GNOME Extension
        # Google's Media Core Technologies Live Encoding examples
        cmd = [
            self.binary,
            '-loglevel', 'error',
            # force overwrite file
            '-y',
            '-hide_banner',
            '-video_size', video_size,
            '-f', 'x11grab',
            '-i', video_input,
            # Somewhere in the code the extension is `.mkv`. Assuming VP9.
            # Google uses 'vp9' only
            '-c:v', 'libvpx-vp9',
            '-b:v', '1000k',
            '-quality', 'realtime',
            # Get threads automatically? Is it CPU threads?
            '-threads', '8',
            '-speed', '7',
            '-row-mt', '1',
            '-tile-columns', '3',
            '-frame-parallel', '1',
            '-qmin', '4',
            '-qmax', '13',
            '-r', '30',
            '-g', '90',
            self.output]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE
        )
        self.proc.poll()

        return self.proc.returncode is None

    def stop(self):
        self.proc.communicate(input=b"q")
        self.proc.wait()
