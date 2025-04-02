import os
import subprocess
import logging
import json

logger = logging.getLogger(__name__)

def get_audio_duration(file_path):
    """Get the duration of an audio file in seconds using ffprobe."""
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None
    
    cmd = [
        'ffprobe', 
        '-v', 'error', 
        '-show_entries', 'format=duration', 
        '-of', 'default=noprint_wrappers=1:nokey=1', 
        file_path
    ]
    
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
        else:
            logger.error(f"ffprobe error: {result.stderr}")
            return None
    except Exception as e:
        logger.error(f"Error getting audio duration: {str(e)}")
        return None

def concatenate_audio_files(file_list, output_file):
    """Concatenate multiple audio files into one using FFmpeg."""
    if not file_list:
        logger.error("No files to concatenate")
        return False
    
    # Create a temporary concat file
    concat_file = os.path.join(os.path.dirname(output_file), 'concat_list.txt')
    
    try:
        with open(concat_file, 'w') as f:
            for file_path in file_list:
                if os.path.exists(file_path):
                    f.write(f"file '{file_path}'\n")
                else:
                    logger.warning(f"File not found, skipping: {file_path}")
        
        # Run FFmpeg to concatenate the files
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file if exists
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            output_file
        ]
        
        logger.info(f"Executing concatenation command: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Clean up the temporary file
        if os.path.exists(concat_file):
            os.remove(concat_file)
        
        if result.returncode == 0:
            logger.info(f"Successfully concatenated {len(file_list)} files into {output_file}")
            return True
        else:
            logger.error(f"FFmpeg concatenation error: {result.stderr}")
            return False
    
    except Exception as e:
        logger.error(f"Error concatenating audio files: {str(e)}")
        if os.path.exists(concat_file):
            os.remove(concat_file)
        return False
