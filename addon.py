from kodiswift import xbmc, Plugin, ListItem
from resources.lib.mubi import Mubi

PLUGIN_NAME = 'MUBI'
PLUGIN_ID = 'plugin.video.mubi'

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
    mubi_film = ListItem(path=mubi_resolved_info['url'])
    if mubi_resolved_info['is_mpd']:
        mubi_film.set_property('inputstreamaddon', 'inputstream.adaptive')
        mubi_film.set_property('inputstream.adaptive.manifest_type', 'mpd')
        if mubi_resolved_info['is_drm']:
            xbmc.log("Playing DRM films is not currently supported", 4)
            return None
            # drm = mubi_resolved_info['drm_item']
            # mubi_film.set_property('inputstream.adaptive.license_key', drm['lurl']+'|'+drm['header']+
            # '|B{SSM}|'+drm['license_field'])
            # mubi_film.set_property('inputstream.adaptive.license_type', "com.widevine.alpha")
    return plugin.set_resolved_url(mubi_film)


if __name__ == '__main__':
    plugin.run()
