#!/usr/bin/env python3
"""
DJ Set Track Recognizer - SAMPLING VERSION
Takes 10-second samples every 60 seconds - works with free API limits
"""

import requests
import yt_dlp
from datetime import timedelta
import json
import sys
import os
from pydub import AudioSegment
import time

# Windows consoles/pipes may default to a legacy codepage (e.g. cp1252)
# that can't encode the emoji used in output.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

class SamplingDJSetAnalyzer:
    def __init__(self, api_key):
        self.api_key = api_key
        
    def download_soundcloud(self, url):
        """Download audio from SoundCloud"""
        print("\n📥 Downloading DJ set from SoundCloud...")
        print("=" * 60)
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': 'djset',
            'quiet': False,
            'no_warnings': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                uploader = info.get('uploader', 'Unknown')
                
                print(f"\n✅ Downloaded successfully!")
                print(f"   Title: {title}")
                print(f"   Artist: {uploader}")
                print(f"   Duration: {timedelta(seconds=int(duration))}")
                
                return 'djset.mp3', title, duration
        except Exception as e:
            print(f"❌ Error downloading: {e}")
            sys.exit(1)
    
    def create_samples(self, audio_file, sample_interval_sec=45, sample_duration_sec=10):
        """
        Create small samples every X seconds for recognition
        sample_interval_sec: How often to sample (45 seconds = good for track changes)
        sample_duration_sec: Length of each sample (10 seconds = perfect for API)
        """
        print(f"\n🎯 Creating samples every {sample_interval_sec} seconds...")
        print("=" * 60)
        
        # Load audio
        try:
            audio = AudioSegment.from_mp3(audio_file)
            total_duration_sec = len(audio) / 1000
            print(f"📊 Total duration: {timedelta(seconds=int(total_duration_sec))}")
        except Exception as e:
            print(f"❌ Error loading audio: {e}")
            sys.exit(1)
        
        samples = []
        sample_count = 0
        
        # Create samples at regular intervals
        current_time_sec = 30  # Start at 30 seconds (skip intro)
        
        while current_time_sec < total_duration_sec - 30:  # Stop 30 seconds before end
            start_ms = int(current_time_sec * 1000)
            end_ms = int((current_time_sec + sample_duration_sec) * 1000)
            
            # Extract sample
            sample = audio[start_ms:end_ms]
            sample_count += 1
            
            # Save sample
            sample_filename = f"sample_{sample_count:03d}.mp3"
            sample.export(sample_filename, format="mp3")
            
            samples.append({
                'filename': sample_filename,
                'timestamp': current_time_sec,
                'number': sample_count
            })
            
            # Move to next sample point
            current_time_sec += sample_interval_sec
        
        print(f"📦 Created {len(samples)} samples")
        print(f"⏱️  Sampling: every {sample_interval_sec}s, {sample_duration_sec}s clips")
        return samples
    
    def recognize_sample(self, sample_info):
        """Recognize a single 10-second sample"""
        try:
            # Check file size
            file_size = os.path.getsize(sample_info['filename'])
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                print(f"   ⚠️  Sample {sample_info['number']} too large: {file_size/1024/1024:.1f}MB")
                return None
            
            with open(sample_info['filename'], 'rb') as f:
                response = requests.post(
                    'https://api.audd.io/',
                    data={
                        'api_token': self.api_key,
                        'return': 'spotify,apple_music',
                    },
                    files={'file': f},
                    timeout=30  # 30 seconds per sample
                )
            
            if response.status_code != 200:
                return None
            
            result = response.json()
            
            if result.get('status') == 'success' and result.get('result'):
                track = result['result']
                track['sample_timestamp'] = sample_info['timestamp']
                track['sample_number'] = sample_info['number']
                return track
            
            return None
                
        except Exception as e:
            print(f"   ⚠️  Error processing sample {sample_info['number']}: {e}")
            return None
    
    def process_samples(self, samples):
        """Process all samples and identify tracks"""
        print(f"\n🎵 Analyzing {len(samples)} samples...")
        print("=" * 60)
        
        recognized_tracks = []
        
        for i, sample in enumerate(samples, 1):
            timestamp_str = str(timedelta(seconds=int(sample['timestamp'])))
            print(f"🎧 Sample {i}/{len(samples)} @ {timestamp_str}...", end=" ")
            
            track = self.recognize_sample(sample)
            if track:
                artist = track.get('artist', 'Unknown')
                title = track.get('title', 'Unknown')
                print(f"✅ {artist} - {title}")
                recognized_tracks.append(track)
            else:
                print("❌ No match")
            
            # Small delay to be respectful
            time.sleep(1)
        
        return recognized_tracks
    
    def build_tracklist(self, recognized_tracks):
        """Build final tracklist with unique tracks and first occurrence timestamps"""
        if not recognized_tracks:
            return []
        
        print(f"\n🔄 Building tracklist from {len(recognized_tracks)} recognized samples...")
        
        # Sort by timestamp
        recognized_tracks.sort(key=lambda x: x['sample_timestamp'])
        
        seen_tracks = set()
        unique_tracklist = []
        
        for track in recognized_tracks:
            # Create unique identifier (normalize to handle slight variations)
            artist = track.get('artist', 'Unknown').strip().lower()
            title = track.get('title', 'Unknown').strip().lower()
            track_key = f"{artist}|{title}"
            
            # Only add if we haven't seen this track before
            if track_key not in seen_tracks:
                seen_tracks.add(track_key)
                
                unique_tracklist.append({
                    'timestamp': track['sample_timestamp'],
                    'artist': track.get('artist', 'Unknown').strip(),
                    'title': track.get('title', 'Unknown').strip(),
                    'album': track.get('album', ''),
                    'spotify': track.get('spotify', {}),
                    'apple_music': track.get('apple_music', {})
                })
        
        print(f"✅ Final tracklist: {len(unique_tracklist)} unique tracks (removed {len(recognized_tracks) - len(unique_tracklist)} duplicates)")
        return unique_tracklist
    
    def cleanup_samples(self, samples):
        """Remove temporary sample files"""
        print("\n🧹 Cleaning up temporary files...")
        for sample in samples:
            try:
                if os.path.exists(sample['filename']):
                    os.remove(sample['filename'])
            except:
                pass
    
    def save_results(self, tracks, set_title):
        """Save results in multiple formats"""
        
        # Save JSON
        with open('tracklist.json', 'w', encoding='utf-8') as f:
            json.dump(tracks, f, indent=2, ensure_ascii=False)
        
        # Save formatted text file (clean format)
        with open('tracklist.txt', 'w', encoding='utf-8') as f:
            f.write(f"{'=' * 70}\n")
            f.write(f"DJ SET TRACKLIST\n")
            f.write(f"{'=' * 70}\n")
            f.write(f"Set: {set_title}\n")
            f.write(f"Total Tracks: {len(tracks)}\n")
            f.write(f"{'=' * 70}\n\n")
            
            for i, track in enumerate(tracks, 1):
                timestamp = timedelta(seconds=int(track['timestamp']))
                artist = track.get('artist', 'Unknown')
                title = track.get('title', 'Unknown')
                
                # Clean format: just timestamp, artist, and title
                f.write(f"{i}. [{timestamp}] {artist} - {title}\n")
                
                # Add streaming links if available
                if track.get('spotify') and track['spotify'].get('external_urls'):
                    f.write(f"   🎧 Spotify: {track['spotify']['external_urls']['spotify']}\n")
                if track.get('apple_music') and track['apple_music'].get('url'):
                    f.write(f"   🍎 Apple Music: {track['apple_music']['url']}\n")
                f.write("\n")
        
        print(f"✅ Saved tracklist.txt (clean format - unique tracks only)")
        print(f"✅ Saved tracklist.json (structured data)")
        
        # Also create a simple text-only version
        with open('tracklist_simple.txt', 'w', encoding='utf-8') as f:
            f.write(f"DJ SET TRACKLIST - {set_title}\n")
            f.write(f"Total: {len(tracks)} unique tracks\n")
            f.write(f"{'='*50}\n\n")
            
            for track in tracks:
                timestamp = timedelta(seconds=int(track['timestamp']))
                artist = track.get('artist', 'Unknown')
                title = track.get('title', 'Unknown')
                f.write(f"[{timestamp}] {artist} - {title}\n")
        
        print(f"✅ Saved tracklist_simple.txt (timestamps + track names only)")
    
    def analyze(self, soundcloud_url=None):
        """Main analysis workflow"""
        print("\n" + "=" * 70)
        print("DJ SET ANALYZER - SAMPLING VERSION")
        print("Works with free API limits - 10-second samples every 45 seconds")
        print("=" * 70)
        
        # Check if file already exists
        if os.path.exists('djset.mp3'):
            print("✅ Found existing djset.mp3 - skipping download")
            set_title = "Existing DJ Set"
        elif soundcloud_url:
            # Download if URL provided
            audio_file, set_title, duration = self.download_soundcloud(soundcloud_url)
        else:
            print("❌ No djset.mp3 found and no URL provided")
            sys.exit(1)
        
        # Create samples (10-second clips every 45 seconds)
        samples = self.create_samples('djset.mp3', sample_interval_sec=45, sample_duration_sec=10)
        
        # Process samples
        recognized_tracks = self.process_samples(samples)
        
        # Clean up temporary files
        self.cleanup_samples(samples)
        
        if not recognized_tracks:
            print("\n⚠️  No tracks were recognized.")
            print("💡 Tips:")
            print("   - The set might contain very obscure tracks")
            print("   - Audio quality might be too low")
            print("   - Try a different DJ set")
            return
        
        # Build final tracklist
        final_tracks = self.build_tracklist(recognized_tracks)
        
        # Save results
        self.save_results(final_tracks, set_title)
        
        # Display summary
        print(f"\n{'=' * 70}")
        print(f"✅ SUCCESS! Recognized {len(final_tracks)} tracks")
        print(f"📊 Recognition rate: {len(recognized_tracks)}/{len(samples)} samples")
        print(f"{'=' * 70}\n")
        
        # Show all tracks
        print("🎵 Complete Tracklist:\n")
        for i, track in enumerate(final_tracks, 1):
            timestamp = timedelta(seconds=int(track['timestamp']))
            artist = track.get('artist', 'Unknown')
            title = track.get('title', 'Unknown')
            print(f"   {i}. [{timestamp}] {artist} - {title}")
        
        print(f"\n📂 Check tracklist.txt for the complete list with links!")


def main():
    print("\n" + "=" * 70)
    print("  DJ SET TRACK RECOGNIZER - SAMPLING VERSION")
    print("  Works with free API limits (10-second samples)")
    print("=" * 70)
    
    # Get API key
    api_key = input("\n🔑 Enter your AudD API key: ").strip()
    if not api_key:
        print("❌ API key required!")
        print("\n💡 Get a free API key at: https://audd.io/")
        sys.exit(1)
    
    # Check if we already have the file
    if os.path.exists('djset.mp3'):
        print("✅ Found djset.mp3 - will analyze existing file")
        analyzer = SamplingDJSetAnalyzer(api_key)
        analyzer.analyze()
    else:
        # Get SoundCloud URL
        soundcloud_url = input("🔗 Enter SoundCloud URL: ").strip()
        if not soundcloud_url:
            print("❌ URL required!")
            sys.exit(1)
        
        analyzer = SamplingDJSetAnalyzer(api_key)
        analyzer.analyze(soundcloud_url)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
