from __future__ import print_function
import os, sys
from getpass import getpass
from gmusicapi import Mobileclient
import argparse
import mutagen
import mutagen.easyid3

VERSION  = "0.0.2"
_DEBUG_FLAG = "false"
_PRETEND_FLAG = "false"
_EXTENSION_LIST_FILE = "common_audio_ext.txt"

def song_info_to_string(song):
    return "%s - %i - %s on %s (%s)" % (
            song['artist'],
            song['tracknumber'] if song['tracknumber'] else 0,
            song['title'],
            song['album'],
            '*'*song['rating'])

def match(local, remote):
    '''
    Returns a score which shows the number of (standard) fields that are equal.
    Fields are: album name, artist name, track and year.
    '''
    score = 0
    if local['album'].lower() == remote['album'].lower():
        score += 1
    if local['artist'].lower() == remote['artist'].lower():
        score += 1
    if local['tracknumber'] == remote['trackNumber']:
        score += 1
    if local['year'] == remote['year']:
        score += 1
    return score

def google_music_login():
    '''
    Ask for credentials and log into Google music.
    '''
    sys.stdout.write("Connecting to Google Music ...\n")
    api = Mobileclient()
    logged_in = False
    attempts = 0
    while not logged_in and attempts < 3:
        email = raw_input("Email: ")
        password = getpass()
        logged_in = api.login(email, password)
        attempts += 1
    if not api.is_authenticated():
        print("Login failed.", file=sys.stderr)
        return None
    sys.stdout.write("Successfully logged in.\n")
    return api

def read_gmusic_lib(api):
    if not api.is_authenticated():
        print("Authentication failed!", file=sys.stderr)
        sys.exit()
    gm_lib = api.get_all_songs()
    return gm_lib

def read_tag(fullpath, ftype):
    try:
        mutag = mutagen.File(fullpath)
        if ftype == "mp3":
            id3 = mutagen.easyid3.EasyID3(fullpath)
            for k, v in id3.items():
                mutag[k] = v
            if "TXXX:FMPS_Rating" in mutag:
                mutag["rating"] = float(mutag["TXXX:FMPS_Rating"].text[0])
        else:
            mutag["rating"] = float(mutag["fmps_rating"][0])
        tag = {}
        for k, v in mutag.items():
            if type(v) is list:
                if len(v) == 1:
                    tag[k] = v[0]
            else:
                tag[k] = v
        if 'album' in tag:
            tag['album'] = tag['album'][0]
        if 'title' in tag:
            tag['title'] = tag['title'][0]
        if 'artist' in tag:
            tag['artist'] = tag['artist'][0]
        if 'tracknumber' in tag:
            tnum = tag['tracknumber']
            tnum = tnum.split("/")[0]
            tag['tracknumber'] = int(tnum)
        if 'year' in tag:
            tag['year'] = int(tag['year'][0])
        if 'rating' in tag:
            tag['rating'] = int(tag['rating']*5)
    except Exception:
        # TODO: Handle exception or print meaningful error
        #for k, v in tag.items():
        #    print("%s - %s" % (k, str(v)))
        raise
    return tag

def read_local_lib(music_root, extension_list):
    local_lib = []
    for dirpath, dirnames, filenames in os.walk(music_root):
        for fname in filenames:
            _, fext = os.path.splitext(fname)
            fext = fext[1:].lower()
            if fext+"\n" not in extension_list:
                continue
            fullpath = os.path.join(dirpath, fname)
            tag = read_tag(fullpath, fext)
            local_lib.append(tag)
            print("\r%i" % len(local_lib), end=" ...")
            sys.stdout.flush()
    return local_lib

