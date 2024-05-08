"""
This contains utility function that extract the metadata from files to check the creation date
and location.
"""

from datetime import datetime
import pytz

import exifread
import ffmpeg
from dateutil import parser
from PyPDF2 import PdfReader
import magic

def convert_to_degrees(value):
    """Convert GPS coordinates to a float."""
    d, m, s = [float(x.num) / float(x.den) for x in value.values]
    return d + (m / 60.0) + (s / 3600.0)

def extract_image_metadata(file_path):
    with open(file_path, 'rb') as file:
        tags = exifread.process_file(file, details=False)

    creation_time = None
    location_data = None
    duration = None

    # Check if 'EXIF DateTimeOriginal' is in tags for creation time
    if 'EXIF DateTimeOriginal' in tags:
        creation_time_str = str(tags['EXIF DateTimeOriginal'])
        offset_time_original = str(tags['EXIF OffsetTimeOriginal']) if 'EXIF OffsetTimeOriginal' in tags else None
        try:
            # EXIF Date format: 'YYYY:MM:DD HH:MM:SS'
            if offset_time_original:
                # The time offset is the timezone given as '+-HH:MM'
                creation_time_str += offset_time_original
                creation_time = datetime.strptime(creation_time_str, '%Y:%m:%d %H:%M:%S%z')
            else:
                creation_time = datetime.strptime(creation_time_str, '%Y:%m:%d %H:%M:%S')
        except ValueError:
            print(f"Error parsing creation date: {creation_time_str}")

    # Check for GPS data
    if 'GPS GPSLatitude' in tags and 'GPS GPSLatitudeRef' in tags and \
       'GPS GPSLongitude' in tags and 'GPS GPSLongitudeRef' in tags:
        try:
            # Extract latitude
            lat = tags['GPS GPSLatitude']
            lat_ref = tags['GPS GPSLatitudeRef']
            latitude = convert_to_degrees(lat)
            if str(lat_ref) != 'N':
                latitude = -latitude

            # Extract longitude
            lon = tags['GPS GPSLongitude']
            lon_ref = tags['GPS GPSLongitudeRef']
            longitude = convert_to_degrees(lon)
            if str(lon_ref) != 'E':
                longitude = -longitude

            location_data = {'lat': latitude, 'lng': longitude}
        except Exception as e:
            print(f"Error parsing GPS data: {e}")

    return creation_time, location_data, duration

def extract_video_metadata(file_path):
    creation_time = None
    location_data = None  # Video files generally do not contain GPS data
    duration = None

    try:
        ffmpeg_probe = ffmpeg.probe(file_path)

        if 'format' in ffmpeg_probe:
            format_data = ffmpeg_probe['format']
            if 'duration' in format_data:
                duration = int(float(format_data['duration']) * 1000)  # Convert to ms
            if 'tags' in format_data:
                tags = format_data['tags']
                if 'creation_time' in tags:
                    creation_time_str = tags['creation_time']
                    try:
                        creation_time = parser.parse(creation_time_str)
                    except ValueError:
                        print(f"Error parsing creation date: {creation_time_str}")
    except Exception as e:
        print(f"Error reading video metadata: {e}")

    return creation_time, location_data, duration

def extract_audio_metadata(file_path):
    creation_time = None
    location_data = None  # Audio files generally do not contain GPS data
    duration = None

    try:
        ffmpeg_probe = ffmpeg.probe(file_path)

        if 'format' in ffmpeg_probe:
            format_data = ffmpeg_probe['format']
            if 'duration' in format_data:
                duration = int(float(format_data['duration']) * 1000)
            if 'tags' in format_data:
                tags = format_data['tags']
                if 'creation_time' in tags:
                    creation_time_str = tags['creation_time']
                    try:
                        creation_time = parser.parse(creation_time_str)
                    except ValueError:
                        print(f"Error parsing creation date: {creation_time_str}")
    except Exception as e:
        print(f"Error reading audio metadata: {e}")

    return creation_time, location_data, duration

def extract_pdf_metadata(file_path):
    creation_time = None
    location_data = None  # PDFs generally do not contain GPS data
    duration = None

    try:
        reader = PdfReader(file_path)
        doc_info = reader.metadata

        # Check for creation date in the document metadata
        if doc_info is not None and '/CreationDate' in doc_info:
            raw_date = doc_info['/CreationDate']

            # The PDF date string is in the format 'D:YYYYMMDDHHmmSS' and may contain extra info
            if raw_date.startswith('D:'):
                raw_date = raw_date[2:]  # Strip the 'D:' prefix

            # Using dateutil to parse the date
            try:
                # The format might contain additional timezone or other info
                # we try to parse up to the basic datetime info
                creation_time = parser.parse(raw_date, fuzzy=True)
            except ValueError as ve:
                print(f"Error parsing the date: {ve}")
    except Exception as e:
        print(f"Error reading PDF metadata: {e}")

    return creation_time, location_data, duration


