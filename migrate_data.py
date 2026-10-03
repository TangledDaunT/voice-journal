#!/usr/bin/env python3
"""
Migration script for Voice Journal
Moves existing audio/transcripts/DB from old locations to new DATA_ROOT layout
"""

import os
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime
import sqlite3

def find_external_drive():
    """Auto-detect external drive mount point"""
    # Check common mount points
    for mount_point in ['/media', '/mnt', '/home/shreyansh/NAS']:
        if os.path.exists(mount_point):
            # Look for mounted drives
            for item in os.listdir(mount_point):
                item_path = os.path.join(mount_point, item)
                if os.path.ismount(item_path) and os.access(item_path, os.W_OK):
                    return item_path
    return None

def setup_data_root(data_root=None):
    """Setup and validate DATA_ROOT"""
    if data_root is None:
        data_root = find_external_drive()
        if data_root is None:
            print("ERROR: Could not auto-detect external drive")
            print("Please connect your 1TB external drive and set DATA_ROOT manually")
            sys.exit(1)
    
    # Ensure DATA_ROOT exists and is writable
    if not os.path.exists(data_root):
        print(f"ERROR: DATA_ROOT path does not exist: {data_root}")
        sys.exit(1)
    
    if not os.access(data_root, os.W_OK):
        print(f"ERROR: DATA_ROOT path is not writable: {data_root}")
        sys.exit(1)
    
    print(f"Using DATA_ROOT: {data_root}")
    return data_root

