# -*- coding: utf-8 -*-

import logging
import requests
import re
from urllib import urlencode
import urllib
from urlparse import urljoin
from collections import namedtuple
from BeautifulSoup import BeautifulSoup as BS
import HTMLParser

Film      = namedtuple('Film', ['title', 'mubi_id', 'artwork', 'metadata','stream_info'])
Metadata  = namedtuple('Metadata', ['title', 'director', 'year', 'duration', 'country', 'plotoutline', 'plot', 'overlay', 'genre', 'originaltitle', 'rating', 'votes', 'castandrole'])

class Mubi(object):
    _URL_MUBI         = "https://mubi.com"
    _USER_AGENT       = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36"
    _regexps = {
        "image_url":  re.compile(r"url\((.*)\)"),
        "country_year":  re.compile(r"(.*)\, ([0-9]{4})")
    }
    _mubi_urls = {
        "login":      urljoin(_URL_MUBI, "session/new"),
        "session":    urljoin(_URL_MUBI, "session"),
        "nowshowing": urljoin(_URL_MUBI, "showing"),
        "video":      urljoin(_URL_MUBI, "showing/%s/watch"),
        "prescreen":  urljoin(_URL_MUBI, "showing/%s/prescreen"),
        "filmdetails": urljoin(_URL_MUBI, "showing/%s"),
        "filmcast": urljoin(_URL_MUBI, "films/%s/cast"),
        "logout":     urljoin(_URL_MUBI, "logout"),
    }

    def __init__(self):
        self._logger = logging.getLogger('mubi.Mubi')
        self._logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        self._logger.addHandler(handler)
        self._session = requests.session()
        self._session.headers = {'User-Agent': self._USER_AGENT}
        self._entparser = HTMLParser.HTMLParser()

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
                           'session[password]': password }

        self._logger.debug("Logging in as user '%s', auth token is '%s'" % (username, auth_token))

        r = self._session.post(self._mubi_urls["session"], data=session_payload, allow_redirects=False)
        if r.status_code == 302:
            self._logger.debug("Login succesful")
        else:
            self._logger.error("Login failed")
        return r.status_code

    def film_info(self,filmid):
        film_details = {}
        stream_info = {}
        page = self._session.get(self._mubi_urls["filmdetails"] % filmid, allow_redirects=True).text
        page_region = BS(page).find('div', { 'id': 'page-region' })
        
        # Top half of page
        trailer_region = page_region.find('div', { 'id': 'trailer-region' })
        show_info = trailer_region.find('div', { 'class': 'film-show__info' })

        film_details['genre'] = show_info.find('div', { 'class': 'film-show__genres' }).text

        film_details['duration'] = int(show_info.find('time', { 'itemprop': 'duration' }).text)*60
        
        alt_title = trailer_region.find('h2', { 'class': 'film-show__titles__title-alt condensed-header' })
        if alt_title:
            film_details['originaltitle'] = self._entparser.unescape(alt_title.text)
        else:
            film_details['originaltitle'] = None

        sect_descriptions = trailer_region.findAll('section', { 'class': 'film-show__descriptions__row' })
        synopsis = sect_descriptions[0].find('p').text
        our_take = sect_descriptions[1].find('p').text

        film_details['plot'] = self._entparser.unescape("Synopsis: %s\n\nOur take: %s" % (synopsis, our_take))

        rating_info = trailer_region.find('div', {'class': 'film-show__average-rating' })
        film_details['rating'] = float(rating_info.find('div', { 'class': 'average-rating__overall' }).text)*2
        film_details['votes'] = " R".join(rating_info.find('div', { 'class': 'average-rating__total' }).text.split('R'))

        lang_info = show_info.find('ul', { 'class': 'film-meta film-show__film-meta light-on-dark' }).findAll('li')
        offset = 0 if len(lang_info) == 3 else 1
        stream_info['audio'] = { 'language': lang_info[1+offset].text }
        stream_info['subtitle'] = { 'language': lang_info[2+offset].text }

        cast_region = BS(page).find('div', {'class': 'entity-body-section'}).find('ul', {'class': 'cast-member-media cast-member-media--film-page'})
        members = cast_region.findAll('span', {'class': 'cast-member-media__info'})
        cast = []
        for m in members:
            name = self._entparser.unescape(m.find( 'span', { 'class': 'cast-member-media__header condensed-header' }).text)
            role = m.find( 'span', { 'class': 'cast-member-media__subheader condensed-upper' }).text
            # We can get an image at this point but I don't think Kodi supports setting it for cast members
            cast.append((name,role))
        film_details['castandrole'] = cast

        return (film_details,stream_info)

    def now_showing(self):
        page = self._session.get(self._mubi_urls["nowshowing"])
        films = []
        items = [x for x in BS(page.content).findAll("article")]
        for x in items:
            mubi_id_elem = x.find('a', {"data-filmid": True})

            if not mubi_id_elem:
                # either a "Coming soon" or a "Just left" movie
                continue

            # core
            mubi_id   = mubi_id_elem.get("data-filmid")
            title     = x.find('h2').text

            meta = x.find('h3');

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

            plotoutline = x.find('p').text

            (film_meta,film_stream) = self.film_info(mubi_id)
            plot = film_meta['plot']

            if x.find('i', {"aria-label": "HD"}):
                hd = True
            else:
                hd = False

            # metadata - ideally need to scrape this from the film page or a JSON API
            metadata = Metadata(
                title=title,
                director=self._entparser.unescape(director),
                year=year,
                duration=film_meta['duration'],
                country=country,
                plotoutline=plotoutline,
                plot=plot,
                overlay=6 if hd else 0,
                genre=film_meta['genre'],
                originaltitle=film_meta['originaltitle'],
                rating=film_meta['rating'],
                votes=film_meta['votes'],
                castandrole=film_meta['castandrole']
            )

            # format a title with the year included for list_view
            #listview_title = u'{0} ({1})'.format(title, year)
            listview_title = title
            if hd:
                listview_title += " [HD]"

            f = Film(listview_title, mubi_id, artwork, metadata, film_stream)

            films.append(f)
        return films

    def enable_film(self, name):
        # Sometimes we have to load a prescreen page first before we can retrieve the film's secure URL
        # ie. https://mubi.com/showing/lets-get-lost/prescreen --> https://mubi.com/showing/lets-get-lost/watch
        self._logger.debug("Enabling film: '%s'" % name)
        self._session.head(self._mubi_urls["prescreen"] % name, allow_redirects=True)
        self._logger.debug("Finished enabling film: '%s'" % name)

    def get_play_url(self, name):
        video_page_url = self._mubi_urls["video"] % name
        video_page = self._session.get(video_page_url).content
        video_data_elem = BS(video_page).find(attrs={"data-secure-url": True})
        video_data_url = video_data_elem.get("data-secure-url")
        # Mubi are using MPD(dash), and Kodi autodetects on extension
        matched_url = re.match('^(.*\.mpd).*',video_data_url)
        if not matched_url:
            self._logger.debug("Warning: stream returned not in mpd format")
            clean_url = video_data_url
        else:
            clean_url = matched_url.group(0)
        self._logger.debug("Got video url as: '%s'" % clean_url)
        return clean_url

