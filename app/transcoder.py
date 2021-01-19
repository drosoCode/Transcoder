import os
import signal
import json
import re
from subprocess import Popen, PIPE
import shutil

from .log import logger
from .files import getFileInfos, getMediaPath, getSubPathFromName, getOutputDir
from .utils import configData


class transcoder:
    def __init__(
        self,
        mediaType: int,
        mediaData: int,
        outDir: str = None,
        encoder: str = configData["config"]["encoder"],
        crf: int = configData["config"]["crf"],
    ):
        if outDir is None:
            self._outDir = getOutputDir()
        else:
            self._outDir = outDir
        self._file = getMediaPath(mediaType, mediaData)
        self._fileInfos = getFileInfos(mediaType, mediaData)
        self._audioStream = "0"
        self._subStream = "-1"
        self._subFile = b""
        self._enableHLS = True
        self._startFrom = 0
        self._hlsTime = configData["config"]["hlsTime"]
        self._resize = -1
        self._encoder = encoder
        self._crf = crf
        self._outFile = self._outDir.encode("utf-8") + b"/stream"
        self._remove3D = 0
        self._runningProcess = None
        self._bitmapSubs = ["hdmv_pgs_subtitle", "dvd_subtitle"]

    def setAudioStream(self, audioStream: str):
        self._audioStream = str(audioStream)

    def setSubStream(self, subStream: str):
        try:
            int(subStream)
            self._subStream = str(subStream)
        except ValueError:
            pass

    def setSubFile(self, subFile: str):
        if subFile != "":
            self._subFile = getSubPathFromName(self._file, subFile)

    def enableHLS(self, en, time=configData["config"]["hlsTime"]):
        self._enableHLS = en
        self._hlsTime = time

    def setStartTime(self, time):
        self._startFrom = time

    def setOutputFile(self, outFile: bytes):
        self.__outFile = outFile

    def getOutputFile(self) -> bytes:
        if self._enableHLS:
            return self._outFile + b".m3u8"
        else:
            return (
                self._outFile
                + b"."
                + self._fileInfos["general"]["extension"].encode("utf-8")
            )

    def resize(self, size):
        self._resize = size

    def remove3D(self, stereoType: int):
        # stereoType is 1 for SBS (side by side) or 2 for TAB (top and bottom)
        self._remove3D = stereoType

    def getWatchedDuration(self, data):
        return float(data) + float(self._startFrom)

    def configure(self, args: dict):
        if args is not None:
            if "audioStream" in args:
                self.setAudioStream(args.get("audioStream"))
            if "subStream" in args:
                self.setSubStream(args.get("subStream"))
            if "subFile" in args:
                self.setSubFile(args.get("subFile"))
            if "startFrom" in args:
                self.setStartTime(args.get("startFrom"))
            if "resize" in args:
                self.resize(args.get("resize"))
            if "remove3D" in args:
                r3 = args["remove3D"]
                self.remove3D(int(r3))

    def getSubtitles(self) -> bytes:
        if self._subStream != "-1":
            if (
                self._fileInfos["subtitles"][int(self._subStream)]["codec"]
                in self._bitmapSubs
            ):
                # we can't easily get text content for bitmap-type subtitles
                return None
            else:
                p = Popen(
                    b'ffmpeg -loglevel panic -i "'
                    + self._file
                    + b'" -map 0:s:'
                    + self._subStream.encode("utf-8")
                    + b" -f webvtt -",
                    shell=True,
                    stdout=PIPE,
                )
                return p.stdout.read()
        elif self._subFile != b"":
            p = Popen(
                b'ffmpeg -loglevel panic -i "' + self._subFile + b'" -f webvtt -',
                shell=True,
                stdout=PIPE,
            )
            return p.stdout.read()
        else:
            return None

    def start(self) -> dict:
        if os.path.exists(self._outDir):
            shutil.rmtree(self._outDir)
        os.makedirs(self._outDir)

        filePath = self._file
        cut = b""
        if int(self._startFrom) > 0:
            if self._subStream != "-1" or self._subFile != b"":
                filePath = filePath.decode("utf-8")
                ext = filePath[filePath.rfind(".") + 1 :]
                filePath = (
                    self._outDir.encode("utf-8") + b"/temp." + ext.encode("utf-8")
                )

                cutCmd = (
                    b"ffmpeg -y -hide_banner -loglevel fatal -ss "
                    + str(self._startFrom).encode("utf-8")
                    + b' -i "'
                    + self._file
                    + b'" -c copy -map 0 '
                    + filePath
                )
                logger.info(b"Cutting file with ffmpeg:" + cutCmd)
                os.system(cutCmd)
            else:
                cut = b"-ss " + str(self._startFrom).encode("utf-8")

        cmd = b"ffmpeg -hide_banner -loglevel fatal " + cut + b' -i "' + filePath + b'"'
        cmd += b" -pix_fmt yuv420p -preset medium"

        rm3d = b""
        rm3dMeta = b""
        if self._remove3D == 1:
            rm3d = b"stereo3d=sbsl:ml[v1];[v1]"
            rm3dMeta = b' -metadata:s:v:0 stereo_mode="mono"'
        elif self._remove3D == 2:
            rm3d = b"stereo3d=abl:ml[v1];[v1]"
            rm3dMeta = b' -metadata:s:v:0 stereo_mode="mono"'

        resize = b""
        if int(self._resize) > 0:
            resize = b"[v2];[v2]scale=" + str(self._resize).encode("utf-8") + b":-1"

        if self._subStream != "-1":
            if (
                self._fileInfos["subtitles"][int(self._subStream)]["codec"]
                in self._bitmapSubs
            ):
                cmd += (
                    b' -filter_complex "[0:v]'
                    + rm3d
                    + b"[0:s:"
                    + self._subStream.encode("utf-8")
                    + b"]overlay"
                    + resize
                    + b'"'
                )
            else:
                cmd += (
                    b' -filter_complex "[0:v:0]'
                    + rm3d
                    + b"subtitles='"
                    + filePath
                    + b"':si="
                    + self._subStream.encode("utf-8")
                    + resize
                    + b'"'
                )
        elif self._subFile != b"":
            cmd += (
                b' -filter_complex "[0:v:0]'
                + rm3d
                + b"subtitles='"
                + self._subFile
                + b"':si="
                + self._subStream.encode("utf-8")
                + resize
                + b'"'
            )

        elif self._remove3D and self._remove3D > 0:
            if self._remove3D == 1:
                cmd += b' -filter_complex "[0:v:0]stereo3d=sbsl:ml' + resize + b'"'
            elif self._remove3D == 2:
                cmd += b' -filter_complex "[0:v:0]stereo3d=abl:ml' + resize + b'"'

        elif self._resize and int(self._resize) > 0:
            cmd += b' -filter_complex "' + resize[9:] + b'"'

        if self._remove3D and self._remove3D > 0:
            if "ratio" in self._fileInfos:
                cmd += b" -aspect " + self._fileInfos.get("ratio").encode("utf-8")
            else:
                cmd += b" -aspect 16:9"

        if self._audioStream != "0":
            cmd += b" -map 0:a:" + self._audioStream.encode("utf-8")
        cmd += b" -c:a aac -ar 48000 -b:a 128k -ac 2"
        cmd += rm3dMeta
        cmd += b" -c:v " + self._encoder.encode("utf-8")
        cmd += b" -crf " + str(self._crf).encode("utf-8")

        if self._enableHLS:
            cmd += (
                b" -hls_time "
                + str(self._hlsTime).encode("utf-8")
                + b" -hls_playlist_type event -hls_segment_filename "
                + self._outFile
                + b"%03d.ts "
                + self._outFile
                + b".m3u8"
            )
        else:
            cmd += b" " + self._outFile + b"." + self._fileInfos["general"]["extension"]

        logger.info(b"Starting ffmpeg with:" + cmd)
        process = Popen(b"exec " + cmd, shell=True)

        return {"pid": process.pid, "outDir": self._outDir}

    @staticmethod
    def stop(data: dict):
        if "pid" in data:
            os.kill(data["pid"], signal.SIGTERM)
        if "outDir" in data:
            os.system('rm -rf "' + data["outDir"] + '"')
