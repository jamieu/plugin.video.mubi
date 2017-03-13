# -*- coding: utf-8 -*-

import logging
import requests
import re
from urllib import urlencode
from urlparse import urljoin
from collections import namedtuple
from BeautifulSoup import BeautifulSoup as BS

Film      = namedtuple('Film', ['title', 'mubi_id', 'artwork', 'metadata'])
Metadata  = namedtuple('Metadata', ['title', 'director', 'year', 'duration', 'country', 'plotoutline', 'plot', 'overlay'])

class Mubi(object):
    _URL_MUBI         = "http://mubi.com"
    _URL_MUBI_SECURE  = "https://mubi.com"
    _USER_AGENT       = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/537.13+ (KHTML, like Gecko) Version/5.1.7 Safari/534.57.2"
    _regexps = {
        "watch_page":  re.compile(r"^.*/watch$"),
        "image_url":  re.compile(r"\((.*)\)"),
        "country_year":  re.compile(r"(.*)\, ([0-9]{4})")
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

        r = self._session.post(self._mubi_urls["session"], data=session_payload)
        if r.status_code == 302:
            self._logger.debug("Login succesful")
        else:
            self._logger.error("Login failed")

    def now_showing(self):
        page = self._session.get(self._mubi_urls["nowshowing"])
        films = []
        items = [x for x in BS(page.content).findAll("article")]
        for x in items:

            # core
            mubi_id   = x.find('a', {"data-filmid": True}).get("data-filmid")
            title     = x.find('h1').text

            meta = x.find('h2');

            # director
            director = meta.find('a', {"itemprop": "director"}).parent.text

            # country-year
            country_year = meta.find('span', "now-showing-tile-director-year__year-country").text
            cyMatch = self._regexps["country_year"].match(country_year)
            if cyMatch:
                country = cyMatch.group(1)
                year = cyMatch.group(2)
            else:
                country = None
                year = None

            # artwork
            artStyle = x.find('div', {"style": True}).get("style")
            urlMatch = self._regexps["image_url"].search(artStyle)
            if urlMatch:
                artwork = urlMatch.group(1)
            else:
                artwork = None

            # format a title with the year included for list_view
            #listview_title = u'{0} ({1})'.format(title, year)
            listview_title = title

            synopsis = x.find('p').text

            if x.find('i', {"aria-label": "HD"}):
                hd = True
                listview_title = title + " [HD]"
            else:
                hd = False

            # metadata - ideally need to scrape this from the film page or a JSON API
            metadata = Metadata(
                title=title,
                director=director,
                year=year,
                duration=None,
                country=country,
                plotoutline="",
                plot=synopsis,
                overlay=6 if hd else 0
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