def update_remote_lib(remote_lib, track):
    '''
    First retrieves a list of all songs that match the song title, then checks
    for items that match the rest of the fields.
    The remote track dictionary is returned but with a modified rating.
    Currently, the following fields are checked:
        - song title
        - album name
        - tracknumber
        - artist
        - year
    Additional fields that could be considered (TODO):
        - duration
    '''
    remote_tracks = [rtrack for rtrack in remote_lib\
            if rtrack['title'].lower() == track['title'].lower()]

    matches = []
    for rt in remote_tracks:
        score = match(track, rt)
        if score >= 2:
            # Just look for a match rating of 2+ for now
            matches.append((score, rt))
    if len(matches) == 1:
        remote_track = matches[0][1]
        #sys.stdout.write("Updating rating for song %s\n" % (
        #    song_info_to_string(remote_track)))
        #sys.stdout.write("----> new metadata: %s\n" % (
        #    song_info_to_string(track)))
        if remote_track['rating'] == track['rating']:
            remote_track == None
        else:
            remote_track['rating'] = track['rating']
    elif len(matches) == 0:
        #sys.stdout.write("No matching song found in remote library.\n")
        #sys.stdout.write("Song info: %s\n" % (
        #    song_info_to_string(track)))
        remote_track = None
    else:
        # PICK HIGHEST RATED TRACK
        #sys.stdout.write('---\n\n')
        #sys.stdout.write("Multiple matching songs found in remote library.\n")
        #sys.stdout.write("Local song info: %s\n" % (
        #    song_info_to_string(track)))
        #sys.stdout.write("Matching songs:\n")
        #for m in matches:
        #    sys.stdout.write("%s - match score: %i\n" % (
        #        song_info_to_string(m[1]), m[0]))
        #best_match = max(matches, key=lambda m: m[0])
        #sys.stdout.write("Best match is %s\n" % (
        #                                song_info_to_string(best_match[1])))
        #ask = True
        #while ask:
        #    yesno = raw_input("Accept best match? [Y/n] ")
        #    if yesno.lower() == 'y' or yesno == '':
        #        remote_track = best_match[1]
        #        if remote_track['rating'] == track['rating']:
        #            remote_track = None
        #        ask = False
        #    elif yesno.lower() == 'n':
        #        remote_track = None
        #        ask = False
        best_match = max(matches, key=lambda m: m[0])
        remote_track = best_match[1]
        remote_track['rating'] = track['rating']
    return remote_track

def get_new_ratings(local_lib, remote_lib):
    new_remotes = []
    for local_track in local_lib:
        if local_track['rating'] == 0:
            # Nothing to do here
            continue
        remote_track = update_remote_lib(remote_lib, local_track)
        if remote_track is not None:
            new_remotes.append(remote_track)
    return new_remotes

def update_metadata(api, library):
    sys.stdout.write("Changing the ratings for %i songs ... " % len(library))
    sys.stdout.flush()
    api.change_song_metadata(library)
    sys.stdout.write("done.\n")
    return

def read_extensions(filename):
    extlist = []
    with open(filename, 'r') as extfile:
        extlist = extfile.readlines()
    return extlist

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Synchronise music ratings between libraries.')
    parser.add_argument('musicdir', metavar='MUSICDIR', type=str,
                        help="Local music directory")
    #parser.add_argument('--dry-run', '-d', action='store_true',
    #        help='don\'t commit any changes')
    #parser.add_argument('--dump-db', metavar='dbname', type=str,
    #        help='read a database and dump it using python pickle')
    args = parser.parse_args()
    music_root = args.musicdir
    #api = google_music_login()
    api = None
    if api is None:
        #sys.exit()
        pass
    try:
        print("Loading extension list ... ", end="")
        sys.stdout.flush()
        extension_list = read_extensions(_EXTENSION_LIST_FILE)
        print("done!")
        print("Reading Google music library ... ", end="")
        sys.stdout.flush()
        #gmusic_lib = read_gmusic_lib(api)
        print("done!")
        print("Reading tags from local library [%s] " % music_root)
        local_lib = read_local_lib(music_root, extension_list)
        print("done!")
        print("Checking for mismatched ratings ... ",  end="")
        sys.stdout.flush()
        #gmusic_updated_lib = get_new_ratings(local_lib, gmusic_lib)
        print("done!")
        #update_metadata(api, gmusic_updated_lib)
    except Exception:
        #api.logout()
        raise
    #api.logout()
