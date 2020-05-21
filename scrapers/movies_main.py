# coding: utf-8
import re
import os
import json
import requests
import urllib.parse
from importlib import import_module
from base64 import b64encode

class movies:

    def __init__(self, logger, dbConnection, apiKeys):
        self._logger = logger
        self._apiKeys = apiKeys
        self._supportedFiles = ["mkv","mp4","avi"]
        self._connection = dbConnection
        self._scrapers = []
        self.importScrapers()
        self._currentMovie = None
        logger.info('Movies Indexer Initialised Successfully')
        logger.info('Supported file formats: '+str(self._supportedFiles))

    def encodeImg(self, img):
        if img is not None and img != "":
            return b64encode(img.encode()).decode()
        else:
            return None

    def importScrapers(self):
        for i in os.listdir('scrapers/'):
            if 'movies_' in i and i[i.rfind('.')+1:] == 'py' and 'main' not in i:
                try:
                    scraperName = i[i.rfind('_')+1:i.rfind('.')]
                    module = import_module('movies_'+scraperName)
                    my_class = getattr(module, scraperName)
                    if my_class.__name__ in self._apiKeys:
                        instance = my_class(self._apiKeys[my_class.__name__])
                        self._scrapers.append(instance)
                        self._logger.info('Scraper '+str(my_class.__name__)+' successfully initialised')
                    else:
                        self._logger.warning('Failed to import scraper '+str(my_class.__name__))
                except:
                    self._logger.warning('Failed to import scraper '+str(my_class.__name__))

    def getName(self, fileName):
        fileName = fileName[fileName.rfind('/')+1:]
        regex = "(?i)^(.+?)[._( \\t]*(?:(19\\d{2}|20(?:0\\d|1[0-9]))|(fansub|VOST|bluray|\\d+p|brrip|webrip|hevc|x26|h26)|(\\[.*\\])|(mkv|avi|mpe?g|mp4)$)"
        find = re.findall(regex, fileName)
        year = -1
        if len(find) > 0 and len(find[0][0]) > 0:
            name = find[0][0]
            if len(find[0][1]) == 4:
                year = find[0][1]
        else:
            name = fileName[:fileName.rfind('.')]
        name = name.replace('_', ' ').replace('.', ' ')

        return (name, year)

    def getMovieData(self):
        cursor = self._connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM movies ORDER BY title;")
        dat = cursor.fetchall()
        paths = []
        movies = {}
        for i in dat:
            paths.append(i["path"])
            movies[i["path"]] = i
        return paths, movies

    def scanDir(self, path, recursive=False, addPath=''):
        self._logger.info('Scan Dir Triggered, recursive: '+str(recursive)+' ; current Movie: '+str(self._currentMovie))
        self._paths, self._movies = self.getMovieData()
        
        for item in os.listdir(path):
            self._logger.debug('New Item: '+str(item))

            if os.path.isdir(os.path.join(path,item)):
                self._logger.debug('Item is a directory')
                self.scanDir(path, True, os.path.join(addPath, item))
            else:
                self._logger.debug('Item is a file')
                self.scanMovie(os.path.join(addPath, item))
                
        self._logger.debug('End of scan (recursive: '+str(recursive)+')')
    

    def scanMovie(self, item):
        cursor = self._connection.cursor(dictionary=True)
        commit = False

        if item in self._paths:
            self._logger.debug('Entries for this item exists in database')

            if self._movies[item]["forceUpdate"] and self._movies[item]["scraperName"] and self._movies[item]["scraperID"]:
                self._logger.debug('Item is marked as force update')
                #movie must be updated
                result = []
                for s in self._scrapers:
                    #create empty dict
                    result = {'title': None,'desc': None, 'icon': None, 'fanart': None, 'premiered': None, 'rating': None,'genres': None, 'scraperData': None}
                    if s.__class__.__name__ == self._movies[item]["scraperName"]:
                        result.update(s.getMovie(self._movies[item]["scraperID"]))
                        break
                data = (result["title"], result["desc"], self.encodeImg(result["icon"]), self.encodeImg(result["fanart"]), result["rating"], result["premiered"], json.dumps(result["genres"]), item, self._movies[item]["idMovie"])
                cursor.execute("UPDATE movies SET title = %s, overview = %s, icon = %s, fanart = %s, rating = %s, premiered = %s, genre = %s, path = %s, forceUpdate = 0, multipleResults = NULL WHERE idMovie = %s;", data)
                commit = True

                self._logger.debug('Updating database with: '+str(data))

            elif self._movies[item]["multipleResults"]:
                #there are multiple matches for scraper, cannot create entries
                self._logger.debug('Item match multipleResults, ignoring')
        else:
            #entries for this tvs doesn't exists, create entry with multipleResults
            self._logger.debug('Entries for this item doesn\'t exists in database')

            results = []
            for s in self._scrapers:
                data = s.searchMovie(*self.getName(item))
                if isinstance(data, dict):
                    data = [data]
                results += data

            self._logger.debug('The multipleResults are: '+str(results))
            cursor.execute("INSERT INTO movies (multipleResults, path) VALUES (%s, %s);", (json.dumps(results), item))
            commit = True

        if commit:
            self._connection.commit()
            self._logger.debug(str(cursor.rowcount)+'were affected')
