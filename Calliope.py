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
import urllib.request
import syncedlyrics
from mutagen.id3 import SYLT, USLT
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error

# Load environment variables from the local .env file
load_dotenv()

def get_track_basename(title: str, artist: str) -> str:
    """Helper utility to generate standard, predictable filename basenames consistently."""
    safe_title = "".join([c for c in title if c.isalnum() or c in " -_()"]).strip()
    safe_artist = "".join([c for c in artist if c.isalnum() or c in " -_()"]).strip()
    return f"{safe_artist} - {safe_title}"

def get_spotify_tracks(playlist_url: str) -> tuple[str, list[dict]]:
    """
    Authenticates with Spotify using full user OAuth context
    and targets the exact structural layouts leaked by the raw JSON dump.
    """
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print(" Error: Spotify credentials missing from .env file!", file=sys.stderr)
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
            
    items = []
    if isinstance(tracks_container, dict):
        items = tracks_container.get('items', [])
    elif isinstance(tracks_container, list):
        items = tracks_container
        
    while isinstance(tracks_payload := tracks_container, dict) and tracks_payload.get('next'):
        try:
            tracks_container = sp.next(tracks_container)
            if tracks_container:
                next_items = tracks_container.get('items', [])
                items.extend(next_items)
        except Exception as e:
            print(f" Warning: Truncated fetch at pagination page break: {e}")
            break
            
    track_meta_list = []
    for item in items:
        if not item or not isinstance(item, dict):
            continue
            
        track_data = None
        if 'item' in item and isinstance(item['item'], dict):
            track_data = item['item']
        elif 'track' in item and isinstance(item['track'], dict):
            track_data = item['track']
        else:
            track_data = item
            
        if track_data and isinstance(track_data, dict):
            if track_data.get('is_local') is True:
                continue
                
            track_name = track_data.get('name', 'Unknown Track')
            artists = track_data.get('artists', [])
            artist_name = artists[0].get('name', 'Unknown Artist') if artists else 'Unknown Artist'
            
            album_data = track_data.get('album', {})
            album_name = album_data.get('name', 'Unknown Album')
            
            images = album_data.get('images', [])
            cover_url = images[0].get('url') if images else None
            
            track_meta_list.append({
                "title": track_name,
                "artist": artist_name,
                "album": album_name,
                "cover_url": cover_url,
                "query": f"{track_name} - {artist_name} official audio"
            })
            
    return playlist_name, track_meta_list

def sync_download_and_tag(track: dict, target_dir: str):
    """Downloads the audio stream and injects Spotify metadata/cover art, USLT tags, and SYLT tags."""
    file_basename = get_track_basename(track['title'], track['artist'])
    final_file_path = os.path.join(target_dir, f"{file_basename}.mp3")

    if os.path.exists(final_file_path):
        print(f" Skipping (Already Archived): {file_basename}")
        return

    opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{target_dir}/{file_basename}.%(ext)s",
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
    
    search_str = f"ytsearch1:{track['query']}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([search_str])
        
    if os.path.exists(final_file_path):
        try:
            # Force initialize the ID3 tag structure layout
            try:
                tags = ID3(final_file_path)
            except error:
                tags = ID3()
                
            tags.add(TIT2(encoding=3, text=track['title']))
            tags.add(TPE1(encoding=3, text=track['artist']))
            tags.add(TALB(encoding=3, text=track['album']))
            
            if track['cover_url']:
                try:
                    with urllib.request.urlopen(track['cover_url'], timeout=10) as response:
                        cover_data = response.read()
                    tags.add(APIC(
                        encoding=3, mime='image/jpeg', type=3, desc=u'Cover', data=cover_data
                    ))
                except Exception as img_err:
                    print(f" Warning: Could not fetch cover art for '{file_basename}': {img_err}")
            
            # --- EMBEDDED-ONLY LYRICS ENGINE ---
            try:
                print(f" Fetching synced lyrics for: {track['title']}")
                
                enc_title = urllib.parse.quote(track['title'])
                enc_artist = urllib.parse.quote(track['artist'])
                lrclib_url = f"https://lrclib.net/api/get?track_name={enc_title}&artist_name={enc_artist}"
                
                req = urllib.request.Request(
                    lrclib_url, 
                    headers={'User-Agent': 'CalliopeMusicArchiver/1.0 (Local Sync Utility)'}
                )
                
                api_data = None
                max_retries = 2
                for attempt in range(max_retries + 1):
                    try:
                        with urllib.request.urlopen(req, timeout=15) as response:
                            import json
                            api_data = json.loads(response.read().decode('utf-8'))
                        break
                    except (urllib.error.URLError, TimeoutError) as net_err:
                        if attempt < max_retries:
                            import time
                            time.sleep(2)
                        else:
                            raise net_err
                
                if api_data:
                    lrc_text = api_data.get('syncedLyrics')
                    
                    if lrc_text:
                        sylt_data = []
                        for line in lrc_text.splitlines():
                            line = line.strip()
                            if line.startswith('[') and ']' in line:
                                try:
                                    time_part, text_part = line.split(']', 1)
                                    time_str = time_part.strip('[] ')
                                    
                                    parts = time_str.split(':')
                                    if len(parts) != 2:
                                        continue
                                        
                                    minutes = int(parts[0])
                                    seconds_seconds = float(parts[1])
                                    
                                    total_ms = int((minutes * 60 + seconds_seconds) * 1000)
                                    text_content = text_part.strip()
                                    
                                    sylt_data.append((text_content, total_ms))
                                except (ValueError, IndexError):
                                    continue
                        
                        if sylt_data:
                            sylt_data.sort(key=lambda x: x[1])  # Chronological timeline alignment
                            
                            # 1. Embed Synchronized binary timeline matrix
                            tags.add(SYLT(
                                encoding=3,
                                lang='eng',    
                                format=1,      
                                type=1,        
                                desc=u'Lyrics',
                                text=sylt_data
                            ))
                            
                            # 2. Embed Unsynchronized text block layout
                            tags.add(USLT(
                                encoding=3,
                                lang='eng',
                                desc=u'Lyrics',
                                text=lrc_text
                            ))
                            
                            print(f" Successfully embedded SYLT and USLT frames into ID3 container.")
                        else:
                            print(f"  No parseable timestamp layout within Lrclib response data.")
                    else:
                        print(f"  No synced lyrics available on Lrclib for this track.")
                        
            except Exception as e:
                print(f"  Lyrics engine error for '{track['title']}': {e}")

            # Commit metadata using strict ID3v2.4 specification constraints
            tags.save(final_file_path, v2_version=4)
            
        except Exception as tag_err:
            print(f" Metadata Frame Error on '{file_basename}': {tag_err}")