def extract_file_metadata(file_path) -> tuple[datetime, dict, int]:
    """
    Extracts the metadata from a file and returns the creation time and location data.
    """
    creation_time = None
    location_data = None
    duration = None

    # Check the file type and call the appropriate function
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(file_path)

    try:
        if mime_type.startswith('image'):
            creation_time, location_data, duration = extract_image_metadata(file_path)
        elif mime_type.startswith('video'):
            creation_time, location_data, duration = extract_video_metadata(file_path)
        elif mime_type.startswith('audio'):
            creation_time, location_data, duration = extract_audio_metadata(file_path)
        elif mime_type.startswith('application/pdf'):
            creation_time, location_data, duration = extract_pdf_metadata(file_path)
        else:
            print(f"Unsupported file type: {mime_type}")
    except Exception as e:
        print(f"Error reading file metadata for {file_path}: {e}")

    print("File Metadata:", creation_time, location_data, duration)
    return creation_time, location_data, duration


if __name__ == "__main__":
    from pathlib import Path

    files_path = Path(__file__).parent.parent.parent / "tests" / "files"
    assert files_path.exists()

    image_file = files_path / "test_img.jpg"
    image_file_w_meta = files_path / "test_img_w_meta.png"
    video_file = files_path / "test_video.mp4"
    video_file_w_meta = files_path / "test_video_w_meta.MOV"
    audio_file = files_path / "test_audio.mp3"
    audio_file_w_meta = files_path / "test_audio_w_meta.m4a"
    pdf_file = files_path / "test_pdf.pdf"
    pdf_file_w_meta = files_path / "test_pdf_w_meta.pdf"

    print("Image metadata:")
    base_img_time, base_img_loc, base_img_loc_duration = extract_image_metadata(image_file)
    # Print out the datetime, location, and datetime converted to ms
    print(base_img_time, base_img_loc, base_img_time.timestamp() * 1000 if base_img_time else None)

    print("Image with metadata:")
    img_time, img_loc, img_duration = extract_image_metadata(image_file_w_meta)
    true_time_ms = 1715105926000
    print(img_time, img_loc, img_time.timestamp() * 1000 if img_time else None, img_time.tzinfo)
    assert img_time.timestamp() * 1000 == true_time_ms


    print("Video metadata:")
    video_time, video_loc, video_duration = extract_video_metadata(video_file)
    print(video_time, video_loc, video_time.timestamp() * 1000 if video_time else None, video_duration)

    print("Video with metadata:")
    video_time, video_loc, video_duration = extract_video_metadata(video_file_w_meta)
    true_time_ms = 1714932721000
    print(video_time, video_loc, video_time.timestamp() * 1000 if video_time else None, video_duration)
    assert video_time.timestamp() * 1000 == true_time_ms


    print("Audio metadata:")
    audio_time, audio_loc, audio_duration = extract_audio_metadata(audio_file)
    print(audio_time, audio_loc, audio_time.timestamp() * 1000 if audio_time else None, audio_duration)

    print("Audio with metadata:")
    audio_time, audio_loc, audio_duration = extract_audio_metadata(audio_file_w_meta)
    print(audio_time, audio_loc, audio_time.timestamp() * 1000 if audio_time else None, audio_duration)


    print("PDF metadata:")
    pdf_time, pdf_loc, pdf_duration = extract_pdf_metadata(pdf_file)
    print(pdf_time, pdf_loc, pdf_time.timestamp() * 1000 if pdf_time else None)

    print("PDF with metadata:")
    pdf_time, pdf_loc, pdf_duration = extract_pdf_metadata(pdf_file_w_meta)
    true_time_ms = 1715178820000
    print(pdf_time, pdf_loc, pdf_time.timestamp() * 1000 if pdf_time else None)
    assert pdf_time.timestamp() * 1000 == true_time_ms


    # Verify that the wrapper returns the same values as the individual functions
    auto_time, auto_loc, auto_duration = extract_file_metadata(image_file_w_meta)
    img_time, img_loc, img_duration = extract_image_metadata(image_file_w_meta)
    assert auto_time == img_time
    assert auto_loc == img_loc
    assert auto_duration == img_duration

    auto_time, auto_loc, auto_duration = extract_file_metadata(video_file_w_meta)
    video_time, video_loc, video_duration = extract_video_metadata(video_file_w_meta)
    assert auto_time == video_time
    assert auto_loc == video_loc
    assert auto_duration == video_duration

    auto_time, auto_loc, auto_duration = extract_file_metadata(audio_file_w_meta)
    audio_time, audio_loc, audio_duration = extract_audio_metadata(audio_file_w_meta)
    assert auto_time == audio_time
    assert auto_loc == audio_loc
    assert auto_duration == audio_duration

    auto_time, auto_loc, auto_duration = extract_file_metadata(pdf_file_w_meta)
    pdf_time, pdf_loc, pdf_duration = extract_pdf_metadata(pdf_file_w_meta)
    assert auto_time == pdf_time
    assert auto_loc == pdf_loc
    assert auto_duration == pdf_duration
