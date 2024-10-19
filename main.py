# imports
from flask import Flask, session, redirect, url_for, request, render_template, g
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler
import os
import json
from dotenv import load_dotenv, dotenv_values
from collections import Counter
import numpy as np
from flask_wtf.csrf import CSRFProtect
from datetime import timedelta
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
import textwrap
import uuid

global_nonce = None

# load env variables
load_dotenv()

# Create playlist Cover Image Function
def create_playlist_cover(playlist_name):
    # Create a new blank image with RGB mode
    img = Image.new('RGB', (800, 800), color='#171717')

    # Initialize ImageDraw
    d = ImageDraw.Draw(img)

    # Define fonts
    try:
        font = ImageFont.truetype(font="fonts/PalanquinDark-Bold.ttf", size=150)
        font2 = ImageFont.truetype(font="fonts/PalanquinDark-Medium.ttf", size=73)
    except IOError:
        font = ImageFont.load_default()
        font2 = ImageFont.load_default()

    # Wrap text to fit the image
    wrapped_text = textwrap.fill(playlist_name, width=10)

    # Split the wrapped text into multiple lines
    lines = wrapped_text.split('\n')

    # Get text bounding box for a tall character to establish line height
    _, _, text_width, text_height = d.textbbox((0, 0), "A", font=font)

    # Set a fixed line height and line spacing
    fixed_line_height = text_height - 65  # You can adjust the spacing as needed

    # Calculate the total height of the text block to center it vertically
    total_text_height = len(lines) * fixed_line_height

    # Starting Y position (for vertical centering)
    y = -50

    # Draw each line of text aligned to the right
    for line in lines:
        # Get text bounding box (to calculate width)
        bbox = d.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]

        # Align the text to the right
        x = 800 - text_width - 20  # 10 pixels padding from the right edge

        # Draw the text on the image
        d.text((x, y), line, fill=(236, 160, 40), font=font)

        # Move to the next line using the fixed line height
        y += fixed_line_height

    # Draw the artist names
    y_offset = 675
    d.text((10, y_offset), 'made by Discovery Jam', fill=(247, 230, 210), font=font2)

    # Create a BytesIO object to hold the image
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)  # Seek to the beginning so it can be read

    # Convert the image to base64
    img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')

    return img_base64

def ensure_token_is_valid():
    token_info = sp_oauth.validate_token(cache_handler.get_cached_token())
    
    if not token_info:
        # Refresh the token if it has expired
        token_info = sp_oauth.refresh_access_token(cache_handler.get_cached_token()['refresh_token'])
        cache_handler.save_token_to_cache(token_info)

# Spotify Web API constants
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
SECRET_KEY = os.getenv('SECRET_KEY')
REDIRECT_URI = 'https://discovery-jam-b001a7c3c17b.herokuapp.com/callback'
SCOPE = 'playlist-read-private,user-top-read,playlist-modify-public,ugc-image-upload'

# create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
app.config['SESSION_PERMANENT'] = False

# Configuration based on environment
app.config['ENV'] = os.getenv('ENV', 'development')  # Default to 'development' if not set
# Use secure cookies
app.config['SESSION_COOKIE_SECURE'] = True  # Ensures cookies are only sent over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevents JavaScript from accessing cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Prevent CSRF attacks
csrf = CSRFProtect(app)

# spotipy cache handler setup
cache_handler = FlaskSessionCacheHandler(session)

# spotipi OAuth setup
sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
    cache_handler=cache_handler,
    show_dialog=True
)

# setup Spotify
sp = Spotify(auth_manager=sp_oauth)

# Force HTTPS in production
@app.before_request
def before_request():
    if not request.is_secure and app.config['ENV'] == 'production':
        return redirect(request.url.replace("http://", "https://"))
    
    # Generate a nonce for the current request and store it in g (Flask's context)
    g.nonce = str(uuid.uuid4())

@app.after_request
def add_csp_header(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "style-src-elem 'self' https://fonts.googleapis.com; "  # Ensure both style-src and style-src-elem include Google Fonts
        "font-src 'self' https://fonts.gstatic.com; "  # Google Fonts require this domain to load the fonts
        f"script-src 'self' 'nonce-{g.nonce}';"  # Allow inline scripts with nonce
    )
    response.set_cookie('csp_nonce', g.nonce)
    return response

