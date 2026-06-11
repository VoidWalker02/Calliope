# Calliope 

Calliope is a simple command-line tool that lets you download your Spotify playlists directly to your computer as `.mp3` files.

It works by looking at the songs in your Spotify playlist, finding the matching audio on YouTube, and safely saving it to your hard drive.

##  Current Status: Very Early

Calliope is fully working but is still in its early stages, I intend to add a few extra features in the future. Currently, you can download the full playlist and, when digging around the file, you can change the number of maximum concurrent downloads. 

##  How It Works

Calliope connects three different pieces behind the scenes:

1. **The Spotify Connection**: It securely logs into Spotify to read the names of the songs in your playlist.
    
2. **The Search Engine**: It takes the song metadata and grabs the closest match off Youtube. 
    
3. **The Downloader**: It grabs the audio from YouTube, converts it into the highest quality `.mp3` file it can, and saves it in a folder named after your playlist.
    

##  Getting Started

### 1. What You Need

Before running the tool, make sure you have `ffmpeg` installed on your system (the tool that handles converting the audio into `.mp3` format).

Next, open your terminal and install these three required Python packages:


```
pip install spotipy python-dotenv yt-dlp
```

### 2. Setting Up Your Spotify Access

To use the tool, (unfortunately) you need to tell Spotify it's allowed to talk to your computer.

1. Go to the **Spotify Developer Dashboard** and create an app layout.
    
2. In the app settings, set the **Redirect URI** to exactly: `http://127.0.0.1:8888/callback`
    
3. Create a text file named exactly `.env` in your project folder and paste your app's secret keys like this:
    

```
SPOTIPY_CLIENT_ID="your_spotify_client_id_here"
SPOTIPY_CLIENT_SECRET="your_spotify_client_secret_here"
```

##  How to Use It

Open your terminal and run the script by typing `python Calliope.py`, followed by **where you want to save the music**, and then the **Spotify playlist link**:



```
python Calliope.py <where_to_save> <spotify_playlist_link>
```

### Example:


```
python Calliope.py ~/Music/MyPlaylists https://open.spotify.com/playlist/...
```

### First-Time Use Only 

The very first time you run the tool, it will ask for your permission to access your playlist:

1. It will print a long web link in your terminal. Copy that link and open it in your web browser of choice.
    
2. Click **Authorize** on the Spotify page.
    
3. Your browser will send you to a blank/broken page. **Copy the entire web address of that broken page** from your browser's address bar.
    
4. Paste that link right back into your terminal prompt and hit `Enter`.
    

_And done! Calliope saves a secret file so it remembers you. Every time you run it after this, it will download your music completely automatically without asking you to log in._

##  Built-In Safety Features

Downloading too fast can make YouTube think you are a malicious robot and temp-ban your home internet. Calliope has built-in safety controls to prevent this:

- **The n-Song Limit**: By changing the MAX_CONCURRENT_DOWNLOADS variable you can change how many downloads are done simultaneously. It is currently set at 3, a good balance of speed vs getting nuked by Youtube. Increase at your own risk.
    
- **Human Jitter**: It waits a random amount of seconds ($1.5$ to $3.0$ seconds) between song downloads to look like a human clicking through a playlist rather than a fast machine.
    

##  Future Updates 

- [ ] Make Calliope embed the proper Album Artwork automatically.
    
- [ ] Add a feature that double-checks the video length to make sure it doesn't accidentally download a 10-hour loop instead of a 3-minute song (something we're entirely relying on yt-dlp to do for us).
    
- [ ] Turn it into a native system command so you can just type `calliope` from anywhere.
