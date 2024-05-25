from hotfixes.parser import HotfixParser, Flavor

FLAVOR = Flavor.Live

GAME_PATH = "F:/Games/World of Warcraft"
DBCACHE_PATH = f"{GAME_PATH}/{FLAVOR}/Cache/ADB/enUS/DBCache.bin"

parser = HotfixParser(GAME_PATH, FLAVOR)
parser.print_hotfixes()
