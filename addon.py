from xbmcswift2 import xbmc, xbmcgui, Plugin
from resources.lib.mubi import Mubi

PLUGIN_NAME = 'MUBI'
PLUGIN_ID = 'plugin.video.mubi'

plugin = Plugin(PLUGIN_NAME, PLUGIN_ID, __file__)

if not plugin.get_setting("username"):
    plugin.open_settings()

mubi = Mubi()
mubi.login(plugin.get_setting("username", unicode), plugin.get_setting("password", unicode))

@plugin.route('/')
def index():
    films = mubi.now_showing()
    items = [{
        'label': film.title,
        'is_playable': True,
        'path': plugin.url_for('play_film', identifier=film.mubi_id),
        'thumbnail': film.artwork,
        'info': film.metadata._asdict(),
        'stream_info': film.stream_info
    } for film in films]
    return items

@plugin.route('/play/<identifier>')
def play_film(identifier):
    mubi.enable_film(identifier)
    mubi_url = mubi.get_play_url(identifier)
    return plugin.set_resolved_url(mubi_url)


if __name__ == '__main__':
    plugin.run()
