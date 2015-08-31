import os
import subprocess
from utils import cmd_exists


class Ffmpeg(object):
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
        cmd = [
            self.binary,
            '-loglevel', 'error',
            # force overwrite file
            '-y',
            '-hide_banner',
            '-video_size', video_size,
            '-f', 'x11grab',
            '-i', video_input,
            self.output]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE
        )
        self.proc.poll()

        return self.proc.returncode is None

    def stop(self):
        self.proc.stdin.write("q")
        self.proc.wait()