MAX_CONCURRENT_DOWNLOADS = 3

async def download_worker(worker_id: int, queue: asyncio.Queue, target_dir: str, total_tracks: int):
    """Persistent worker driving metadata validation and extraction."""
    loop = asyncio.get_running_loop()
    
    while True:
        task_data = await queue.get()
        if task_data is None:
            queue.task_done()
            break
            
        index, track = task_data
        await loop.run_in_executor(None, lambda: sync_download_and_tag(track, target_dir))
        await asyncio.sleep(random.uniform(1.5, 3.0))
        queue.task_done()

async def main():
    parser = argparse.ArgumentParser(
        description="CLI tool to archive a Spotify playlist locally with a bi-directional sync purge."
    )
    parser.add_argument("path", type=str, help="The target download destination path.")
    parser.add_argument("url", type=str, help="The link to the target Spotify playlist.")
    
    args = parser.parse_args()
    base_path = os.path.abspath(os.path.expanduser(args.path))
    
    print("Connecting to Spotify architecture...")
    loop = asyncio.get_running_loop()
    
    playlist_name, tracks = await loop.run_in_executor(
        None, lambda: get_spotify_tracks(args.url)
    )
    
    total_tracks = len(tracks)
    safe_folder_name = "".join([c for c in playlist_name if c.isalnum() or c in " -_"]).strip()
    final_output_path = os.path.join(base_path, safe_folder_name)
    
    os.makedirs(final_output_path, exist_ok=True)
    
    print(f"\n Destination: {final_output_path}")
    print(f" Archive Target: '{playlist_name}' ({total_tracks} tracks loaded)")
    print("=" * 65)
    print(f"  Spinning up {MAX_CONCURRENT_DOWNLOADS} concurrent worker nodes...")
    print("=" * 65)
    
    if total_tracks == 0:
        print(" Error: No track items detected. Ensure authorization is fully bound.")
        sys.exit(1)
        
    # --- SYNCHRONIZATION DATA SHOT ---
    # Create a quick-lookup hash set of file basenames that SHOULD exist
    expected_filenames = {f"{get_track_basename(t['title'], t['artist'])}.mp3" for t in tracks}
        
    queue = asyncio.Queue()
    for i, track in enumerate(tracks, start=1):
        await queue.put((i, track))
        
    workers = []
    for worker_id in range(1, MAX_CONCURRENT_DOWNLOADS + 1):
        task = asyncio.create_task(
            download_worker(worker_id, queue, final_output_path, total_tracks)
        )
        workers.append(task)
        
    await queue.join()
    
    for _ in range(MAX_CONCURRENT_DOWNLOADS):
        await queue.put(None)
        
    await asyncio.gather(*workers)
    
    # --- PHASE 2: THE BI-DIRECTIONAL PURGE SYNC ENGINE ---
    print("\n" + "=" * 65)
    print(" Synchronizing local files with Spotify playlist updates...")
    print("=" * 65)
    
    # Read what files are actually physically present on the hard drive
    local_files = os.listdir(final_output_path)
    local_mp3s = [f for f in local_files if f.lower().endswith('.mp3')]
    
    # Isolate orphaned files using set differences
    orphaned_files = [f for f in local_mp3s if f not in expected_filenames]
    
    if orphaned_files:
        print(f"  Found {len(orphaned_files)} tracks locally that were removed from your Spotify playlist:\n")
        for orphan in orphaned_files:
            print(f"    {orphan}")
            
        # Prompt the user securely via stdin inside the Fish loop
        print("\n" + "-" * 40)
        try:
            # We run the input choice inside an executor context to prevent locking up async threads
            choice = await loop.run_in_executor(
                None, lambda: input("Do you want to permanently delete these tracks from your drive? (y/N): ").strip().lower()
            )
            
            if choice in ['y', 'yes']:
                for orphan in orphaned_files:
                    orphan_path = os.path.join(final_output_path, orphan)
                    try:
                        os.remove(orphan_path)
                        print(f" Deleted: {orphan}")
                    except Exception as ex:
                        print(f" Failed to delete {orphan}: {ex}")
                print("\n Local directory successfully pruned and updated.")
            else:
                print("\n Purge cancelled. Local orphaned files left intact.")
        except KeyboardInterrupt:
            print("\n Purge prompt bypassed via execution interruption.")
    else:
        print(" Directory sync verified! No orphaned tracks discovered.")
            
    print("\n Download complete! Your local library archive is up to date.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Execution canceled by user. Safe-exiting pipeline.")
        sys.exit(0)
