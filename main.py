import os
import time
import hashlib

from dotenv import load_dotenv

from client.automation import ClientAutomation
from hotfixes.parser import HotfixParser, Flavor

load_dotenv()

FLAVOR = Flavor.Live

GAME_PATH = "F:/Games/World of Warcraft"
DBCACHE_PATH = f"{GAME_PATH}/{FLAVOR}/Cache/ADB/enUS/DBCache.bin"

parser = HotfixParser(GAME_PATH, FLAVOR)


def get_file_hash(file_path: str):
    hash_func = hashlib.new("sha256")

    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hash_func.update(chunk)

    return hash_func.hexdigest()


client = ClientAutomation(os.path.join(GAME_PATH, FLAVOR))


def run_loop():
    loop_time = 60  # seconds
    last_hash = None
    while True:
        client.launch()

        new_hash = get_file_hash(DBCACHE_PATH)
        if new_hash != last_hash:
            parser.print_hotfixes()

        last_hash = new_hash
        time.sleep(loop_time)


def run_once(launch_client: bool = False):
    if launch_client:
        client.launch()
    parser.print_hotfixes()


if __name__ == "__main__":
    launch_client = False

    run_once(launch_client=launch_client)
