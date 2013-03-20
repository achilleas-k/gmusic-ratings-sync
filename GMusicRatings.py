#!/usr/bin/env python

from getpass import getpass
from gmusicapi import Api
import MySQLdb as sql
import sys, os
import argparse

VERSION  = "0.0.1"
DEBUG_FLAG = "false"
PRETEND_FLAG = "false"

def song_info_to_string(song):
    return "%s - %i - %s on %s (%s)" % (
            song['artist'],
            song['track'] if song['track'] else 0,
            song['name'],
            song['album'],
            '*'*song['rating'])

def match(one, two):
    '''
    Returns a score which shows the number of fields that are equal.
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
    #print("%s \n %s \n score %i" % (
    #    song_info_to_string(one),
    #    song_info_to_string(two),
    #    score))
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

def read_amarok_lib(socket):
    '''
    Loads the relevant Amarok tables and makes dictionary lists with all the
    relevant data.
    '''
    sys.stdout.write("Connecting to local database using %s ..." % (socket))
    sys.stdout.flush()
    dbconn = sql.connect(
            unix_socket=socket)
    sys.stdout.write("OK\n")
    sys.stdout.write("Reading local database ... ")
    sys.stdout.flush()
    dbconn.select_db('amarok')
    cursor = dbconn.cursor()
    select_statement = '''
            SELECT tracks.title,
                    tracks.tracknumber,
                    albums.name,
                    artists.name,
                    tracks.year,
                    statistics.rating
            FROM tracks, albums, artists, statistics
            WHERE tracks.url = statistics.url and tracks.artist = artists.id
                    and tracks.album = albums.id;
            '''
    cursor.execute(select_statement)
    local_lib = cursor.fetchall()
    sys.stdout.write("done.\n")
    return local_lib

def google_music_login():
    '''
    Ask for credentials and log into Google music.
    '''
    sys.stdout.write("Connecting to Google Music ...\n")
    api = Api()
    logged_in = False
    attempts = 0
    while not logged_in and attempts < 3:
        email = raw_input("Email: ")
        password = getpass()
        logged_in = api.login(email, password, perform_upload_auth=False)
        attempts += 1
    if not api.is_authenticated():
        sys.stderr("Login failed.\n")
        return None
    sys.stdout.write("Successfully logged in.\n")
    return api

def read_gmusic_lib():
    if not api.is_authenticated():
        sys.stderr.write('Something went wrong. No auth.\n')
        sys.exit(3)
    gm_lib = api.get_all_songs()
    return gm_lib

def read_local_gmusic_lib(filename):
    libfile = open(filename, 'r')
    import pickle
    locallib = pickle.load(libfile)
    return locallib

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Copy Amarok library ratings to Google Music.')
    parser.add_argument('--socket', '-s', metavar='socket', type=str,
        default=os.path.join(os.environ['HOME'], '.kde4/share/apps/amarok/sock'),
        help='socket which will be used to connect to the database with'
        ' (default: %(default)s)')
    args = parser.parse_args()

    # add check if file exists
    local_lib = read_amarok_lib(args.socket)
    api = google_music_login()
    if api is None:
        sys.exit(3)
    try:
        gmusic_lib = read_gmusic_lib()
        gmusic_updated_lib = get_new_ratings(local_lib, gmusic_lib)
        update_metadata(api, gmusic_updated_lib)
    except Exception:
        api.logout()
        raise

    api.logout()