# home route
@app.route('/')
def home():
    return render_template('index.html', nonce=g.nonce)

# home route
@app.route('/login')
def login():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return redirect(url_for('get_top_artists'))

# redirect uri route
@app.route('/callback')
def callback():
    # This retrieves the cached token instead of getting a new one
    token_info = sp_oauth.get_cached_token()

    # If no token exists, fetch a new one
    if not token_info:
        token_info = sp_oauth.get_access_token(request.args['code'], as_dict=False)
    return redirect(url_for('get_top_artists'))

# get_top_artists route
@app.route('/get_top_artists', methods=['GET', 'POST'])
def get_top_artists():
    # Route Functions
    def create_artists_genres_arrays(top_artists):
        """input spotify's current user top artists object and
            return 2 arrays, genre names and artist ids"""
        genres_array = []
        artist_array = []
        for artist in top_artists:
            for genre in artist['genres']:
                genres_array.append(genre)
            artist_array.append(artist['id'])
        return (genres_array, artist_array)

    def clean_arrays(array):
        """Input: array of strings
            Output: array of ordered, top 5 without duplicates"""
        # orders array by most common
        ordered_array = [item for items, c in 
                       Counter(array).most_common() for item in [items] * c] 
        no_dupes = []
        for x in ordered_array: # remove duplicates
            if x not in no_dupes:
                no_dupes.append(x)  
        return no_dupes[:5]

    def get_audio_features_stats(audio_features):
        """Input: Spotify audio features object. 
        Return: Danceability Stats, Energy Stats, and Valence Stats as dictionaries"""
        # extract features from the spotify features object
        danceability_array, energy_array, valence_array = [], [], []
        for track in audio_features:
            danceability_array.append(track['danceability'])
            energy_array.append(track['energy'])
            valence_array.append(track['valence'])
        
        danceability = {
        'min': min(danceability_array),
        'mean': float(np.mean(danceability_array)),
        'max': max(danceability_array)
        }

        energy = {
            'min': min(energy_array),
            'mean': float(np.mean(energy_array)),
            'max': max(energy_array)
        }

        valence = {
            'min': min(valence_array),
            'mean': float(np.mean(valence_array)),
            'max': max(valence_array)
        }

        return (danceability, energy, valence)
    
    def get_spotify_recommendations(genres, artists, danceability, energy, valence):
        """INPUT: genres array, artists array, daceability dictionary, 
            energy dictionary, valence dictionary
            OUTPUT: artist seeds, genre seeds, and track recommendations"""
        recs = sp.recommendations(    #5 total seeds
                                seed_genres=genres[:2]
                            #    ,seed_tracks=track_ids[:2]
                               ,seed_artists=artists[:3]
                               ,min_danceability=danceability['min']
                               ,max_danceability=danceability['max']
                               ,target_danceability=danceability['mean']
                               ,min_energy=energy['min']
                               ,max_energy=energy['max']
                               ,target_energy=energy['mean']
                               ,min_valence=valence['min']
                               ,max_valence=valence['max']
                               ,target_valence=valence['mean']
                               ,min_popularity=0
                               ,max_popularity=8
                               ,target_popularity=4           #popularity setting
                               )
        
        top_artist_ids = [artist for artist in artists]  # List of artist IDs
        cleaned_tracks = []
        for track in recs['tracks']:
            artist_id = track['artists'][0]['id']
            if artist_id not in top_artist_ids:
                cleaned_tracks.append({
                    'track_id': track['id'],
                    'track_name': track['name'],
                    'track_image': track['album']['images'][0]['url'],
                    'preview': track['preview_url'],
                    'artist_id': track['artists'][0]['id'],
                    'artist_name': track['artists'][0]['name']
                })
        artist_seeds = []
        genre_seeds = []
        for seed in recs['seeds']:
            if seed['type'] == 'ARTIST':
                artist = sp.artist(seed['id'])
                artist_seeds.append({
                    'name': artist['name'],
                    'id': artist['id'],
                    'image_url': artist['images'][0]['url']
                })
            else:
                genre_seeds.append(seed['id'])
        return (artist_seeds, genre_seeds, cleaned_tracks)

    def get_user_info():
        """no inputs, returns a dictionaty of current loggedin users name and ID"""
        user = sp.current_user()
        user_info = {
            'name': user['display_name'],
            'id': user['id']
        }
        return user_info
    
    def create_user_playlist():
        """checks if playlist already exists and then creates a 
        playlist with the recommended tracks for the user.
        If a playlist was already created, it will create a new
        playlist wiht a unique name."""

        # Ensure that the token is valid before making any API requests
        ensure_token_is_valid()
        
        base_name = f"{user['name'].title()}'s Discovery Jam Vol:"
        check = sp.user_playlists(user=user['id'], limit=1)['items']
        if base_name in check[0]['name']:
            idx = check[0]['name'].find(base_name) + len(base_name) + 1
            vol_num = int(check[0]['name'][idx:]) + 1
        else:
            vol_num = 1

        playlist_name = base_name + '0' + str(vol_num)
        
        sp.user_playlist_create(user=user['id'],
                                name=playlist_name,
                                description="Discovery playlist created using your top genres and artists over the past year with the goal of helping you find new artists with smaller followings. Learn more at **webaddress**")
        playlist = sp.user_playlists(user=user['id'], limit=1)['items']
        sp.user_playlist_add_tracks(user=user['id'],
                                    playlist_id=playlist[0]['id'],
                                    tracks=[track['track_id'] for track in track_recs])
        # Generate the cover image
        img = create_playlist_cover(playlist_name)

        # Upload the custom cover image
        try:
            sp.playlist_upload_cover_image(playlist_id=playlist[0]['id'], image_b64=img)
        except Exception as e:
            print(f"Error uploading cover image: {e}")

        
        if playlist:
            return (playlist[0]['external_urls']['spotify'], playlist_name)
        else:
            return False

    # check validation
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    
    # get current user info
    user = get_user_info()
    top_artists = sp.current_user_top_artists(time_range='long_term')['items']
    top_tracks = sp.current_user_top_tracks(limit=40, time_range='long_term')['items']

    # get array of genres and artists from  spotify objects
    genres_array, artists_array = create_artists_genres_arrays(top_artists=top_artists)

    # order by most common and limit to 5
    genres = clean_arrays(genres_array)
    artists = clean_arrays(artists_array)
    
    # create list of dictionaries for top tracks
    tracks = []
    for track in top_tracks:
        tracks.append(
            {
                'id': track['id'],
                'title': track['name'],
                'artist': track['artists'][0]['name']
            }
        )

    track_ids = [track['id'] for track in tracks] # make list of track ids
    audio_features = sp.audio_features(tracks=track_ids) # get spotify audio features

    # extract features from the spotify features object
    danceability, energy, valence = get_audio_features_stats(audio_features=audio_features)

    # genre_options = sp.recommendation_genre_seeds()
    artist_seeds, genre_seeds, track_recs = get_spotify_recommendations(genres=genres, 
                                                    artists=artists, 
                                                    danceability=danceability, 
                                                    energy=energy, 
                                                    valence=valence)

    if request.method == 'POST':  # When the form is submitted
        playlist_url, playlist_name = create_user_playlist()
        if playlist_url:
            session.clear()
            message = 'Playlist Created! View ↓'
            return redirect(url_for('success', playlist_url=playlist_url, playlist_name=playlist_name))  # Pass the URL as a query parameter
        elif not playlist_url:
            message = 'Playlist not created, try again'
        return redirect(url_for('get_top_artists', message=message))  # Redirect to avoid form resubmission

    # Handle GET request
    playlist_url = request.args.get('playlist_url')  # Retrieve the playlist URL from the query parameters
    playlist_created = request.args.get('playlist_created')  # Check if the playlist was created
    message = request.args.get('message')

    return render_template('recs.html', user=user, artist_seeds=artist_seeds, genre_seeds=genre_seeds, track_recs=track_recs, playlist_url=playlist_url, playlist_created=playlist_created, message=message, nonce=g.nonce)

# Playlist created Successfully
@app.route('/success')
def success():
    playlist_url = request.args.get('playlist_url')  # Retrieve the playlist URL from the query parameters
    playlist_name = request.args.get('playlist_name')
    img = create_playlist_cover(playlist_name)
    return render_template('playlist_created.html', playlist_url=playlist_url, img=img, nonce=g.nonce)

# logout route
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Handle errors
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run()