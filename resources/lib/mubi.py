# -*- coding: utf-8 -*-

import logging
import requests
import re
from urllib import urlencode
from urlparse import urljoin
from collections import namedtuple
from BeautifulSoup import BeautifulSoup as BS

Film      = namedtuple('Film', ['title', 'mubi_id', 'artwork', 'metadata'])
Metadata  = namedtuple('Metadata', ['director', 'year', 'duration', 'country', 'plotoutline', 'plot'])

class Mubi(object):
    _URL_MUBI         = "http://mubi.com"
    _URL_MUBI_SECURE  = "https://mubi.com"
    _USER_AGENT       = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/537.13+ (KHTML, like Gecko) Version/5.1.7 Safari/534.57.2"
    _regexps = { "watch_page":  re.compile(r"^.*/watch$"),
                 "director_year":  re.compile(r"^(.+), (\d+)$")
               }
    _mubi_urls = {
                  "login":      urljoin(_URL_MUBI_SECURE, "login"),
                  "session":    urljoin(_URL_MUBI_SECURE, "session"),
                  "nowshowing": urljoin(_URL_MUBI, "films/showing"),
                  "video":      urljoin(_URL_MUBI, "films/%s/secure_url"),
                  "prescreen":  urljoin(_URL_MUBI, "films/%s/watch"),
                  "filmdetails": urljoin(_URL_MUBI, "films/%s"),
                  "logout":     urljoin(_URL_MUBI, "logout"),
                 }

    def __init__(self):
        self._logger = logging.getLogger('mubi.Mubi')
        self._session = requests.session()
        self._session.headers = {'User-Agent': self._USER_AGENT}

    def __del__(self):
        self._session.get(self._mubi_urls["logout"])

    def login(self, username, password):
        self._username = username
        self._password = password
        login_page = self._session.get(self._mubi_urls["login"]).content
        auth_token = (BS(login_page).find("input", {"name": "authenticity_token"}).get("value"))
        session_payload = {'utf8': '✓',
                           'authenticity_token': auth_token,
                           'session[email]': username,
                           'session[password]': password,
                           'x': 0,
                           'y': 0}
                           
        self._logger.debug("Logging in as user '%s', auth token is '%s'" % (username, auth_token))
        
        landing_page = self._session.post(self._mubi_urls["session"], data=session_payload)
        self._userid = BS(landing_page.content).find("a", "link -image").get("href").split("/")[-1]

        self._logger.debug("Login succesful, user ID is '%s'" % self._userid)

    def now_showing(self):
        #<ol class="list-now-showing">
        # <li class="film-tile film-media item -item-1">
        #    <img class="film-thumb" src="***w856/the-idiots.jpg***">
        #    <div class="film-tile-inner">
        #        <a href="/films/the-idiots" class="film-link">
        #            <div class="film-title">***The Idiots***</div>
        #            <div class="director-year">***Lars von Trier, 1998***</div>
        #        </a>
        #        <a class="app-play-film play-film" data-filmid="***423***" href="/films/the-idiots/prescreen"></a>
        #    </div>
        #    <div class="now-showing-time-remaining">
        #        <strong>**34h 30m**</strong>left
        #    </div>
        # </li>
        #<ol>
        page = self._session.get(self._mubi_urls["nowshowing"])
        items = [x for x in BS(page.content).findAll("li", {"class": re.compile('film-tile film-media item -item-*')})]
        films = []
        for x in items:

            # core 
            # added ' ' space to start of " app-play-film play-film" 7/12/2015
            mubi_id   = x.find('a', {"class": " app-play-film play-film"}).get("data-filmid")
            title     = x.find('a', {"class": "film-title tile-text-link"}).text
            artwork   = x.find('img', {"class": "film-thumb"}).get("src")
            
            # year, director and remaining
            director_year = x.find("div", {"class": "director-year"}).text
            director = self._regexps["director_year"].match(director_year).group(1)
            year = self._regexps["director_year"].match(director_year).group(2)

            # format a title with the year included for list_view
            listview_title = u'{0} ({1})'.format(title, year)

            # metadata - ideally need to scrape this from the film page or a JSON API
            metadata = Metadata(
                director=director, 
                year=year, 
                duration=None, 
                country=None, 
                plotoutline='Synopsis (not yet implemented)',
                plot=""
            )

            f = Film(listview_title, mubi_id, artwork, metadata)

            films.append(f)
        return films

    def is_film_available(self, name):
        # Sometimes we have to load a prescreen page first before we can retrieve the film's secure URL  
        # ie. https://mubi.com/films/lets-get-lost/prescreen --> https://mubi.com/films/lets-get-lost/watch  
        self._session.head(self._mubi_urls["prescreen"] % name, allow_redirects=True) 
        return True
        
        #if not self._session.get(self._mubi_urls["video"] % name):
        #    prescreen_page = self._session.head(self._mubi_urls["prescreen"] % name, allow_redirects=True)
        #    if not prescreen_page:
        #        raise Exception("Oops, something went wrong while scraping :(")
        #    elif self._regexps["watch_page"].match(prescreen_page.url):
        #        return True
        #    else:
        #        availability = BS(prescreen_page.content).find("div", "film_viewable_status ").text
        #        return not "Not Available to watch" in availability
        #else:
        #    return True

    def get_play_url(self, name):
        if not self.is_film_available(name):
            raise Exception("This film is not available.")
        return self._session.get(self._mubi_urls["video"] % name).content

