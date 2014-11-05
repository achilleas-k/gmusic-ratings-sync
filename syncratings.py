from __future__ import print_function
import os, sys
from getpass import getpass
from gmusicapi import Mobileclient
import argparse
import stagger

VERSION  = "0.0.2"
_DEBUG_FLAG = "false"
_PRETEND_FLAG = "false"
_EXTENSION_LIST_FILE = "common_audio_ext.txt"

def song_info_to_string(song):
    return "%s - %i - %s on %s (%s)" % (
            song['artist'],
            song['track'] if song['track'] else 0,
            song['name'],
            song['album'],
            '*'*song['rating'])

def match(one, two):
    '''
    Returns a score which shows the number of (standard) fields that are equal.
    Fields are: album name, artist name, track and year.
    '''
    score = 0
    if one['album'].lower() == two['album'].lower():
        score += 1
    if one['artist'].lower() == two['artist'].lower():
        score += 1
    if one['track'] == two['track']:
        score += 1
    if one['year'] == two['year']:
        score += 1
    return score

def make_dict(track):
    '''
    Converts a track tuple to a dictionary which is more convenient to handle.
    The indices should match the select statement in `read_amarok_lib()`.
    '''
    dict_track = {
            'name': track[0],
            'track': track[1],
            'album': track[2],
            'artist': track[3],
            'year': track[4],
            'rating': track[5]/2 # amarok ratings are 1-10
            }
    return dict_track

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

def read_gmusic_lib():
    if not api.is_authenticated():
        print("Authentication failed!", file=sys.stderr)
        sys.exit()
    gm_lib = api.get_all_songs()
    return gm_lib

def read_local_lib(music_root, extension_list):
    for dirpath, dirnames, filenames in os.walk(music_root):
        for fname in filenames:
            _, fext = os.path.splitext(fname)
            fext = fext[1:]
            if fext not in extension_list:
                continue
            

def update_remote_track(remote_lib, track):
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
        - album artist
    '''
    remote_tracks = [rtrack for rtrack in remote_lib\
            if rtrack['name'] == track['name']]

    matches = []
    for rt in remote_tracks:
        score = match(track, rt)
        if score >= 2:
            'Just look for a match rating of 2+ for now.'
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
        sys.stdout.write('---\n\n')
        sys.stdout.write("Multiple matching songs found in remote library.\n")
        sys.stdout.write("Local song info: %s\n" % (
            song_info_to_string(track)))
        sys.stdout.write("Matching songs:\n")
        for m in matches:
            sys.stdout.write("%s - match score: %i\n" % (
                song_info_to_string(m[1]), m[0]))
        best_match = max(matches, key=lambda m: m[0])
        sys.stdout.write("Best match is %s\n" % (
                                        song_info_to_string(best_match[1])))
        ask = True
        while ask:
            yesno = raw_input("Accept best match? [Y/n] ")
            if yesno.lower() == 'y' or yesno == '':
                remote_track = best_match[1]
                if remote_track['rating'] == track['rating']:
                    remote_track = None
                ask = False
            elif yesno.lower() == 'n':
                remote_track = None
                ask = False
    return remote_track

def get_new_ratings(local_lib, remote_lib):
    new_remotes = []
    for lt in local_lib:
        local_track = make_dict(lt)
        if local_track['rating'] == 0:
            'Nothing to do here'
            continue
        remote_track = update_remote_track(remote_lib, local_track)
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
    music_dir = args.musicdir
    api = google_music_login()
    if api is None:
        sys.exit()
    try:
        print("Loading extension list ...", end="")
        sys.stdout.flush()
        extension_list = read_extensions(_EXTENSION_LIST_FILE)
        print("done!")
        print("Reading Google music library ...", end="")
        sys.stdout.flush()
        gmusic_lib = read_gmusic_lib()
        print("done!")
        print("Reading tags from local library [%s] ..." % music_dir, end="")
        sys.stdout.flush()
        local_lib = read_local_lib()
        print("done!")
        #gmusic_updated_lib = get_new_ratings(local_lib, gmusic_lib)
        #update_metadata(api, gmusic_updated_lib)
    except Exception:
        api.logout()
        raise
    api.logout()

