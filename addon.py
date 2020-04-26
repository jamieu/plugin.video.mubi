from __future__ import absolute_import, division, unicode_literals
from kodiswift import xbmc, Plugin, ListItem, xbmcgui
from resources.lib.mubi import Mubi
import xbmcplugin

PLUGIN_NAME = 'MUBI'
PLUGIN_ID = 'plugin.video.mubi'

DRM = 'widevine'
PROTOCOL = 'mpd'
LICENSE_URL = 'https://lic.drmtoday.com/license-proxy-widevine/cenc/'
LICENSE_URL_HEADERS = 'User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.123 Safari/537.36&Host=lic.drmtoday.com&Origin=https://mubi.com&Referer=https://mubi.com/&Sec-Fetch-Dest=empty&Sec-Fetch-Mode=cors&Sec-Fetch-Site=cross-site&Accept-Encoding=gzip, deflate, br&Accept-Language=en-US,en;q=0.9&Connection=keep-alive&Content-Type=application/json;charset=utf-8'

plugin = Plugin(PLUGIN_NAME, PLUGIN_ID, __file__)

if not plugin.get_setting("username") or not plugin.get_setting("password"):
    plugin.open_settings()

mubi = Mubi(plugin.get_setting("username", unicode), plugin.get_setting("password", unicode))


@plugin.route('/')
def index():
    films = mubi.now_showing()
    items = [{
        'label': film.title,
        'is_playable': True,
        'path': plugin.url_for('play_film', identifier=film.mubi_id),
        'thumbnail': film.artwork,
        'info': film.metadata._asdict()
    } for film in films]
    return items


@plugin.route('/play/<identifier>')
def play_film(identifier):
    mubi_resolved_info = mubi.get_play_url(identifier)
    mubi_film = xbmcgui.ListItem(path=mubi_resolved_info['url'])

    if mubi_resolved_info['is_mpd']:
        mubi_film.setProperty('inputstreamaddon', 'inputstream.adaptive')
        mubi_film.setProperty('inputstream.adaptive.manifest_type', 'mpd')

        if mubi_resolved_info['is_drm']:
            xbmc.log('DRM Header: %s' %mubi_resolved_info['drm_header'], 2)
            mubi_film.setProperty('inputstream.adaptive.license_type', "com.widevine.alpha")
            mubi_film.setProperty('inputstream.adaptive.license_key', LICENSE_URL + '|' + LICENSE_URL_HEADERS + '&dt-custom-data=' + mubi_resolved_info['drm_header'] + '|R{SSM}|JBlicense')
            mubi_film.setMimeType('application/dash+xml')
            mubi_film.setContentLookup(False)
    return xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem=mubi_film)

    #return plugin


if __name__ == '__main__':
    plugin.run()
