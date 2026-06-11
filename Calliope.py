#!/usr/bin/env python3
import argparse
import asyncio
import os
import random
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import yt_dlp

# Load environment variables from the local .env file
load_dotenv()

def get_spotify_tracks(playlist_url: str) -> tuple[str, list[str]]:
    """
    Authenticates with Spotify using full user OAuth context
    """
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print(" Error: Spotify credentials missing from .env file.", file=sys.stderr)
        sys.exit(1)
        
    scope = "playlist-read-private playlist-read-collaborative"
    
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope=scope,
            cache_path=".spotify_caches",
            open_browser=False
        ))
        
        playlist_id = playlist_url.split("playlist/")[1].split("?")[0]
        results = sp.playlist(playlist_id)
        
    except IndexError:
        print(" Error: Invalid Spotify playlist URL layout.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f" Error connecting to Spotify API infrastructure: {e}", file=sys.stderr)
        sys.exit(1)
        
    playlist_name = results.get('name', 'Unknown Archive')
    
    
    tracks_container = {}
    if isinstance(results, dict):
        if 'tracks' in results:
            tracks_container = results['tracks']
        elif 'items' in results:
            tracks_container = results['items']
            
    # Pull raw items array safely
    items = []
    if isinstance(tracks_container, dict):
        items = tracks_container.get('items', [])
    elif isinstance(tracks_container, list):
        items = tracks_container
        
    # Process pagination loops for large playlists using the active structural container
    tracks_payload = tracks_container
    while isinstance(tracks_payload, dict) and tracks_payload.get('next'):
        try:
            tracks_payload = sp.next(tracks_payload)
            if tracks_payload:
                next_items = tracks_payload.get('items', [])
                items.extend(next_items)
        except Exception as e:
            print(f" Warning: Truncated fetch at pagination page break: {e}")
            break
            
    queries = []
    for item in items:
        if not item or not isinstance(item, dict):
            continue
            
        
        track_data = None
        if 'item' in item and isinstance(item['item'], dict):
            track_data = item['item']
        elif 'track' in item and isinstance(item['track'], dict):
            track_data = item['track']
        else:
            track_data = item # Fallback if flat
            
        if track_data and isinstance(track_data, dict):
            # Skip local system music files
            if track_data.get('is_local') is True:
                continue
                
            track_name = track_data.get('name', 'Unknown Track')
            
            # Extract nested artists name
            artists = track_data.get('artists', [])
            if artists and isinstance(artists, list):
                artist_name = artists[0].get('name', 'Unknown Artist')
            else:
                artist_name = 'Unknown Artist'
                
            queries.append(f"{track_name} - {artist_name} official audio")
            
    return playlist_name, queries

def sync_download(query: str, target_dir: str):
    """Executes the synchronous search extraction via yt-dlp."""
    opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{target_dir}/%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }
    
    search_str = f"ytsearch1:{query}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([search_str])

# Change the amount of concurrent downloads
MAX_CONCURRENT_DOWNLOADS = 3

async def download_worker(worker_id: int, queue: asyncio.Queue, target_dir: str, total_tracks: int):
    """
    A persistent worker that pulls download tasks out of the queue
    and processes them concurrently in its own thread executor.
    """
    loop = asyncio.get_running_loop()
    
    while True:
        # Grab a task from the queue
        task_data = await queue.get()
        if task_data is None:
            # Sentinel value received, shutting down worker safely
            queue.task_done()
            break
            
        index, query = task_data
        clean_name = query.replace(" official audio", "")
        print(f" [Worker {worker_id}] Processing [{index}/{total_tracks}]: {clean_name}")
        
        try:
            # Fire off the heavy I/O download block to a background thread
            await loop.run_in_executor(None, lambda: sync_download(query, target_dir))
        except Exception as e:
            print(f" [Worker {worker_id}] Error syncing '{clean_name}': {e}", file=sys.stderr)
            
        # Introduce a soft pacing variable PER WORKER so Youtube doesn't think we are bots!
        await asyncio.sleep(random.uniform(1.5, 3.0))
        
        # Tell the queue the task is complete
        queue.task_done()

async def main():
    parser = argparse.ArgumentParser(
        description="CLI tool to archive a Spotify playlist locally via verified user context authentication."
    )
    parser.add_argument("path", type=str, help="The target download destination path.")
    parser.add_argument("url", type=str, help="The link to the target Spotify playlist.")
    
    args = parser.parse_args()
    base_path = os.path.abspath(os.path.expanduser(args.path))
    
    
    print("Connecting to Spotify architecture...")
    loop = asyncio.get_running_loop()
    
    # Run the blocking synchronous network lookup inside a separate worker thread executor context
    playlist_name, queries = await loop.run_in_executor(
        None, lambda: get_spotify_tracks(args.url)
    )
    # ------------------------
    
    total_tracks = len(queries)
    safe_folder_name = "".join([c for c in playlist_name if c.isalnum() or c in " -_"]).strip()
    final_output_path = os.path.join(base_path, safe_folder_name)
    
    print(f"\n Destination: {final_output_path}")
    print(f" Archive Target: '{playlist_name}' ({total_tracks} tracks loaded)")
    print("=" * 65)
    print(f" Spinning up {MAX_CONCURRENT_DOWNLOADS} concurrent worker nodes...")
    print("=" * 65)
    
    if total_tracks == 0:
        print(" Error: No track items detected. Ensure authorization is fully bound.")
        sys.exit(1)
        
    # Initialize the Async Queue and seed it with tasks
    queue = asyncio.Queue()
    for i, query in enumerate(queries, start=1):
        await queue.put((i, query))
        
    # Spawn the persistent worker tasks
    workers = []
    for worker_id in range(1, MAX_CONCURRENT_DOWNLOADS + 1):
        task = asyncio.create_task(
            download_worker(worker_id, queue, final_output_path, total_tracks)
        )
        workers.append(task)
        
    # Wait until all items in the queue have been fully processed
    await queue.join()
    
    # Tell the workers to gracefully exit
    for _ in range(MAX_CONCURRENT_DOWNLOADS):
        await queue.put(None)
        
    # Wait for all worker tasks to fully spin down
    await asyncio.gather(*workers)
            
    print("\n Download complete! Playlist successfully archived.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Execution canceled by user. Safe-exiting pipeline.")
        sys.exit(0)
