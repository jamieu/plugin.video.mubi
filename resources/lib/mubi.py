# -*- coding: utf-8 -*-

import logging
import requests
import re
from urllib import urlencode
import urllib
import base64
import json
import pytz
from urlparse import urljoin
from collections import namedtuple
from bs4 import BeautifulSoup as BS
from multiprocessing.dummy import Pool as ThreadPool
from lang import language_to_code
try:
    from simplecache import SimpleCache
except:
    from simplecachedummy import SimpleCache
from requests.adapters import HTTPAdapter
import datetime
import HTMLParser
import pickle

#http://kodi.wiki/view/InfoLabels
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
        "login":       urljoin(_URL_MUBI, "session/new"),
        "session":     urljoin(_URL_MUBI, "session"),
        "nowshowing":  urljoin(_URL_MUBI, "showing"),
        "video":       urljoin(_URL_MUBI, "showing/%s/watch"),
        "prescreen":   urljoin(_URL_MUBI, "showing/%s/prescreen"),
        "filmdetails": urljoin(_URL_MUBI, "showing/%s"),
        "filmcast":    urljoin(_URL_MUBI, "films/%s/cast"),
        "logout":      urljoin(_URL_MUBI, "logout"),
        "account":     urljoin(_URL_MUBI, "account")
    }

    def __init__(self, username, password):
        self._logger = logging.getLogger('mubi.Mubi')
        self._logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        self._logger.addHandler(handler)
        self._entparser = HTMLParser.HTMLParser()
        self._cache_prefix = "plugin.video.mubi.cached_obj"
        self._simplecache = SimpleCache()
        self._username = username
        self._password = password
        self._threaded = True
        pickled_session = self._simplecache.get("%s.session" % self._cache_prefix)
        if pickled_session:
            cached_session = pickle.loads(pickled_session)
            if (self.is_logged_in(cached_session)):
                self._logger.debug("Already logged in, using cached session")
                self._session = cached_session
            else:
                self.login()
        else:
            self.login()
        self._simplecache.set("%s.session" % self._cache_prefix, pickle.dumps(self._session), expiration=datetime.timedelta(days=30))

    def is_logged_in(self,session):
        r = session.head(self._mubi_urls["account"], allow_redirects=False)
        return r.status_code == 200
        

    def login(self):
        self._session = requests.session()
        self._session.mount(self._URL_MUBI, HTTPAdapter(max_retries=5))
        self._session.headers = {'User-Agent': self._USER_AGENT}
        login_page = self._session.get(self._mubi_urls["login"]).content
        auth_token = BS(login_page,'html.parser').find("input", {"name": "authenticity_token"}).get("value")
        session_payload = {'utf8': '✓',
                           'authenticity_token': auth_token,
                           'session[email]': self._username,
                           'session[password]': self._password }

        self._logger.debug("Logging in as user '%s', auth token is '%s'" % (self._username, auth_token))

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
        page_region = BS(page,'html.parser').find('div', { 'id': 'page-region' })
        
        # Top half of page
        trailer_region = page_region.find('div', { 'id': 'trailer-region' })
        show_info = trailer_region.find('div', { 'class': 'film-show__info' })

        film_details['genre'] = self._entparser.unescape(show_info.find('div', { 'class': 'film-show__genres' }).text)

        film_details['duration'] = int(show_info.find('time', { 'itemprop': 'duration' }).text)*60
        
        alt_title = trailer_region.find('h2', { 'class': 'film-show__titles__title-alt' })
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

        lang_info = show_info.find('ul', { 'class': 'film-meta' }).findAll('li')
        offset = 0 if len(lang_info) == 3 else 1

        # These fields don't seem to do anything, I'll just place it in the plot
        audio_lang = lang_info[1+offset].text.strip()
        audio_code = language_to_code(audio_lang)
        if audio_code:
            stream_info['audio'] = { 'language': audio_code }
        sub_lang = lang_info[2+offset].text.strip()
        sub_code = language_to_code(sub_lang)
        if sub_code:
            stream_info['subtitle'] = { 'language': sub_code }
        film_details['plot'] = ("Language: %s, Subtitles: %s\n" % (audio_lang,sub_lang)) + film_details['plot']

        cast_region = BS(page,'html.parser').find('ul', {'class': 'cast-member-media'})
        members = cast_region.findAll('li', {'class': 'cast-member-media__item'})
        cast = []
        for m in members:
            name = self._entparser.unescape(m.find( 'span', { 'class': 'cast-member-media__header' }).text)
            role = m.find( 'span', { 'class': 'cast-member-media__subheader' }).text
            img = m.find('img')['src'] # If not present, it will have placeholder in string
            # We can get an image at this point but I don't think Kodi supports setting it for cast members
            # https://forum.kodi.tv/showthread.php?tid=118845&page=2
            # https://forum.kodi.tv/showthread.php?tid=287683
            cast.append((name,role))
        film_details['castandrole'] = cast

        result = (film_details,stream_info)
        return result

    def generate_entry(self,x):
        mubi_id_elem = x.find('a', {"data-filmid": True})

        if not mubi_id_elem:
            # either a "Coming soon" or a "Just left" movie
            return None

        # core
        mubi_id   = mubi_id_elem.get("data-filmid")
        cached = self._simplecache.get("%s.%s" % (self._cache_prefix, mubi_id))
        if cached:
            return pickle.loads(cached)

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
        result = Film(listview_title, mubi_id, artwork, metadata, film_stream)
        cached = self._simplecache.set("%s.%s" % (self._cache_prefix, mubi_id), pickle.dumps(result), expiration=datetime.timedelta(days=32))
        return result

    def now_showing(self):
        cached_showing = self._simplecache.get("%s.now_showing" % self._cache_prefix)
        if cached_showing:
            return pickle.loads(cached_showing)
        page = self._session.get(self._mubi_urls["nowshowing"])
        items = [x for x in BS(page.content,'html.parser').findAll("article")]
        if self._threaded:
            pool = ThreadPool(10)
            films = pool.map(self.generate_entry,items)
        else:
            films = []
            for elem in items:
                films.append(self.generate_entry(elem))
        # Filter out empty ones
        films = [f for f in films if f]
        # Get time until midnight PDT
        cur = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(pytz.timezone('US/Pacific'))
        seconds = (cur.replace(hour=23, minute=59, second=59, microsecond=999) - cur).total_seconds()
        self._simplecache.set("%s.now_showing" % self._cache_prefix, pickle.dumps(films), expiration=datetime.timedelta(seconds=seconds))
        return films

    def enable_film(self, name):
        # Sometimes we have to load a prescreen page first before we can retrieve the film's secure URL
        # ie. https://mubi.com/showing/lets-get-lost/prescreen --> https://mubi.com/showing/lets-get-lost/watch
        self._logger.debug("Enabling film: '%s'" % name)
        self._session.head(self._mubi_urls["prescreen"] % name, allow_redirects=True)
        self._logger.debug("Finished enabling film: '%s'" % name)

    def get_play_url(self, name):
        video_page_url = self._mubi_urls["video"] % name
        video_page = BS(self._session.get(video_page_url).content,'html.parser')
        video_data_elem = video_page.find(attrs={"data-secure-url": True})
        video_data_url = video_data_elem.get("data-secure-url")
        # Mubi are using MPD(dash), and Kodi autodetects on extension
        matched_url = re.match('^(.*\.mpd).*',video_data_url)
        is_drm = "drm" in video_data_url
        drm_item = {}
        if not matched_url:
            self._logger.debug("Warning: stream returned not in mpd format")
            clean_url = video_data_url
            is_mpd = False
        else:
            clean_url = matched_url.group(1)
            is_mpd = True
            if is_drm: #Is DRM
                drm_block = [drmconf for drmconf in video_page.findAll('script') if 'DrmConfig' in drmconf.text]
                fields = { 'username': '.*username: \"([^\"]+)\".*', 'accountCode': '.*accountCode: \"([^\"]+)\".*', 'transaction': '.*transaction: \"([^\"]+)\".*', 'widevineLicenseServerURL': '.*widevineLicenseServerURL: \"([^\"]+)\".*' }
                result = {}
                for k,v in fields.iteritems():
                    result[k] = re.search(v,drm_block[0].text).group(1)
                header = {"userId": long(result['username']), "sessionId": result['transaction'], "merchant": result['accountCode']}
                # This might need optdata in header however looking in requests during browser negotiation I don't see it
                # https://stackoverflow.com/questions/35792897/http-request-header-field-optdata
                # The best conversation for this is:
                # https://github.com/emilsvennesson/kodi-viaplay/issues/9
                drm_item = { 'header': "dt-custom-data="+urllib.quote_plus(base64.b64encode(json.dumps(header).encode())), 'lurl': result['widevineLicenseServerURL'], 'license_field': "" }
        self._logger.debug("Got video info as: '%s'" % clean_url)
        item_result = { 'url': clean_url, 'is_mpd': is_mpd, 'is_drm': is_drm, 'drm_item': drm_item }
        self._logger.debug("Got video info as: '%s'" % json.dumps(item_result))
        return item_result

