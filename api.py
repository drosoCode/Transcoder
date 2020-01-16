import requests
import mysql.connector as sql
from indexer import scanner
import json
import os
from wakeonlan import send_magic_packet
import time
import base64

class api:

    def __init__(self, configFile):
        with open(configFile) as f:
            data = json.load(f)
            self._data = data
            self._connection = sql.connect(host=data["db"]["host"],user=data["db"]["user"],password=data["db"]["password"],database='mediaController')
            self._scanner = scanner(data["db"]["host"],data["db"]["user"], data["db"]["password"], data["api"]["tmdb"], data["api"]["tvdb"])

    def getTVSData(self):
        cursor = self._connection.cursor(dictionary=True)
        cursor.execute("SELECT idShow AS id, title, overview, icon, fanart, rating, premiered, genre, scraperName, scraperID, multipleResults, (SELECT MAX(season) FROM episodes WHERE idShow = t.idShow) AS seasons, (SELECT COUNT(idEpisode) FROM episodes WHERE idShow = t.idShow) AS episodes, CONCAT((SELECT scraperURL FROM scrapers WHERE scraperName = t.scraperName),scraperID) AS scraperLink FROM tv_shows t ORDER BY title;")
        return cursor.fetchall()
    
    def getTVSEp(self, idShow):
        cursor = self._connection.cursor(dictionary=True)
        cursor.execute("SELECT idEpisode AS id, title, overview, icon, season, episode, rating, scraperName, scraperID FROM episodes WHERE idShow = "+str(idShow)+" ORDER BY season, episode;")
        return cursor.fetchall()
    
    def setTVSID(self, idShow, id):
        self._scanner.setTVSID(idShow, id)

    def runScan(self):
        self._scanner.scanDir(self._data["paths"]["scanDirectory"])

    def getFileInfos(self, episodeID):
        os.system("./"+self._data["paths"]["ffprobe"]+" -v quiet -print_format json -show_format -show_streams "+self.getEpPath(episodeID)+" > out/data.json")

        with open("data.json","r") as f:
            dat = f.read()

        data = {
            "general":{
                "format": dat["format"]["format_long_name"],
                "duration": dat["format"]["duration"]
            },
            "audio":[],
            "subtitles":[]
        }

        for stream in dat["streams"]:
            if stream["codec_type"] == "video":
                data["general"]["video_codec"] = dat["codec_name"]
            elif stream["codec_type"] == "audio":
                data["audio"].append({"index":stream["index"], "codec":stream["codec_name"], "channels":stream["channels"], "language": dat["tags"]["language"]})
            elif stream["codec_type"] == "subtitle":
                data["subtitles"].append({"index":stream["index"], "codec":stream["codec_name"], "language": dat["tags"]["language"]})

        return data


    def getEpPath(self, idEpisode):
        cursor = self._connection.cursor(dictionary=True)
        cursor.execute("SELECT CONCAT(t.path, '/', e.path) FROM tv_shows t INNER JOIN episodes e ON t.idShow = e.idShow WHERE e.idEpisode = "+str(idEpisode)+";")
        path = self._data["paths"]["scanDirectory"]+'/'+cursor.fetchone()
        print(path)
        return path
        
    def getTranscoderUrl(self):
        return self._data["paths"]["transcoderURL"]

    def getFile(self, idEpisode, userID):
        path = self.getEpPath(idEpisode)
        extension = path[path.rfind('.')+1:]
        if extension == "mp4":
            return (True, path)
        else:
            success = False
            trys = 0
            while not success and trys < 4:
                try:
                    if requests.get(self._data["paths"]["transcoderURL"]+"/ping").text == "pong":
                        success = True
                except:
                    pass
                if not success and trys == 0:
                    mac = self._data["paths"]["transcoderMAC"]
                    mac = mac.replace(":",".")
                    send_magic_packet(mac)
                time.sleep(10)
                trys += 1
            if not success:
                return (False, False)
            else:
                requests.get(self._data["paths"]["transcoderURL"]+"/transcode?user="+str(userID)+"&file="+base64.b64encode(path))
                return (False, True)

    def getUserData(self,idUser):
        cursor = self._connection.cursor(dictionary=True)
        cursor.execute("SELECT name, icon, admin, kodiLinkBase FROM users WHERE idUser = "+str(idUser)+";")
        return cursor.fetchone()

    def authenticateUser(self, user, password):
        cursor = self._connection.cursor(dictionary=True)
        cursor.execute("SELECT toekn FROM users WHERE user = "+str(user)+" AND password = "+str(password)+";")
        dat = cursor.fetchone()
        if "token" in dat:
            return dat["token"]
        else:
            return False