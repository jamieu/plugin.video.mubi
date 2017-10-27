# -*- coding: utf-8 -*-
import datetime
import dateutil.parser
import requests
import json
import hashlib
from collections import namedtuple
from kodiswift import xbmc
from urlparse import urljoin

try:
    from simplecache import SimpleCache
except:
    from simplecachedummy import SimpleCache

# All of the packet exchanges for the Android API were sniffed using the Packet Capture App
Film = namedtuple('Film', ['title', 'mubi_id', 'artwork', 'metadata'])
Metadata = namedtuple('Metadata',
                      ['title', 'director', 'year', 'duration', 'country', 'plot', 'overlay', 'genre', 'originaltitle',
                       'rating', 'votes', 'castandrole', 'trailer'])


class Mubi(object):
    _URL_MUBI = "https://mubi.com"
    _mubi_urls = {
        "login": urljoin(_URL_MUBI, "services/android/sessions"),
        "films": urljoin(_URL_MUBI, "services/android/films"),
        "film": urljoin(_URL_MUBI, "services/android/films/%s"),
        "viewing": urljoin(_URL_MUBI, "services/android/viewings/%s/secure_url"),
        "startup": urljoin(_URL_MUBI, "services/android/app_startup")
    }

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._cache_id = "plugin.video.mubi.filminfo.%s"
        self._simplecache = SimpleCache()
        # Need a 20 digit id, hash username to make it predictable
        self._udid = int(hashlib.sha1(username).hexdigest(), 32) % (10 ** 20)
        self._token = None
        self._country = None
        self.login()

    def login(self):
        payload = {'udid': self._udid, 'token': '', 'client': 'android',
                   'client_version': '3.05', 'email': self._username,
                   'password': self._password}
        xbmc.log("Logging in with username: %s and udid: %s" % (self._username, self._udid), 2)
        r = requests.post(self._mubi_urls["login"] + "?client=android", data=payload)
        if r.status_code == 200:
            self._token = json.loads(r.text)['token']
            xbmc.log("Login Successful and got token %s" % self._token, 2)
        else:
            xbmc.log("Login Failed", 4)
        self.app_startup()
        return r.status_code

    def app_startup(self):
        payload = {'udid': self._udid, 'token': self._token, 'client': 'android',
                   'client_version': '3.05'}
        r = requests.post(self._mubi_urls['startup'] + "?client=android", data=payload)
        if r.status_code == 200:
            self._country = json.loads(r.text)['country']
            xbmc.log("Successfully got country as %s" % self._country, 2)
        else:
            xbmc.log("Failed to get country: %s" % r.text, 4)
        return

    def get_film_page(self, film_id):
        cached = self._simplecache.get(self._cache_id % film_id)
        if cached:
            return json.loads(cached)
        args = "?client=android&country=%s&token=%s&udid=%s&client_version=3.05" % (self._country, self._token, self._udid)
        r = requests.get((self._mubi_urls['film'] % str(film_id)) + args)
        if r.status_code != 200:
            xbmc.log("Invalid status code %s getting film info for %s" % (r.status_code, film_id), 4)
        self._simplecache.set(self._cache_id % film_id, r.text, expiration=datetime.timedelta(days=32))
        return json.loads(r.text)

    def get_film_metadata(self, film_overview):
        film_id = film_overview['id']
        available_at = dateutil.parser.parse(film_overview['available_at'])
        expires_at = dateutil.parser.parse(film_overview['expires_at'])
        # Check film is valid, has not expired and is not preview
        now = datetime.datetime.now(available_at.tzinfo)
        if available_at > now:
            xbmc.log("Film %s is not yet available" % film_id, 2)
            return None
        elif expires_at < now:
            xbmc.log("Film %s has expired" % film_id, 2)
            return None
        hd = film_overview['hd']
        drm = film_overview['default_reel']['drm']
        audio_lang = film_overview['default_reel']['audio_language']
        subtitle_lang = film_overview['default_reel']['subtitle_language']
        # Build plot field. Place lang info in here since there is nowhere else for it to go
        drm_string = "Warning: this film cannot be played since it uses DRM\n" if drm else ""
        lang_string = ("Language: %s" % audio_lang) + ((", Subtitles: %s\n" % subtitle_lang) if subtitle_lang else "\n")
        plot_string = "Synopsis: %s\n\nOur take: %s" % (film_overview['excerpt'], film_overview['editorial'])
        # Get detailed look at film to get cast info
        film_page = self.get_film_page(film_id)
        cast = [(m['name'], m['credits']) for m in film_page['cast']]
        # Build film metadata object
        metadata = Metadata(
            title=film_overview['title'],
            director=film_overview['directors'],
            year=film_overview['year'],
            duration=film_overview['duration'] * 60,  # This is in seconds
            country=film_overview['country'],
            plot=drm_string + lang_string + plot_string,
            overlay=6 if hd else 0,
            genre=', '.join(film_overview['genres']),
            originaltitle=film_overview['original_title'],
            rating=film_overview['average_rating'] * 2,  # Out of 5, kodi uses 10
            votes=film_overview['number_of_ratings'],
            castandrole=cast,
            trailer=film_overview['trailer_url']
        )
        listview_title = film_overview['title'] + (" [HD]" if hd else "")
        return Film(listview_title, film_id, film_overview['stills']['standard'], metadata)

    def get_now_showing_json(self):
        # Get list of available films
        args = "?client=android&country=%s&token=%s&udid=%s&client_version=3.05" % (self._country, self._token, self._udid)
        r = requests.get(self._mubi_urls['films'] + args)
        if r.status_code != 200:
            xbmc.log("Invalid status code %s getting list of films", 4)
        return r.text

    def now_showing(self):
        films = [self.get_film_metadata(film) for film in json.loads(self.get_now_showing_json())]
        return [f for f in films if f]

    def get_default_reel_id_is_drm(self, film_id):
        reel_id = [(f['default_reel']['id'], f['default_reel']['drm'])
                   for f in json.loads(self.get_now_showing_json()) if str(f['id']) == str(film_id)]
        if len(reel_id) == 1:
            return reel_id[0]
        elif reel_id:
            xbmc.log("Multiple default_reel's returned for film %s: %s" % (film_id, ', '.join(reel_id)), 3)
            return reel_id[0]
        else:
            xbmc.log("Could not find default reel id for film %s" % film_id, 4)
            return None

    def get_play_url(self, film_id):
        (reel_id, is_drm) = self.get_default_reel_id_is_drm(film_id)
        args = "?client=android&country=%s&token=%s&udid=%s&client_version=3.05&film_id=%s&reel_id=%s&download=false" \
               % (self._country, self._token, self._udid, film_id, reel_id)
        r = requests.get((self._mubi_urls['viewing'] % str(film_id)) + args)
        if r.status_code != 200:
            xbmc.log("Could not get secure URL for film %s" % film_id, 4)
        url = json.loads(r.text)["url"]
        # For DRM you will have to find the following info:
        # {"userId": long(result['username']), "sessionId": result['transaction'], "merchant": result['accountCode']}
        # This might need optdata in header however looking in requests during browser negotiation I don't see it
        # https://stackoverflow.com/questions/35792897/http-request-header-field-optdata
        # The best conversation for this is:
        # https://github.com/emilsvennesson/kodi-viaplay/issues/9
        # You can pick this conversation up using Android Packet Capture
        item_result = {'url': url, 'is_mpd': "mpd" in url, 'is_drm': is_drm}
        xbmc.log("Got video info as: '%s'" % json.dumps(item_result), 2)
        return item_result