def create_directory_structure(data_root):
    """Create the new directory structure"""
    voice_journal_dir = Path(data_root) / "voice-journal"
    
    directories = [
        voice_journal_dir / "audio",
        voice_journal_dir / "transcripts", 
        voice_journal_dir / "db",
        voice_journal_dir / "audio" / "audio_cache"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {directory}")
    
    return voice_journal_dir

def migrate_database(old_db_path, new_db_path):
    """Migrate SQLite database"""
    if not os.path.exists(old_db_path):
        print(f"Old database not found: {old_db_path}")
        return False
    
    print(f"Migrating database from {old_db_path} to {new_db_path}")
    
    # Copy the database file
    shutil.copy2(old_db_path, new_db_path)
    print("Database copied successfully")
    return True

def migrate_audio_files(old_audio_dir, new_audio_base):
    """Migrate audio files to new date-based structure"""
    if not os.path.exists(old_audio_dir):
        print(f"Old audio directory not found: {old_audio_dir}")
        return 0
    
    print(f"Migrating audio files from {old_audio_dir}")
    migrated_count = 0
    
    # Walk through old audio directory
    for root, dirs, files in os.walk(old_audio_dir):
        for file in files:
            if file.endswith(('.opus', '.wav', '.flac')):
                old_file_path = os.path.join(root, file)
                
                # Try to extract date from path or filename
                # Default to today if we can't determine
                date_str = datetime.now().strftime("%Y-%m-%d")
                
                # Look for date patterns in path
                path_parts = Path(root).parts
                for part in path_parts:
                    if len(part) == 10 and part[4] == '-' and part[7] == '-':  # YYYY-MM-DD
                        try:
                            datetime.strptime(part, "%Y-%m-%d")
                            date_str = part
                            break
                        except ValueError:
                            pass
                
                # Create new path structure
                new_date_dir = Path(new_audio_base) / date_str / "segments"
                new_date_dir.mkdir(parents=True, exist_ok=True)
                
                new_file_path = new_date_dir / file
                
                # Avoid overwriting existing files
                counter = 1
                original_new_file_path = new_file_path
                while new_file_path.exists():
                    stem = original_new_file_path.stem
                    suffix = original_new_file_path.suffix
                    new_file_path = new_date_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
                
                # Copy the file
                shutil.copy2(old_file_path, new_file_path)
                print(f"Migrated audio: {file} -> {new_file_path.relative_to(new_audio_base)}")
                migrated_count += 1
    
    return migrated_count

def migrate_transcripts(old_transcript_dir, new_transcript_base):
    """Migrate transcript files to new date-based structure"""
    if not os.path.exists(old_transcript_dir):
        print(f"Old transcript directory not found: {old_transcript_dir}")
        return 0
    
    print(f"Migrating transcript files from {old_transcript_dir}")
    migrated_count = 0
    
    # Walk through old transcript directory
    for root, dirs, files in os.walk(old_transcript_dir):
        for file in files:
            if file.endswith(('.json', '.jsonl', '.txt')):
                old_file_path = os.path.join(root, file)
                
                # Try to extract date from path or filename
                date_str = datetime.now().strftime("%Y-%m-%d")
                
                # Look for date patterns in path
                path_parts = Path(root).parts
                for part in path_parts:
                    if len(part) == 10 and part[4] == '-' and part[7] == '-':  # YYYY-MM-DD
                        try:
                            datetime.strptime(part, "%Y-%m-%d")
                            date_str = part
                            break
                        except ValueError:
                            pass
                
                # Create new path structure
                new_date_dir = Path(new_transcript_base) / date_str
                new_date_dir.mkdir(parents=True, exist_ok=True)
                
                new_file_path = new_date_dir / file
                
                # Avoid overwriting existing files
                counter = 1
                original_new_file_path = new_file_path
                while new_file_path.exists():
                    stem = original_new_file_path.stem
                    suffix = original_new_file_path.suffix
                    new_file_path = new_date_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
                
                # Copy the file
                shutil.copy2(old_file_path, new_file_path)
                print(f"Migrated transcript: {file} -> {new_file_path.relative_to(new_transcript_base)}")
                migrated_count += 1
    
    return migrated_count

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate Voice Journal data to new structure")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without doing it")
    parser.add_argument("--data-root", help="Specify DATA_ROOT path (optional, will auto-detect)")
    parser.add_argument("--old-data-dir", default=".", help="Directory containing old data (default: current directory)")
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("=== DRY RUN MODE ===")
    
    # Setup DATA_ROOT
    data_root = setup_data_root(args.data_root)
    
    # Define paths
    voice_journal_dir = Path(data_root) / "voice-journal"
    old_data_dir = Path(args.old_data_dir)
    
    # Old data locations (based on current structure)
    old_locations = {
        "database": old_data_dir / "data" / "voice_journal.db",
        "audio": old_data_dir / "audio_clips",
        "transcripts": old_data_dir / "audio_cache",  # This might need adjustment
        "obsidian": old_data_dir / "obsidian_vault"  # We're not migrating this as it's disabled
    }
    
    # New data locations
    new_locations = {
        "database": voice_journal_dir / "db" / "voice_journal.db",
        "audio_base": voice_journal_dir / "audio",
        "transcripts_base": voice_journal_dir / "transcripts",
        "audio_cache": voice_journal_dir / "audio" / "audio_cache"
    }
    
    print(f"Old data directory: {old_data_dir}")
    print(f"New data directory: {voice_journal_dir}")
    print()
    
    if not args.dry_run:
        # Create directory structure
        create_directory_structure(data_root)
        
        # Migrate database
        migrate_database(
            str(old_locations["database"]), 
            str(new_locations["database"])
        )
        
        # Migrate audio files
        audio_count = migrate_audio_files(
            str(old_locations["audio"]), 
            str(new_locations["audio_base"])
        )
        
        # Migrate transcript files
        transcript_count = migrate_transcripts(
            str(old_locations["transcripts"]), 
            str(new_locations["transcripts_base"])
        )
        
        print()
        print(f"Migration complete!")
        print(f"  Database: {'Migrated' if os.path.exists(old_locations['database']) else 'Not found'}")
        print(f"  Audio files: {audio_count} migrated")
        print(f"  Transcript files: {transcript_count} migrated")
    else:
        print("DRY RUN - Would perform the following actions:")
        print(f"  1. Create directory structure in {voice_journal_dir}")
        print(f"  2. Migrate database from {old_locations['database']} to {new_locations['database']}")
        print(f"  3. Migrate audio files from {old_locations['audio']} to {new_locations['audio_base']}")
        print(f"  4. Migrate transcript files from {old_locations['transcripts']} to {new_locations['transcripts_base']}")
        
        # Check what exists
        print()
        print("Existing files:")
        for name, path in old_locations.items():
            if os.path.exists(path):
                if os.path.isdir(path):
                    file_count = sum(len(files) for _, _, files in os.walk(path))
                    print(f"  {name}: {path} ({file_count} files)")
                else:
                    print(f"  {name}: {path} ({os.path.getsize(path)} bytes)")
            else:
                print(f"  {name}: {path} (NOT FOUND)")

if __name__ == "__main__":
    main()
